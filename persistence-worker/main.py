import asyncio
import os
import json
import aio_pika
import asyncpg
import re
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/postgres")

# RabbitMQ 설정
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
EXCHANGE_NAME = "stock.realtime"
QUEUE_NAME = "stock.ticks.persistence"


class PersistenceWorker:
    def __init__(self):
        self.buffer = []
        self.lock = asyncio.Lock()
        self.batch_size = 200
        self.flush_interval = 5  # 5초마다 버퍼 비우기
        self._flush_task = None  # auto_flush 태스크 저장용

    def parse_time(self, time_str: str) -> datetime:
        """HHMMSS 형식의 시간 문자열을 datetime으로 변환"""
        today = datetime.now().date()
        hour = int(time_str[0:2])
        minute = int(time_str[2:4])
        second = int(time_str[4:6])
        return datetime(today.year, today.month, today.day, hour, minute, second)

    async def save_to_database(self, pool):
        if not self.buffer:
            return

        async with self.lock:
            current_batch = self.buffer
            self.buffer = []

        if not current_batch:
            return

        try:
            async with pool.acquire() as conn:
                insert_query = """
                    INSERT INTO stock_ticks (stock_code, symbol, time, price, volume)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (stock_code, time) DO UPDATE SET
                        price = EXCLUDED.price,
                        volume = stock_ticks.volume + EXCLUDED.volume,
                        symbol = COALESCE(EXCLUDED.symbol, stock_ticks.symbol)
                """
                records = [
                    (
                        r.get("stock_code"),
                        r.get("symbol"),
                        (
                            self.parse_time(time_str=r["time"])
                            if isinstance(r["time"], str)
                            else r["time"]
                        ),
                        int(r["price"]),
                        int(r["volume"]),
                    )
                    for r in current_batch
                    if r.get("stock_code")
                ]

                if records:
                    await conn.executemany(insert_query, records)
                    print(f"[DB] Saved {len(records)} rows to database")
                else:
                    print("[DB] No valid records to save (missing stock_code)")

        except Exception as e:
            print(f"[ERROR] Error saving to database: {e}")
            # 실패 시 버퍼 복구 (재처리 위해)
            async with self.lock:
                self.buffer = current_batch + self.buffer
            print(f"[BUFFER] Restored: {len(self.buffer)} rows (will retry)")
            raise  # 예외를 상위로 전파하여 RabbitMQ에서 NACK 처리

    async def run(self):
        print("[INIT] Starting PersistenceWorker (RabbitMQ mode)...")
        print(f"[INIT] Queue: {QUEUE_NAME}, Exchange: {EXCHANGE_NAME}")
        print(f"[INIT] RABBITMQ_URL: {RABBITMQ_URL}")
        masked_url = re.sub(r"://[^:]+:[^@]+@", "://***:***@", DATABASE_URL)
        print(f"[INIT] DATABASE_URL: {masked_url}")

        try:
            # RabbitMQ 연결
            print("[INIT] Connecting to RabbitMQ...")
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=200)  # 배치 크기
            print("[INIT] RabbitMQ connected")

            # Exchange 선언
            exchange = await channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.FANOUT,
                durable=True
            )

            # Queue 선언
            # 주의: TTL 제거됨 - 메시지가 처리될 때까지 유지
            # x-max-length만 유지하여 디스크 공간 보호
            queue = await channel.declare_queue(
                QUEUE_NAME,
                durable=True,
                arguments={
                    "x-max-length": 1000000,  # 최대 메시지 수 (초과 시 오래된 것부터 삭제)
                }
            )

            # Queue를 Exchange에 바인딩
            await queue.bind(exchange)
            print(f"[INIT] Queue '{QUEUE_NAME}' bound to '{EXCHANGE_NAME}'")

            # Database Connection Pool
            print("[INIT] Creating database connection pool...")
            pool = await asyncpg.create_pool(dsn=DATABASE_URL)
            print("[INIT] Database pool created")

            # 주기적 flush 태스크 생성
            self._flush_task = asyncio.create_task(self.auto_flush(pool))
            print("[INIT] Listening for messages...")

            message_count = 0

            # Consumer
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    try:
                        async with message.process(requeue=True):  # 실패 시 재큐잉
                            message_count += 1

                            # 메시지 파싱
                            data = json.loads(message.body)

                            # 버퍼에 추가
                            async with self.lock:
                                self.buffer.append(data)

                            if message_count % 50 == 0:
                                print(
                                    f"[RECV] Processed {message_count} messages, buffer={len(self.buffer)}"
                                )

                            # 배치 크기 도달 시 즉시 저장
                            if len(self.buffer) >= self.batch_size:
                                await self.save_to_database(pool)

                    except json.JSONDecodeError as e:
                        print(f"[ERROR] JSON decode error: {e}")
                        # JSON 파싱 실패 시 메시지 버림 (ACK)
                        await message.ack()
                    except Exception as e:
                        print(f"[ERROR] Error processing message: {e}")
                        # 예외 발생 시 NACK (재큐잉)
                        # message.process(requeue=True)가 자동으로 처리

        except Exception as e:
            print(f"[FATAL] Error in run(): {e}")
            import traceback
            traceback.print_exc()

            # flush 태스크 정리
            if self._flush_task:
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except asyncio.CancelledError:
                    pass
            raise

    async def auto_flush(self, pool):
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.save_to_database(pool)


if __name__ == "__main__":
    try:
        worker = PersistenceWorker()
        asyncio.run(worker.run())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()
        raise
