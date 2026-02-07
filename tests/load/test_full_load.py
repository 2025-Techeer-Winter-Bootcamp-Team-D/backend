"""
종합 부하 테스트

실제 운영 환경과 유사한 부하에서 전체 시스템을 검증합니다.
- 다수 종목 동시 처리
- 고처리량 Publisher/Consumer
- E2E 지연 측정
"""

import asyncio
import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
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
class LoadTestMetrics:
    """부하 테스트 메트릭"""

    # Publisher
    total_published: int = 0
    publish_confirmed: int = 0
    publish_failed: int = 0
    publish_latencies: list = field(default_factory=list)

    # Consumer
    total_consumed: int = 0
    consume_latencies: list = field(default_factory=list)

    # Database
    total_stored: int = 0
    db_latencies: list = field(default_factory=list)

    # 시간 통계
    start_time: float = 0
    end_time: float = 0

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def publish_rate(self) -> float:
        if self.duration_seconds == 0:
            return 0
        return self.total_published / self.duration_seconds

    @property
    def consume_rate(self) -> float:
        if self.duration_seconds == 0:
            return 0
        return self.total_consumed / self.duration_seconds

    @property
    def avg_e2e_latency_ms(self) -> float:
        if not self.consume_latencies:
            return 0
        return sum(self.consume_latencies) / len(self.consume_latencies) * 1000

    @property
    def p99_e2e_latency_ms(self) -> float:
        if not self.consume_latencies:
            return 0
        sorted_latencies = sorted(self.consume_latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx] * 1000


# 테스트용 종목 코드 (시가총액 상위)
TEST_STOCK_CODES = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "373220",  # LG에너지솔루션
    "207940",  # 삼성바이오로직스
    "005380",  # 현대차
    "006400",  # 삼성SDI
    "051910",  # LG화학
    "035420",  # NAVER
    "000270",  # 기아
    "005490",  # POSCO홀딩스
    "035720",  # 카카오
    "068270",  # 셀트리온
    "028260",  # 삼성물산
    "012330",  # 현대모비스
    "105560",  # KB금융
    "055550",  # 신한지주
    "003670",  # 포스코퓨처엠
    "096770",  # SK이노베이션
    "066570",  # LG전자
    "034730",  # SK
    "032830",  # 삼성생명
    "086790",  # 하나금융지주
    "003550",  # LG
    "015760",  # 한국전력
    "017670",  # SK텔레콤
    "030200",  # KT
    "033780",  # KT&G
    "047050",  # 포스코인터내셔널
    "018260",  # 삼성에스디에스
    "009150",  # 삼성전기
    "010130",  # 고려아연
    "024110",  # 기업은행
    "326030",  # SK바이오팜
    "011200",  # HMM
    "010140",  # 삼성중공업
    "009540",  # 한국조선해양
    "000810",  # 삼성화재
    "036570",  # 엔씨소프트
    "259960",  # 크래프톤
    "352820",  # 하이브
]


async def run_full_load_test(
    rabbitmq_url: str = RABBITMQ_URL,
    database_url: str = DATABASE_URL,
    stock_count: int = 40,
    messages_per_second: int = 400,
    duration_seconds: int = 60,
    consumer_batch_size: int = 200,
) -> LoadTestMetrics:
    """
    시나리오 4: 종합 부하 테스트

    Args:
        stock_count: 동시 테스트 종목 수
        messages_per_second: 초당 발행 메시지 수
        duration_seconds: 테스트 지속 시간
        consumer_batch_size: Consumer 배치 크기
    """
    metrics = LoadTestMetrics()
    batch_id = uuid.uuid4()
    table_name = "stock_ticks_loadtest"

    total_messages = messages_per_second * duration_seconds

    print("=" * 60)
    print("종합 부하 테스트")
    print("=" * 60)
    print(f"배치 ID: {batch_id}")
    print(f"종목 수: {stock_count}")
    print(f"목표 처리량: {messages_per_second}/초")
    print(f"테스트 시간: {duration_seconds}초")
    print(f"총 메시지: {total_messages}개")
    print("=" * 60)

    # 테스트 종목 선택
    test_stocks = TEST_STOCK_CODES[:stock_count]

    # DB 연결
    db_pool = await asyncpg.create_pool(database_url, min_size=10, max_size=20)

    try:
        # 테스트 테이블 생성
        await db_pool.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                stock_code VARCHAR(10) NOT NULL,
                time TIMESTAMPTZ NOT NULL,
                price DECIMAL(15, 2) NOT NULL,
                volume BIGINT NOT NULL,
                test_batch_id UUID NOT NULL,
                test_seq INTEGER NOT NULL,
                publish_time DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (stock_code, time, test_batch_id, test_seq)
            )
        """
        )

        # RabbitMQ 연결
        rmq_connection = await aio_pika.connect_robust(rabbitmq_url)

        try:
            # Publisher 채널
            pub_channel = await rmq_connection.channel(publisher_confirms=True)

            exchange = await pub_channel.declare_exchange(
                "test.loadtest", ExchangeType.FANOUT, durable=True
            )

            queue = await pub_channel.declare_queue(
                "test.loadtest.queue",
                durable=True,
                arguments={"x-max-length": 1000000},
            )
            await queue.bind(exchange)

            # Consumer 채널
            con_channel = await rmq_connection.channel()
            await con_channel.set_qos(prefetch_count=consumer_batch_size)

            # 제어 플래그
            publishing_done = asyncio.Event()

            # ===== Producer Task =====
            async def producer():
                nonlocal metrics

                interval = 1.0 / messages_per_second
                metrics.start_time = time.time()

                print("\n[PRODUCER] 시작...")

                for seq in range(total_messages):
                    stock_code = test_stocks[seq % len(test_stocks)]
                    publish_time = time.time()

                    data = {
                        "stock_code": stock_code,
                        "time": datetime.now().strftime("%H%M%S%f")[:9],
                        "price": float(50000 + random.randint(-1000, 1000)),
                        "volume": random.randint(100, 10000),
                        "test_batch_id": str(batch_id),
                        "test_seq": seq,
                        "publish_time": publish_time,
                    }

                    message = aio_pika.Message(
                        body=json.dumps(data).encode(),
                        delivery_mode=DeliveryMode.PERSISTENT,
                    )

                    confirm_start = time.time()

                    try:
                        await exchange.publish(message, routing_key="")
                        metrics.publish_latencies.append(time.time() - confirm_start)
                        metrics.total_published += 1
                        metrics.publish_confirmed += 1

                    except Exception:
                        metrics.total_published += 1
                        metrics.publish_failed += 1

                    # 속도 조절
                    elapsed = time.time() - metrics.start_time
                    expected = (seq + 1) * interval
                    if elapsed < expected:
                        await asyncio.sleep(expected - elapsed)

                    # 10초마다 진행 상황
                    if (seq + 1) % (messages_per_second * 10) == 0:
                        current_rate = (seq + 1) / (time.time() - metrics.start_time)
                        print(
                            f"  [PUB] {(seq + 1) // messages_per_second}초: "
                            f"{current_rate:.0f}/초, "
                            f"확인율 "
                            f"{metrics.publish_confirmed / metrics.total_published * 100:.1f}%"
                        )

                publishing_done.set()
                print(f"[PRODUCER] 완료: {metrics.total_published}개 발행")

            # ===== Consumer Task =====
            async def consumer():
                nonlocal metrics

                buffer: list[tuple] = []

                async def save_batch():
                    if not buffer:
                        return

                    db_start = time.time()

                    async with db_pool.acquire() as conn:
                        await conn.executemany(
                            f"""
                            INSERT INTO {table_name}
                            (stock_code, time, price, volume, test_batch_id,
                             test_seq, publish_time)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT DO NOTHING
                            """,
                            buffer,
                        )

                    metrics.db_latencies.append(time.time() - db_start)
                    metrics.total_stored += len(buffer)
                    buffer.clear()

                print("\n[CONSUMER] 시작...")

                async with queue.iterator(no_ack=False) as queue_iter:
                    async for message in queue_iter:
                        consume_time = time.time()

                        async with message.process():
                            data = json.loads(message.body)

                            # E2E 지연 계산
                            publish_time = data.get("publish_time", consume_time)
                            metrics.consume_latencies.append(
                                consume_time - publish_time
                            )
                            metrics.total_consumed += 1

                            # 시간 파싱
                            time_str = data["time"]
                            msg_time = datetime.now().replace(
                                hour=int(time_str[:2]),
                                minute=int(time_str[2:4]),
                                second=int(time_str[4:6]),
                                microsecond=(
                                    int(time_str[6:]) * 1000 if len(time_str) > 6 else 0
                                ),
                            )

                            buffer.append(
                                (
                                    data["stock_code"],
                                    msg_time,
                                    Decimal(str(data["price"])),
                                    data["volume"],
                                    uuid.UUID(data["test_batch_id"]),
                                    data["test_seq"],
                                    publish_time,
                                )
                            )

                            if len(buffer) >= consumer_batch_size:
                                await save_batch()

                        # 10초마다 진행 상황
                        if metrics.total_consumed % (messages_per_second * 10) == 0:
                            print(
                                f"  [CON] 소비: {metrics.total_consumed}개, "
                                f"저장: {metrics.total_stored}개"
                            )

                        # 모든 메시지 처리 완료
                        if (
                            publishing_done.is_set()
                            and metrics.total_consumed >= metrics.total_published
                        ):
                            break

                # 남은 버퍼 저장
                await save_batch()

                metrics.end_time = time.time()

                print(
                    f"[CONSUMER] 완료: {metrics.total_consumed}개 소비, "
                    f"{metrics.total_stored}개 저장"
                )

            # ===== 병렬 실행 =====
            await asyncio.gather(producer(), consumer())

            # ===== 결과 분석 =====
            print("\n" + "=" * 60)
            print("테스트 결과")
            print("=" * 60)

            print("\n[시간]")
            print(f"  총 소요 시간: {metrics.duration_seconds:.2f}초")

            print("\n[Publisher]")
            print(f"  발행: {metrics.total_published}개")
            print(
                f"  확인: {metrics.publish_confirmed}개 "
                f"({metrics.publish_confirmed / metrics.total_published * 100:.1f}%)"
            )
            print(f"  실패: {metrics.publish_failed}개")
            print(f"  처리량: {metrics.publish_rate:.0f}/초")
            if metrics.publish_latencies:
                avg_lat = (
                    sum(metrics.publish_latencies)
                    / len(metrics.publish_latencies)
                    * 1000
                )
                print(f"  확인 지연 (평균): {avg_lat:.2f}ms")

            print("\n[Consumer]")
            print(f"  소비: {metrics.total_consumed}개")
            print(f"  저장: {metrics.total_stored}개")
            print(f"  처리량: {metrics.consume_rate:.0f}/초")
            print(f"  E2E 지연 (평균): {metrics.avg_e2e_latency_ms:.2f}ms")
            print(f"  E2E 지연 (P99): {metrics.p99_e2e_latency_ms:.2f}ms")

            if metrics.db_latencies:
                print("\n[Database]")
                print(f"  배치 저장 횟수: {len(metrics.db_latencies)}")
                avg_db = (
                    sum(metrics.db_latencies) / len(metrics.db_latencies) * 1000
                )
                print(f"  저장 지연 (평균): {avg_db:.2f}ms")

            # 검증
            print("\n[검증]")
            loss_count = metrics.total_published - metrics.total_consumed
            loss_rate = (
                loss_count / metrics.total_published * 100
                if metrics.total_published > 0
                else 0
            )
            print(f"  손실: {loss_count}개 ({loss_rate:.2f}%)")

            # 정리
            await queue.delete()
            await exchange.delete()

        finally:
            await rmq_connection.close()

        # 테스트 테이블 삭제
        await db_pool.execute(f"DROP TABLE IF EXISTS {table_name}")

    finally:
        await db_pool.close()

    return metrics


async def run_load_test_suite():
    """부하 테스트 스위트 실행"""

    # 테스트 1: 경량 부하 (1분)
    print("\n" + "=" * 70)
    print("테스트 1: 경량 부하 (100/초 × 60초)")
    print("=" * 70)

    metrics1 = await run_full_load_test(
        stock_count=10, messages_per_second=100, duration_seconds=60
    )

    # 테스트 2: 중간 부하 (1분)
    print("\n" + "=" * 70)
    print("테스트 2: 중간 부하 (300/초 × 60초)")
    print("=" * 70)

    metrics2 = await run_full_load_test(
        stock_count=30, messages_per_second=300, duration_seconds=60
    )

    # 테스트 3: 고부하 (30초)
    print("\n" + "=" * 70)
    print("테스트 3: 고부하 (500/초 × 30초)")
    print("=" * 70)

    metrics3 = await run_full_load_test(
        stock_count=40, messages_per_second=500, duration_seconds=30
    )

    # 종합 결과
    print("\n" + "=" * 70)
    print("종합 결과 요약")
    print("=" * 70)

    results = [
        ("경량 (100/초)", metrics1),
        ("중간 (300/초)", metrics2),
        ("고부하 (500/초)", metrics3),
    ]

    print(
        f"\n{'테스트':<15} {'발행':<10} {'소비':<10} {'손실률':<10} {'E2E P99':<12}"
    )
    print("-" * 60)

    for name, m in results:
        loss_rate = (m.total_published - m.total_consumed) / m.total_published * 100
        print(
            f"{name:<15} {m.total_published:<10} {m.total_consumed:<10} "
            f"{loss_rate:<10.2f}% {m.p99_e2e_latency_ms:<12.2f}ms"
        )

    # 합격 기준
    all_passed = all(
        (m.total_published - m.total_consumed) / m.total_published < 0.01
        and m.p99_e2e_latency_ms < 1000  # 손실률 < 1%  # P99 < 1초
        for _, m in results
    )

    print(f"\n최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_load_test_suite())
