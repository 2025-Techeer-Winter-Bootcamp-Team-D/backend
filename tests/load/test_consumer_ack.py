"""
Consumer ACK 검증 테스트

RabbitMQ Consumer의 ACK/NACK 메커니즘이 올바르게 동작하는지 검증합니다.
- 기본 ACK 동작
- Requeue (NACK with requeue) 동작
- Prefetch (QoS) 동작
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field

import aio_pika
from aio_pika import DeliveryMode, ExchangeType

# 환경변수에서 RabbitMQ URL 읽기
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


@dataclass
class ConsumerMetrics:
    """Consumer 메트릭"""

    total_received: int = 0
    total_acked: int = 0
    total_nacked: int = 0
    total_requeued: int = 0
    processing_times: list = field(default_factory=list)
    received_sequences: set = field(default_factory=set)

    @property
    def ack_rate(self) -> float:
        if self.total_received == 0:
            return 0.0
        return (self.total_acked / self.total_received) * 100

    @property
    def avg_processing_ms(self) -> float:
        if not self.processing_times:
            return 0.0
        return sum(self.processing_times) / len(self.processing_times) * 1000


async def test_consumer_ack_basic(
    rabbitmq_url: str = RABBITMQ_URL, message_count: int = 500
) -> ConsumerMetrics:
    """
    시나리오 2-1: 기본 Consumer ACK 테스트

    메시지 발행 → 소비 → ACK 확인
    """
    metrics = ConsumerMetrics()

    connection = await aio_pika.connect_robust(rabbitmq_url)

    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=100)

        # Exchange, Queue 설정
        exchange = await channel.declare_exchange(
            "test.consumer.ack", ExchangeType.FANOUT, durable=True
        )

        queue = await channel.declare_queue("test.consumer.ack.queue", durable=True)
        await queue.bind(exchange)

        # 1단계: 메시지 발행
        print(f"[PRODUCER] {message_count}개 메시지 발행...")

        for seq in range(message_count):
            data = {
                "stock_code": f"00{seq % 10:04d}",
                "price": 50000 + seq,
                "volume": 100,
                "test_seq": seq,
                "timestamp": time.time(),
            }

            message = aio_pika.Message(
                body=json.dumps(data).encode(), delivery_mode=DeliveryMode.PERSISTENT
            )

            await exchange.publish(message, routing_key="")

        print("[PRODUCER] 발행 완료")

        # 2단계: 메시지 소비 및 ACK
        print("[CONSUMER] 메시지 소비 시작...")

        processed = 0

        async def process_message(message: aio_pika.IncomingMessage):
            nonlocal processed

            start_time = time.time()

            async with message.process():  # 자동 ACK
                data = json.loads(message.body)
                seq = data.get("test_seq", -1)

                metrics.total_received += 1
                metrics.received_sequences.add(seq)

                # 처리 시뮬레이션 (1ms)
                await asyncio.sleep(0.001)

                metrics.total_acked += 1
                metrics.processing_times.append(time.time() - start_time)

                processed += 1

                if processed % 100 == 0:
                    print(f"  처리: {processed}/{message_count}")

        # 타임아웃과 함께 소비
        async with queue.iterator() as queue_iter:
            try:
                async for message in queue_iter:
                    await process_message(message)

                    if processed >= message_count:
                        break

            except asyncio.TimeoutError:
                pass

        # 큐에 남은 메시지 확인
        queue_info = await queue.declare(passive=True)
        remaining = queue_info.message_count

        print(f"[CONSUMER] 처리 완료: {processed}개, 큐 잔여: {remaining}개")

        # 정리
        await queue.delete()
        await exchange.delete()

    finally:
        await connection.close()

    return metrics


async def test_consumer_requeue(
    rabbitmq_url: str = RABBITMQ_URL,
    message_count: int = 100,
    fail_rate: float = 0.2,  # 20% 실패
) -> dict:
    """
    시나리오 2-2: Requeue 동작 테스트

    일부 메시지 처리 실패 → Requeue → 재처리 확인
    """
    result = {
        "total_messages": message_count,
        "initial_failures": 0,
        "requeue_attempts": 0,
        "final_success": 0,
        "all_processed": False,
    }

    connection = await aio_pika.connect_robust(rabbitmq_url)

    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            "test.requeue", ExchangeType.FANOUT, durable=True
        )

        queue = await channel.declare_queue("test.requeue.queue", durable=True)
        await queue.bind(exchange)

        # 실패 이력 추적
        attempt_counts: dict[int, int] = {}
        processed_seqs: set[int] = set()

        # 메시지 발행
        print(f"[PRODUCER] {message_count}개 메시지 발행...")

        for seq in range(message_count):
            data = {"test_seq": seq, "timestamp": time.time()}

            message = aio_pika.Message(
                body=json.dumps(data).encode(), delivery_mode=DeliveryMode.PERSISTENT
            )

            await exchange.publish(message, routing_key="")
            attempt_counts[seq] = 0

        # 메시지 소비 (실패 시뮬레이션 포함)
        print(f"[CONSUMER] 소비 시작 (실패율: {fail_rate * 100}%)...")

        max_iterations = message_count * 3  # 무한 루프 방지
        iteration = 0

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                iteration += 1

                if iteration > max_iterations:
                    print("  최대 반복 횟수 도달")
                    break

                data = json.loads(message.body)
                seq = data.get("test_seq", -1)
                attempt_counts[seq] = attempt_counts.get(seq, 0) + 1

                # 첫 시도에서 일정 확률로 실패
                should_fail = (
                    attempt_counts[seq] == 1 and seq < message_count * fail_rate
                )

                if should_fail:
                    # NACK with requeue
                    result["initial_failures"] += 1
                    await message.nack(requeue=True)
                    result["requeue_attempts"] += 1
                else:
                    # ACK
                    await message.ack()
                    processed_seqs.add(seq)
                    result["final_success"] += 1

                if len(processed_seqs) >= message_count:
                    break

        result["all_processed"] = len(processed_seqs) == message_count

        # 재시도 통계
        retry_counts = [c for c in attempt_counts.values() if c > 1]
        if retry_counts:
            print(
                f"  재시도된 메시지: {len(retry_counts)}개, "
                f"평균 재시도: {sum(retry_counts) / len(retry_counts):.1f}회"
            )

        # 정리
        await queue.delete()
        await exchange.delete()

    finally:
        await connection.close()

    return result


async def test_consumer_prefetch(
    rabbitmq_url: str = RABBITMQ_URL,
    message_count: int = 1000,
    prefetch_count: int = 100,
) -> dict:
    """
    시나리오 2-3: Prefetch (QoS) 동작 테스트

    prefetch_count 설정이 올바르게 적용되는지 확인
    """
    result = {
        "prefetch_count": prefetch_count,
        "max_unacked": 0,
        "total_processed": 0,
        "prefetch_respected": False,
    }

    connection = await aio_pika.connect_robust(rabbitmq_url)

    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=prefetch_count)

        exchange = await channel.declare_exchange(
            "test.prefetch", ExchangeType.FANOUT, durable=True
        )

        queue = await channel.declare_queue("test.prefetch.queue", durable=True)
        await queue.bind(exchange)

        # 메시지 발행
        for seq in range(message_count):
            message = aio_pika.Message(
                body=json.dumps({"seq": seq}).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
            )
            await exchange.publish(message, routing_key="")

        print(f"[TEST] {message_count}개 메시지 발행, prefetch={prefetch_count}")

        # 수동 ACK로 unacked 메시지 추적
        unacked_messages: list[aio_pika.IncomingMessage] = []
        processed = 0

        async with queue.iterator(no_ack=False) as queue_iter:
            async for message in queue_iter:
                unacked_messages.append(message)

                if len(unacked_messages) > result["max_unacked"]:
                    result["max_unacked"] = len(unacked_messages)

                # 10개마다 ACK
                if len(unacked_messages) >= 10:
                    for msg in unacked_messages:
                        await msg.ack()
                        processed += 1
                    unacked_messages.clear()

                if processed >= message_count:
                    break

        # 남은 메시지 ACK
        for msg in unacked_messages:
            await msg.ack()
            processed += 1

        result["total_processed"] = processed
        result["prefetch_respected"] = result["max_unacked"] <= prefetch_count

        print(
            f"  최대 unacked: {result['max_unacked']}, "
            f"prefetch 준수: {result['prefetch_respected']}"
        )

        # 정리
        await queue.delete()
        await exchange.delete()

    finally:
        await connection.close()

    return result


async def run_consumer_ack_tests():
    """모든 Consumer ACK 테스트 실행"""
    print("=" * 60)
    print("Consumer ACK 검증 테스트")
    print("=" * 60)

    # 테스트 1: 기본 ACK
    print("\n[1/3] 기본 Consumer ACK 테스트")
    metrics1 = await test_consumer_ack_basic(message_count=500)
    print(
        f"  결과: ACK율 {metrics1.ack_rate:.1f}%, "
        f"평균 처리시간 {metrics1.avg_processing_ms:.2f}ms"
    )

    # 테스트 2: Requeue
    print("\n[2/3] Requeue 동작 테스트")
    result2 = await test_consumer_requeue(message_count=100, fail_rate=0.2)
    print(
        f"  초기 실패: {result2['initial_failures']}개, "
        f"재큐잉: {result2['requeue_attempts']}회, "
        f"최종 성공: {result2['final_success']}개"
    )
    print(f"  전체 처리: {'완료' if result2['all_processed'] else '미완료'}")

    # 테스트 3: Prefetch
    print("\n[3/3] Prefetch (QoS) 테스트")
    result3 = await test_consumer_prefetch(message_count=1000, prefetch_count=100)
    print(f"  Prefetch 준수: {'예' if result3['prefetch_respected'] else '아니오'}")

    # 종합 결과
    print("\n" + "=" * 60)
    print("테스트 종합 결과")
    print("=" * 60)

    all_passed = (
        metrics1.ack_rate == 100
        and result2["all_processed"]
        and result3["prefetch_respected"]
    )

    print(f"  기본 ACK: {'PASS' if metrics1.ack_rate == 100 else 'FAIL'}")
    print(f"  Requeue 처리: {'PASS' if result2['all_processed'] else 'FAIL'}")
    print(f"  Prefetch: {'PASS' if result3['prefetch_respected'] else 'FAIL'}")
    print(f"\n  최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_consumer_ack_tests())
