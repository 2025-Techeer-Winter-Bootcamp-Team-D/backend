"""
Publisher Confirm 검증 테스트

RabbitMQ Publisher Confirms 기능이 올바르게 동작하는지 검증합니다.
- 기본 Confirm 동작
- 실패 감지 (mandatory 플래그)
- 부하 상황에서의 Confirm 지연
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.exceptions import DeliveryError

# 환경변수에서 RabbitMQ URL 읽기
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


@dataclass
class ConfirmMetrics:
    """Publisher Confirm 메트릭"""

    total_published: int = 0
    total_confirmed: int = 0
    total_failed: int = 0
    confirm_latencies: list = field(default_factory=list)
    failed_messages: list = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_published == 0:
            return 0.0
        return (self.total_confirmed / self.total_published) * 100

    @property
    def avg_latency_ms(self) -> float:
        if not self.confirm_latencies:
            return 0.0
        return sum(self.confirm_latencies) / len(self.confirm_latencies) * 1000

    @property
    def max_latency_ms(self) -> float:
        if not self.confirm_latencies:
            return 0.0
        return max(self.confirm_latencies) * 1000


def generate_stock_tick(stock_code: str, seq: int) -> dict:
    """테스트용 주가 데이터 생성"""
    return {
        "stock_code": stock_code,
        "symbol": f"KR{stock_code}",
        "time": datetime.now().strftime("%H%M%S"),
        "price": 50000 + (seq % 1000),
        "volume": 100 + (seq % 500),
        "test_seq": seq,
        "timestamp": time.time(),
    }


async def test_publisher_confirm_basic(
    rabbitmq_url: str = RABBITMQ_URL, message_count: int = 1000
) -> ConfirmMetrics:
    """
    시나리오 1-1: 기본 Publisher Confirm 테스트

    Args:
        rabbitmq_url: RabbitMQ 연결 URL
        message_count: 발행할 메시지 수

    Returns:
        ConfirmMetrics: 테스트 결과 메트릭
    """
    metrics = ConfirmMetrics()

    connection = await aio_pika.connect_robust(rabbitmq_url)

    try:
        # Publisher Confirms 활성화
        channel = await connection.channel(publisher_confirms=True)

        # Exchange 선언
        exchange = await channel.declare_exchange(
            "stock.realtime.test", ExchangeType.FANOUT, durable=True
        )

        # 임시 큐 생성 (메시지 라우팅 확인용)
        queue = await channel.declare_queue("", exclusive=True)
        await queue.bind(exchange)

        print(f"[TEST] {message_count}개 메시지 발행 시작...")

        for seq in range(message_count):
            stock_code = f"00{seq % 10:04d}"
            data = generate_stock_tick(stock_code, seq)

            message = aio_pika.Message(
                body=json.dumps(data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            )

            start_time = time.time()

            try:
                # mandatory=True: 라우팅 실패 시 예외 발생
                await exchange.publish(message, routing_key="", mandatory=True)

                latency = time.time() - start_time
                metrics.total_published += 1
                metrics.total_confirmed += 1
                metrics.confirm_latencies.append(latency)

            except DeliveryError as e:
                metrics.total_published += 1
                metrics.total_failed += 1
                metrics.failed_messages.append({"seq": seq, "error": str(e)})

            # 진행 상황 출력
            if (seq + 1) % 100 == 0:
                print(
                    f"  진행: {seq + 1}/{message_count} "
                    f"(성공률: {metrics.success_rate:.1f}%)"
                )

        # 큐 정리 (메시지가 남아있어도 삭제)
        await queue.delete(if_empty=False, if_unused=False)
        await exchange.delete(if_unused=False)

    finally:
        await connection.close()

    return metrics


async def test_publisher_confirm_failure(
    rabbitmq_url: str = RABBITMQ_URL,
) -> dict:
    """
    시나리오 1-2: Publisher Confirm 실패 케이스 테스트

    존재하지 않는 Exchange로 발행 시 실패 감지 확인
    """
    connection = await aio_pika.connect_robust(rabbitmq_url)
    result = {
        "test_name": "publisher_confirm_failure",
        "failure_detected": False,
        "error_type": None,
        "error_message": None,
    }

    try:
        channel = await connection.channel(publisher_confirms=True)

        # 존재하지 않는 Exchange 사용
        exchange = await channel.declare_exchange(
            "nonexistent.exchange", ExchangeType.FANOUT, durable=False, auto_delete=True
        )

        # 바인딩 없이 mandatory=True로 발행 → 실패 예상
        message = aio_pika.Message(
            body=b'{"test": "failure"}', delivery_mode=DeliveryMode.PERSISTENT
        )

        try:
            await exchange.publish(
                message, routing_key="nonexistent.key", mandatory=True
            )
            # 실패가 감지되지 않음 (문제)
            result["failure_detected"] = False

        except DeliveryError as e:
            # 실패가 정상 감지됨
            result["failure_detected"] = True
            result["error_type"] = "DeliveryError"
            result["error_message"] = str(e)

        except Exception as e:
            result["failure_detected"] = True
            result["error_type"] = type(e).__name__
            result["error_message"] = str(e)

        await exchange.delete(if_unused=False)

    finally:
        await connection.close()

    return result


async def test_publisher_confirm_under_load(
    rabbitmq_url: str = RABBITMQ_URL,
    messages_per_second: int = 1000,
    duration_seconds: int = 10,
) -> ConfirmMetrics:
    """
    시나리오 1-3: 부하 상황에서의 Publisher Confirm 테스트

    Args:
        messages_per_second: 초당 발행할 메시지 수
        duration_seconds: 테스트 지속 시간 (초)
    """
    metrics = ConfirmMetrics()

    connection = await aio_pika.connect_robust(rabbitmq_url)

    try:
        channel = await connection.channel(publisher_confirms=True)

        exchange = await channel.declare_exchange(
            "stock.realtime.loadtest", ExchangeType.FANOUT, durable=True
        )

        queue = await channel.declare_queue("loadtest.sink", durable=True)
        await queue.bind(exchange)

        total_messages = messages_per_second * duration_seconds
        interval = 1.0 / messages_per_second

        print(
            f"[LOAD TEST] {messages_per_second}/초 × {duration_seconds}초 "
            f"= {total_messages}개 메시지"
        )

        start_time = time.time()

        for seq in range(total_messages):
            stock_code = f"00{seq % 100:04d}"
            data = generate_stock_tick(stock_code, seq)

            message = aio_pika.Message(
                body=json.dumps(data).encode(), delivery_mode=DeliveryMode.PERSISTENT
            )

            confirm_start = time.time()

            try:
                await exchange.publish(message, routing_key="")
                latency = time.time() - confirm_start
                metrics.total_published += 1
                metrics.total_confirmed += 1
                metrics.confirm_latencies.append(latency)

            except DeliveryError:
                metrics.total_published += 1
                metrics.total_failed += 1

            # 속도 조절
            elapsed = time.time() - start_time
            expected_elapsed = (seq + 1) * interval
            if elapsed < expected_elapsed:
                await asyncio.sleep(expected_elapsed - elapsed)

            # 초당 진행 상황
            if (seq + 1) % messages_per_second == 0:
                current_rate = (seq + 1) / (time.time() - start_time)
                print(
                    f"  {(seq + 1) // messages_per_second}초 경과: "
                    f"실제 처리량 {current_rate:.0f}/초, "
                    f"평균 지연 {metrics.avg_latency_ms:.2f}ms"
                )

        total_time = time.time() - start_time
        print(
            f"[완료] 총 {total_time:.2f}초 소요, "
            f"처리량: {total_messages / total_time:.0f}/초"
        )

        # 정리
        await queue.delete(if_empty=False, if_unused=False)
        await exchange.delete(if_unused=False)

    finally:
        await connection.close()

    return metrics


async def run_publisher_confirm_tests():
    """모든 Publisher Confirm 테스트 실행"""
    print("=" * 60)
    print("Publisher Confirm 검증 테스트")
    print("=" * 60)

    # 테스트 1: 기본 확인
    print("\n[1/3] 기본 Publisher Confirm 테스트")
    metrics1 = await test_publisher_confirm_basic(message_count=1000)
    print(
        f"  결과: 성공률 {metrics1.success_rate:.1f}%, "
        f"평균 지연 {metrics1.avg_latency_ms:.2f}ms, "
        f"최대 지연 {metrics1.max_latency_ms:.2f}ms"
    )

    # 테스트 2: 실패 감지
    print("\n[2/3] 실패 감지 테스트")
    result2 = await test_publisher_confirm_failure()
    print(f"  실패 감지: {'성공' if result2['failure_detected'] else '실패'}")
    if result2["failure_detected"]:
        print(f"  에러 타입: {result2['error_type']}")

    # 테스트 3: 부하 테스트
    print("\n[3/3] 부하 상황 테스트 (500/초 × 10초)")
    metrics3 = await test_publisher_confirm_under_load(
        messages_per_second=500, duration_seconds=10
    )
    print(
        f"  결과: 성공률 {metrics3.success_rate:.1f}%, "
        f"평균 지연 {metrics3.avg_latency_ms:.2f}ms, "
        f"최대 지연 {metrics3.max_latency_ms:.2f}ms"
    )

    # 종합 결과
    print("\n" + "=" * 60)
    print("테스트 종합 결과")
    print("=" * 60)

    all_passed = (
        metrics1.success_rate == 100
        and result2["failure_detected"]
        and metrics3.success_rate == 100
        and metrics3.avg_latency_ms < 10
        and metrics3.max_latency_ms < 100
    )

    print(f"  기본 테스트: {'PASS' if metrics1.success_rate == 100 else 'FAIL'}")
    print(f"  실패 감지: {'PASS' if result2['failure_detected'] else 'FAIL'}")
    print(f"  부하 성공률: {'PASS' if metrics3.success_rate == 100 else 'FAIL'}")
    print(
        f"  부하 평균지연 (<10ms): {'PASS' if metrics3.avg_latency_ms < 10 else 'FAIL'}"
    )
    print(
        f"  부하 최대지연 (<100ms): {'PASS' if metrics3.max_latency_ms < 100 else 'FAIL'}"
    )
    print(f"\n  최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_publisher_confirm_tests())
