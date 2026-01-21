import asyncio
import os
import redis.asyncio as redis
import asyncpg
import re
from datetime import datetime

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

if REDIS_PASSWORD:
    import urllib.parse
    encoded_pwd = urllib.parse.quote(REDIS_PASSWORD)
    REDIS_URL = f"redis://:{encoded_pwd}@{REDIS_HOST}:{REDIS_PORT}/0"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
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
        self._flush_task = None  # auto_flush 태스크 저장용

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
        """
        시작 시 처리되지 않은 PENDING 메시지 처리

        XAUTOCLAIM을 사용하여 idle time이 충분한 메시지만 안전하게 클레임하고,
        cursor 기반 pagination으로 모든 메시지를 처리합니다.
        """
        try:
            pending_info = await redis_client.xpending(STREAM_KEY, CONSUMER_GROUP)
            pending_count = pending_info.get("pending", 0) if pending_info else 0

            if pending_count == 0:
                return

            print(f"[PENDING] Found {pending_count} pending messages. Processing...")

            # 안전한 min_idle_time 설정 (5초 이상 idle인 메시지만 클레임)
            # 즉시 스틸 방지 및 메시지 누락 방지
            min_idle_time_ms = 5000  # 5초 (밀리초)
            batch_size = 100
            start_id = "0-0"  # XAUTOCLAIM 시작 ID
            total_processed = 0

            # XAUTOCLAIM을 사용하여 cursor 기반 pagination으로 모든 PENDING 메시지 처리
            while True:
                # XAUTOCLAIM: idle time이 충분한 메시지만 자동으로 클레임하고 반환
                # 반환값: (next_id, claimed_entries)
                next_id, claimed = await redis_client.xautoclaim(
                    STREAM_KEY,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    min_idle_time=min_idle_time_ms,
                    start_id=start_id,
                    count=batch_size,
                )

                # 클레임된 메시지 처리
                if claimed:
                    for entry_id, fields in claimed:
                        await self._process_entry(entry_id, fields)
                        total_processed += 1

                # cursor가 "0-0"이면 더 이상 처리할 메시지가 없음
                if next_id == "0-0":
                    break

                # 다음 iteration을 위한 start_id 업데이트
                start_id = next_id

                # 배치 처리 후 버퍼 저장 (메모리 관리)
                if len(self.buffer) >= self.batch_size:
                    await self.save_to_database(pool, redis_client)

            # 남은 버퍼 저장
            if self.buffer:
                await self.save_to_database(pool, redis_client)

            print(f"[PENDING] Processed {total_processed} pending messages")

        except Exception as e:
            print(f"[ERROR] Error processing pending messages: {e}")
            import traceback

            traceback.print_exc()

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
        print("[INIT] Starting PersistenceWorker (Redis Streams mode)...")
        print(
            f"[INIT] Stream: {STREAM_KEY}, Group: {CONSUMER_GROUP}, Consumer: {CONSUMER_NAME}"
        )
        print(f"[INIT] REDIS_URL: {REDIS_URL}")
        masked_url = re.sub(r"://[^:]+:[^@]+@", "://***:***@", DATABASE_URL)
        print(f"[INIT] DATABASE_URL: {masked_url}")

        try:
            # Redis 연결
            print("[INIT] Connecting to Redis...")
            redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=0)
            await redis_client.ping()
            print("[INIT] Redis connected")

            # Consumer Group 생성/확인
            await self.ensure_consumer_group(redis_client)

            # Database Connection Pool
            print("[INIT] Creating database connection pool...")
            pool = await asyncpg.create_pool(dsn=DATABASE_URL)
            print("[INIT] Database pool created")

            # PENDING 메시지 먼저 처리
            await self.process_pending_messages(redis_client, pool)

            # 주기적 flush 태스크 생성 및 저장
            self._flush_task = asyncio.create_task(self.auto_flush(pool, redis_client))
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
                except redis.ResponseError as e:
                    # NOGROUP 에러 처리: Consumer Group이 없으면 재생성
                    if "NOGROUP" in str(e):
                        print(
                            f"[WARN] Consumer group not found, recreating: {CONSUMER_GROUP}"
                        )
                        await self.ensure_consumer_group(redis_client)
                        continue  # 재시도
                    else:
                        print(f"[ERROR] Redis response error: {e}")
                        await asyncio.sleep(5)
                        continue
                except Exception as e:
                    print(f"[ERROR] Error reading messages: {e}")
                    await asyncio.sleep(5)
                    continue
                try:

                    if messages:
                        for _stream_name, entries in messages:
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
                    # flush 태스크 취소 및 정리
                    if self._flush_task:
                        self._flush_task.cancel()
                        try:
                            await self._flush_task
                        except asyncio.CancelledError:
                            pass
                        self._flush_task = None
                    # 기존 Redis 연결 정리
                    if redis_client:
                        try:
                            await redis_client.close()
                        except Exception as close_error:
                            print(
                                f"[WARN] Error closing old Redis connection: {close_error}"
                            )
                    await asyncio.sleep(5)
                    # 새 Redis 연결 생성
                    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=0)
                    # Consumer Group 복원
                    await self.ensure_consumer_group(redis_client)
                    # flush 태스크 재생성
                    self._flush_task = asyncio.create_task(
                        self.auto_flush(pool, redis_client)
                    )

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
