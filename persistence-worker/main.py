import asyncio
import json
import os
import redis.asyncio as redis
import asyncpg
import re
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/postgres")

# Redis Stream 설정
STREAM_KEY = "stock:realtime"
CONSUMER_GROUP = "stock_ticks_ingest"
CONSUMER_NAME = os.getenv("CONSUMER_NAME", f"persistence_worker_{os.getpid()}")


class PersistenceWorker:
    def __init__(self):
        self.buffer = []
        self.lock = asyncio.Lock()
        self.batch_size = 200
        self.flush_interval = 5  # 5초마다 버퍼 비우기
        self.pending_ids = []  # ACK 대기 중인 메시지 ID

    def parse_time(self, time_str: str) -> datetime:
        """HHMMSS 형식의 시간 문자열을 datetime으로 변환"""
        today = datetime.now().date()
        hour = int(time_str[0:2])
        minute = int(time_str[2:4])
        second = int(time_str[4:6])
        return datetime(today.year, today.month, today.day, hour, minute, second)

    async def ensure_consumer_group(self, redis_client):
        """Consumer Group이 없으면 생성"""
        try:
            await redis_client.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="$", mkstream=True
            )
            print(f"[INIT] Created consumer group: {CONSUMER_GROUP}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                print(f"[INIT] Consumer group already exists: {CONSUMER_GROUP}")
            else:
                raise

    async def save_to_database(self, pool, redis_client):
        if not self.buffer:
            return

        async with self.lock:
            current_batch = self.buffer
            current_ids = self.pending_ids.copy()
            self.buffer = []
            self.pending_ids = []

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

                    # 저장 성공 시 ACK
                    if current_ids:
                        await redis_client.xack(
                            STREAM_KEY, CONSUMER_GROUP, *current_ids
                        )
                        print(f"[ACK] Acknowledged {len(current_ids)} messages")
                else:
                    print("[DB] No valid records to save (missing stock_code)")
                    # 유효하지 않은 레코드도 ACK (재처리 방지)
                    if current_ids:
                        await redis_client.xack(
                            STREAM_KEY, CONSUMER_GROUP, *current_ids
                        )

        except Exception as e:
            print(f"[ERROR] Error saving to database: {e}")
            # 실패 시 버퍼 복구 (ACK하지 않음 → 재처리 가능)
            async with self.lock:
                self.buffer = current_batch + self.buffer
                self.pending_ids = current_ids + self.pending_ids
            print(f"[BUFFER] Restored: {len(self.buffer)} rows (will retry)")

    async def process_pending_messages(self, redis_client, pool):
        """시작 시 처리되지 않은 PENDING 메시지 처리"""
        try:
            pending_info = await redis_client.xpending(STREAM_KEY, CONSUMER_GROUP)
            pending_count = pending_info.get("pending", 0) if pending_info else 0

            if pending_count > 0:
                print(
                    f"[PENDING] Found {pending_count} pending messages. Processing..."
                )

                # PENDING 메시지 조회 (최대 1000개씩)
                pending_messages = await redis_client.xpending_range(
                    STREAM_KEY, CONSUMER_GROUP, min="-", max="+", count=1000
                )

                for msg_info in pending_messages:
                    msg_id = msg_info.get("message_id")
                    if msg_id:
                        # XCLAIM으로 메시지 가져오기
                        claimed = await redis_client.xclaim(
                            STREAM_KEY,
                            CONSUMER_GROUP,
                            CONSUMER_NAME,
                            min_idle_time=0,
                            message_ids=[msg_id],
                        )
                        for entry_id, fields in claimed:
                            await self._process_entry(entry_id, fields)

                # 버퍼에 있는 것들 저장
                await self.save_to_database(pool, redis_client)
                print(f"[PENDING] Processed pending messages")

        except Exception as e:
            print(f"[ERROR] Error processing pending messages: {e}")

    async def _process_entry(self, entry_id, fields):
        """단일 Stream Entry 처리"""
        # bytes → str 변환
        data = {}
        for k, v in fields.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else k
            val = v.decode("utf-8") if isinstance(v, bytes) else v
            data[key] = val

        async with self.lock:
            self.buffer.append(data)
            self.pending_ids.append(entry_id)

    async def run(self):
        print(f"[INIT] Starting PersistenceWorker (Redis Streams mode)...")
        print(
            f"[INIT] Stream: {STREAM_KEY}, Group: {CONSUMER_GROUP}, Consumer: {CONSUMER_NAME}"
        )
        print(f"[INIT] REDIS_URL: {REDIS_URL}")
        masked_url = re.sub(r"://[^:]+:[^@]+@", "://***:***@", DATABASE_URL)
        print(f"[INIT] DATABASE_URL: {masked_url}")

        try:
            # Redis 연결
            print("[INIT] Connecting to Redis...")
            redis_client = redis.from_url(REDIS_URL)
            await redis_client.ping()
            print(f"[INIT] Redis connected")

            # Consumer Group 생성/확인
            await self.ensure_consumer_group(redis_client)

            # Database Connection Pool
            print("[INIT] Creating database connection pool...")
            pool = await asyncpg.create_pool(dsn=DATABASE_URL)
            print("[INIT] Database pool created")

            # PENDING 메시지 먼저 처리
            await self.process_pending_messages(redis_client, pool)

            # 주기적 flush 태스크
            asyncio.create_task(self.auto_flush(pool, redis_client))
            print("[INIT] Listening for stream messages...")

            message_count = 0
            while True:
                try:
                    # XREADGROUP: 새 메시지 읽기 (블로킹)
                    messages = await redis_client.xreadgroup(
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        {STREAM_KEY: ">"},  # ">" = 아직 전달되지 않은 새 메시지
                        count=200,
                        block=2000,  # 2초 대기
                    )

                    if messages:
                        for stream_name, entries in messages:
                            for entry_id, fields in entries:
                                message_count += 1
                                await self._process_entry(entry_id, fields)

                                if message_count % 50 == 0:
                                    print(
                                        f"[RECV] Processed {message_count} messages, buffer={len(self.buffer)}"
                                    )

                        # 배치 크기 도달 시 즉시 저장
                        if len(self.buffer) >= self.batch_size:
                            await self.save_to_database(pool, redis_client)

                except redis.ConnectionError as e:
                    print(f"[ERROR] Redis connection error: {e}. Reconnecting...")
                    await asyncio.sleep(5)
                    redis_client = redis.from_url(REDIS_URL)

        except Exception as e:
            print(f"[FATAL] Error in run(): {e}")
            import traceback

            traceback.print_exc()
            raise

    async def auto_flush(self, pool, redis_client):
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.save_to_database(pool, redis_client)


if __name__ == "__main__":
    try:
        worker = PersistenceWorker()
        asyncio.run(worker.run())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()
        raise
