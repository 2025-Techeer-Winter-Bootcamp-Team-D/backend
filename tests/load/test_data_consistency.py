"""
데이터 일관성 검증 테스트

발행된 메시지와 데이터베이스에 저장된 데이터의 일치 여부를 검증합니다.
- 데이터 손실 확인
- 데이터 중복 확인
- 필드 일치 확인
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

import aio_pika
import asyncpg
from aio_pika import DeliveryMode, ExchangeType

# 환경변수
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)


@dataclass
class ConsistencyMetrics:
    """데이터 일관성 메트릭"""

    total_published: int = 0
    total_stored: int = 0
    total_matched: int = 0
    total_missing: int = 0
    total_duplicates: int = 0
    field_mismatches: list = field(default_factory=list)
    missing_sequences: list = field(default_factory=list)

    @property
    def loss_rate(self) -> float:
        if self.total_published == 0:
            return 0.0
        return (self.total_missing / self.total_published) * 100

    @property
    def match_rate(self) -> float:
        if self.total_published == 0:
            return 0.0
        return (self.total_matched / self.total_published) * 100


async def create_test_table(pool: asyncpg.Pool, table_name: str):
    """테스트용 테이블 생성"""
    await pool.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL,
            stock_code VARCHAR(10) NOT NULL,
            symbol VARCHAR(20),
            time TIMESTAMPTZ NOT NULL,
            price DECIMAL(15, 2) NOT NULL,
            volume BIGINT NOT NULL,
            test_batch_id UUID NOT NULL,
            test_seq INTEGER NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (stock_code, time, test_batch_id)
        )
    """
    )

    # 인덱스 생성
    await pool.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_batch
        ON {table_name} (test_batch_id)
    """
    )


async def drop_test_table(pool: asyncpg.Pool, table_name: str):
    """테스트 테이블 삭제"""
    await pool.execute(f"DROP TABLE IF EXISTS {table_name}")


async def test_data_consistency(
    rabbitmq_url: str = RABBITMQ_URL,
    database_url: str = DATABASE_URL,
    message_count: int = 1000,
    batch_size: int = 100,
) -> ConsistencyMetrics:
    """
    시나리오 3: 데이터 일관성 종합 테스트

    1. 테스트 테이블 생성
    2. 고유 batch_id로 메시지 발행
    3. Consumer로 데이터베이스 저장
    4. 발행 데이터와 저장 데이터 비교
    """
    metrics = ConsistencyMetrics()
    batch_id = uuid.uuid4()
    table_name = "stock_ticks_test"

    print(f"[TEST] 배치 ID: {batch_id}")
    print(f"[TEST] 메시지 수: {message_count}, 배치 크기: {batch_size}")

    # 발행된 데이터 추적
    published_data: dict[int, dict] = {}

    # DB 연결
    db_pool = await asyncpg.create_pool(database_url, min_size=5, max_size=10)

    try:
        # 테스트 테이블 생성
        await create_test_table(db_pool, table_name)

        # RabbitMQ 연결
        rmq_connection = await aio_pika.connect_robust(rabbitmq_url)

        try:
            channel = await rmq_connection.channel(publisher_confirms=True)
            await channel.set_qos(prefetch_count=batch_size)

            exchange = await channel.declare_exchange(
                "test.consistency", ExchangeType.FANOUT, durable=True
            )

            queue = await channel.declare_queue(
                "test.consistency.queue", durable=True
            )
            await queue.bind(exchange)

            # ===== 1단계: 메시지 발행 =====
            print("\n[1/4] 메시지 발행...")

            base_time = datetime.now()

            for seq in range(message_count):
                stock_code = f"00{seq % 10:04d}"
                msg_time = base_time + timedelta(milliseconds=seq)

                data = {
                    "stock_code": stock_code,
                    "symbol": f"KR{stock_code}",
                    "time": msg_time.strftime("%H%M%S%f")[:9],  # HHMMSSmmm
                    "price": float(50000 + (seq % 1000)),
                    "volume": 100 + (seq % 500),
                    "test_batch_id": str(batch_id),
                    "test_seq": seq,
                }

                published_data[seq] = {**data, "time_dt": msg_time}

                message = aio_pika.Message(
                    body=json.dumps(data).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                )

                await exchange.publish(message, routing_key="")
                metrics.total_published += 1

                if (seq + 1) % 200 == 0:
                    print(f"  발행: {seq + 1}/{message_count}")

            print(f"  발행 완료: {metrics.total_published}개")

            # ===== 2단계: 메시지 소비 및 저장 =====
            print("\n[2/4] 메시지 소비 및 저장...")

            buffer: list[dict] = []
            stored_count = 0

            async def save_batch():
                nonlocal stored_count
                if not buffer:
                    return

                async with db_pool.acquire() as conn:
                    await conn.executemany(
                        f"""
                        INSERT INTO {table_name}
                        (stock_code, symbol, time, price, volume, test_batch_id, test_seq)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (stock_code, time, test_batch_id) DO UPDATE SET
                            price = EXCLUDED.price,
                            volume = EXCLUDED.volume
                        """,
                        [
                            (
                                d["stock_code"],
                                d["symbol"],
                                d["time_dt"],
                                Decimal(str(d["price"])),
                                d["volume"],
                                uuid.UUID(d["test_batch_id"]),
                                d["test_seq"],
                            )
                            for d in buffer
                        ],
                    )

                stored_count += len(buffer)
                buffer.clear()

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        data = json.loads(message.body)

                        # 시간 파싱
                        time_str = data["time"]
                        hour = int(time_str[:2])
                        minute = int(time_str[2:4])
                        second = int(time_str[4:6])
                        microsecond = (
                            int(time_str[6:]) * 1000 if len(time_str) > 6 else 0
                        )

                        data["time_dt"] = base_time.replace(
                            hour=hour,
                            minute=minute,
                            second=second,
                            microsecond=microsecond,
                        )

                        buffer.append(data)

                        if len(buffer) >= batch_size:
                            await save_batch()
                            print(f"  저장: {stored_count}/{message_count}")

                        if stored_count + len(buffer) >= message_count:
                            break

            # 남은 버퍼 저장
            await save_batch()

            metrics.total_stored = stored_count
            print(f"  저장 완료: {stored_count}개")

            # ===== 3단계: 데이터 검증 =====
            print("\n[3/4] 데이터 검증...")

            async with db_pool.acquire() as conn:
                # 저장된 데이터 조회
                rows = await conn.fetch(
                    f"""
                    SELECT stock_code, symbol, time, price, volume, test_seq
                    FROM {table_name}
                    WHERE test_batch_id = $1
                    ORDER BY test_seq
                    """,
                    batch_id,
                )

            stored_data: dict[int, dict] = {}
            for row in rows:
                seq = row["test_seq"]
                if seq in stored_data:
                    metrics.total_duplicates += 1
                stored_data[seq] = dict(row)

            # 비교
            for seq, pub_data in published_data.items():
                if seq not in stored_data:
                    metrics.total_missing += 1
                    metrics.missing_sequences.append(seq)
                    continue

                stored = stored_data[seq]
                matched = True

                # 필드 비교
                if pub_data["stock_code"] != stored["stock_code"]:
                    matched = False
                    metrics.field_mismatches.append(
                        {
                            "seq": seq,
                            "field": "stock_code",
                            "expected": pub_data["stock_code"],
                            "actual": stored["stock_code"],
                        }
                    )

                if abs(float(pub_data["price"]) - float(stored["price"])) > 0.01:
                    matched = False
                    metrics.field_mismatches.append(
                        {
                            "seq": seq,
                            "field": "price",
                            "expected": pub_data["price"],
                            "actual": float(stored["price"]),
                        }
                    )

                if pub_data["volume"] != stored["volume"]:
                    matched = False
                    metrics.field_mismatches.append(
                        {
                            "seq": seq,
                            "field": "volume",
                            "expected": pub_data["volume"],
                            "actual": stored["volume"],
                        }
                    )

                if matched:
                    metrics.total_matched += 1

            print("  검증 완료")

            # ===== 4단계: 결과 출력 =====
            print("\n[4/4] 결과 분석...")
            print(f"  발행: {metrics.total_published}개")
            print(f"  저장: {metrics.total_stored}개")
            print(f"  일치: {metrics.total_matched}개 ({metrics.match_rate:.1f}%)")
            print(f"  누락: {metrics.total_missing}개 ({metrics.loss_rate:.1f}%)")
            print(f"  중복: {metrics.total_duplicates}개")
            print(f"  필드 불일치: {len(metrics.field_mismatches)}건")

            if metrics.missing_sequences and len(metrics.missing_sequences) <= 10:
                print(f"  누락 시퀀스: {metrics.missing_sequences}")

            if metrics.field_mismatches and len(metrics.field_mismatches) <= 5:
                print("  불일치 샘플:")
                for m in metrics.field_mismatches[:5]:
                    print(
                        f"    seq={m['seq']}, {m['field']}: "
                        f"{m['expected']} → {m['actual']}"
                    )

            # 정리
            await queue.delete(if_empty=False, if_unused=False)
            await exchange.delete(if_unused=False)

        finally:
            await rmq_connection.close()

        # 테스트 테이블 삭제
        await drop_test_table(db_pool, table_name)

    finally:
        await db_pool.close()

    return metrics


async def run_data_consistency_tests():
    """데이터 일관성 테스트 실행"""
    print("=" * 60)
    print("데이터 일관성 검증 테스트")
    print("=" * 60)

    metrics = await test_data_consistency(message_count=1000, batch_size=100)

    # 종합 결과
    print("\n" + "=" * 60)
    print("테스트 종합 결과")
    print("=" * 60)

    all_passed = (
        metrics.loss_rate == 0
        and metrics.total_duplicates == 0
        and len(metrics.field_mismatches) == 0
    )

    print(f"  손실률 (0%): {'PASS' if metrics.loss_rate == 0 else 'FAIL'}")
    print(f"  중복 (0개): {'PASS' if metrics.total_duplicates == 0 else 'FAIL'}")
    print(
        f"  필드 일치 (100%): {'PASS' if len(metrics.field_mismatches) == 0 else 'FAIL'}"
    )
    print(f"\n  최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_data_consistency_tests())
