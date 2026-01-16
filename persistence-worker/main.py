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

        페이징을 통해 모든 PENDING 메시지를 조회하고,
        min_idle_time을 설정하여 즉시 스틸을 방지하며,
        배치 단위로 처리하여 효율성을 높입니다.
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
            last_id = "-"
            total_processed = 0

            # 페이징을 통해 모든 PENDING 메시지 처리
            while True:
                # XPENDING RANGE로 배치 조회
                pending_messages = await redis_client.xpending_range(
                    STREAM_KEY,
                    CONSUMER_GROUP,
                    min=last_id,
                    max="+",
                    count=batch_size,
                )

                if not pending_messages:
                    break

                # 메시지 ID 수집
                message_ids = []
                for msg_info in pending_messages:
                    msg_id = msg_info.get("message_id")
                    if msg_id:
                        message_ids.append(msg_id)

                if not message_ids:
                    # 더 이상 처리할 메시지가 없으면 종료
                    break

                # XCLAIM으로 메시지 클레임 (min_idle_time 적용)
                claimed = await redis_client.xclaim(
                    STREAM_KEY,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    min_idle_time=min_idle_time_ms,
                    message_ids=message_ids,
                )

                # 클레임된 메시지 처리
                for entry_id, fields in claimed:
                    await self._process_entry(entry_id, fields)
                    total_processed += 1

                # 마지막 메시지 ID를 다음 페이징 시작점으로 사용 (exclusive pagination)
                if pending_messages:
                    last_message_id = pending_messages[-1].get("message_id")
                    if last_message_id:
                        # 메시지 ID를 증가시켜 exclusive start로 사용
                        # Redis Stream ID 형식: "timestamp-sequence"
                        try:
                            parts = last_message_id.split("-")
                            if len(parts) == 2:
                                timestamp = int(parts[0])
                                sequence = int(parts[1])
                                # 시퀀스 번호 증가 (exclusive start)
                                last_id = f"{timestamp}-{sequence + 1}"
                            else:
                                # 예상치 못한 형식이면 그대로 사용
                                last_id = last_message_id
                        except (ValueError, AttributeError):
                            # 파싱 실패 시 그대로 사용
                            last_id = last_message_id
                    else:
                        break
                else:
                    break

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
                    # flush 태스크 취소 및 정리
                    if self._flush_task:
                        self._flush_task.cancel()
                        try:
                            await self._flush_task
                        except asyncio.CancelledError:
                            pass
                        self._flush_task = None
                    await asyncio.sleep(5)
                    redis_client = redis.from_url(REDIS_URL)
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
