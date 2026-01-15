import asyncio
import json
import os
import redis.asyncio as redis
import asyncpg
import re
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/postgres")


class PersistenceWorker:
    def __init__(self):
        self.buffer = []
        self.lock = asyncio.Lock()
        self.batch_size = 200
        self.flush_interval = 5  # 5초마다 버퍼 비우기 (배치 효율성 향상)

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

        try:
            async with pool.acquire() as conn:
                # ON CONFLICT를 사용하여 중복 시 volume 누적, price 업데이트
                # 기본 키: (stock_code, time)
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
                        r.get("stock_code"),  # 실제 종목코드 (6자리) - PK
                        r.get("symbol"),  # KIS 내부 식별자 (optional)
                        (
                            self.parse_time(time_str=r["time"])
                            if isinstance(r["time"], str)
                            else r["time"]
                        ),
                        r["price"],
                        r["volume"],
                    )
                    for r in current_batch
                    if r.get("stock_code")  # stock_code가 있는 것만 저장
                ]

                if records:
                    await conn.executemany(insert_query, records)
                    print(f"Saved {len(records)} rows to database (with upsert)")
                else:
                    print("No valid records to save (missing stock_code)")
        except Exception as e:
            print(f"Error saving to database: {e}")
            # 실패 시 버퍼 복구
            async with self.lock:
                self.buffer.extend(current_batch)
            print(f"Buffer restored: {len(self.buffer)} rows")

    async def run(self):
        print(f"[INIT] Starting PersistenceWorker...")
        print(f"[INIT] REDIS_URL: {REDIS_URL}")
        masked_url = re.sub(r"://[^:]+:[^@]+@", "://***:***@", DATABASE_URL)
        print(f"[INIT] DATABASE_URL: {masked_url}")

        try:
            # Redis 연결
            print("[INIT] Connecting to Redis...")
            redis_client = redis.from_url(REDIS_URL)

            # Redis 연결 테스트
            await redis_client.ping()
            print(f"[INIT] Redis connected and ping successful")

            # Connection Pool 생성
            print("[INIT] Creating database connection pool...")
            pool = await asyncpg.create_pool(dsn=DATABASE_URL)
            print("[INIT] Database connection pool created")

            # Redis Pub/Sub 구독 (패턴 매칭을 위해 psubscribe 사용)
            print("[INIT] Subscribing to Redis channel: stock:realtime:*")
            pubsub = redis_client.pubsub()
            await pubsub.psubscribe("stock:realtime:*")
            print("[INIT] Subscribed to Redis channel successfully")

            # 주기적으로 버퍼를 비우는 태스크
            asyncio.create_task(self.auto_flush(pool))
            print("[INIT] Auto-flush task started. Listening for messages...")

            message_count = 0
            async for message in pubsub.listen():
                print(
                    f"[DEBUG] Received raw message: type={message['type']}, message={message}"
                )

                if message["type"] == "pmessage":
                    message_count += 1
                    channel = (
                        message["channel"].decode("utf-8")
                        if isinstance(message["channel"], bytes)
                        else message["channel"]
                    )
                    data_raw = (
                        message["data"].decode("utf-8")
                        if isinstance(message["data"], bytes)
                        else message["data"]
                    )
                    print(f"[RECV #{message_count}] channel={channel}, data={data_raw}")

                    data = json.loads(data_raw)
                    async with self.lock:
                        self.buffer.append(data)
                        buffer_size = len(self.buffer)
                        # 배치 크기에 도달하면 즉시 저장
                        if buffer_size >= self.batch_size:
                            print(
                                f"[BUFFER] Batch size reached ({buffer_size}). Saving..."
                            )
                            await self.save_to_database(pool)
                        elif buffer_size % 50 == 0:  # 50개마다 로그 출력 (성능 개선)
                            print(
                                f"[BUFFER] Current size: {buffer_size}/{self.batch_size}"
                            )
        except Exception as e:
            print(f"Error in run(): {e}")
            import traceback

            traceback.print_exc()
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
