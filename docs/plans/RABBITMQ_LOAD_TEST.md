# RabbitMQ 주가 데이터 통신 부하테스트 계획

## 1. 테스트 개요

### 1.1 목적

RabbitMQ를 통한 실시간 주가 데이터 통신 시스템의 안정성과 데이터 무결성을 검증합니다.

- **Producer Confirm**: 메시지가 RabbitMQ에 정상 도달했는지 확인
- **Consumer ACK**: 메시지가 정상 처리되었는지 확인
- **데이터 일관성**: 발행된 메시지와 저장된 데이터의 일치 여부 확인

### 1.2 테스트 대상 시스템

```
┌─────────────────┐
│  Test Producer  │  ← 테스트용 데이터 생성
└────────┬────────┘
         │
    ┌────▼──────────────────────────────────┐
    │  FANOUT Exchange: stock.realtime      │
    │  (Publisher Confirms 검증)            │
    └────┬────────────────┬─────────────────┘
         │                │
┌────────▼────────┐  ┌────▼────────────┐
│ Queue:          │  │ Queue:          │
│ .persistence    │  │ .channels       │
└────────┬────────┘  └────────┬────────┘
         │                    │
┌────────▼────────────┐  ┌────▼────────────────┐
│ tick-writer  │  │ tick_broadcaster   │
│ (Consumer ACK)      │  │ (Consumer ACK)      │
└────────┬────────────┘  └───────────────────┘
         │
┌────────▼────────────┐
│  TimescaleDB        │
│  stock_ticks        │
│  (데이터 일관성)    │
└─────────────────────┘
```

### 1.3 현재 구현 상태

| 구성요소 | 구현 상태 | 파일 위치 |
|----------|----------|-----------|
| Publisher Confirms | `publisher_confirms=True` | `kis-publisher/main.py:391` |
| Confirm Metrics | `PublishMetrics` 클래스 | `kis-publisher/main.py:58-90` |
| Consumer ACK (persistence) | `requeue=True` | `tick-writer/main.py:133` |
| Consumer ACK (channels) | 자동 ACK | `core/management/commands/tick_broadcaster.py:79` |
| QoS 설정 | prefetch 200/100 | 각 워커 설정 |

---

## 2. 테스트 환경 구성

### 2.1 필수 서비스

```bash
# Docker Compose로 필수 서비스 시작
docker-compose up -d rabbitmq db redis

# 서비스 상태 확인
docker-compose ps
```

### 2.2 환경 변수 설정

```bash
# .env.test 파일 생성
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
REDIS_URL=redis://localhost:6379/0

# 테스트 모드 활성화
TEST_MODE=true
LOG_LEVEL=DEBUG
```

### 2.3 테스트용 Python 패키지

```bash
pip install aio-pika asyncpg pytest pytest-asyncio locust
```

---

## 3. 테스트 시나리오

### 3.1 시나리오 1: Publisher Confirm 검증

**목적**: Publisher가 발행한 모든 메시지가 RabbitMQ에 도달했는지 확인

**테스트 절차**:

1. **정상 케이스**: 메시지 1,000개 발행 → Confirm 수 확인
2. **실패 케이스**: 존재하지 않는 Exchange로 발행 → 실패 감지 확인
3. **부하 케이스**: 초당 1,000개 메시지 발행 → Confirm 지연 측정

**검증 기준**:

| 항목 | 기준값 |
|------|--------|
| Confirm 성공률 | 100% |
| Confirm 평균 지연 | < 10ms |
| Confirm 최대 지연 | < 100ms |

**테스트 코드**: `tests/load/test_publisher_confirm.py`

```python
"""
Publisher Confirm 검증 테스트
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.exceptions import DeliveryError


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
        "test_seq": seq,  # 검증용 시퀀스 번호
        "timestamp": time.time()
    }


async def test_publisher_confirm_basic(
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    message_count: int = 1000
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
            "stock.realtime.test",
            ExchangeType.FANOUT,
            durable=True
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
                content_type="application/json"
            )

            start_time = time.time()

            try:
                # mandatory=True: 라우팅 실패 시 예외 발생
                await exchange.publish(
                    message,
                    routing_key="",
                    mandatory=True
                )

                latency = time.time() - start_time
                metrics.total_published += 1
                metrics.total_confirmed += 1
                metrics.confirm_latencies.append(latency)

            except DeliveryError as e:
                metrics.total_published += 1
                metrics.total_failed += 1
                metrics.failed_messages.append({
                    "seq": seq,
                    "error": str(e)
                })

            # 진행 상황 출력
            if (seq + 1) % 100 == 0:
                print(f"  진행: {seq + 1}/{message_count} "
                      f"(성공률: {metrics.success_rate:.1f}%)")

        # 큐 정리
        await queue.delete()
        await exchange.delete()

    finally:
        await connection.close()

    return metrics


async def test_publisher_confirm_failure(
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
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
        "error_message": None
    }

    try:
        channel = await connection.channel(publisher_confirms=True)

        # 존재하지 않는 Exchange 사용
        exchange = await channel.declare_exchange(
            "nonexistent.exchange",
            ExchangeType.FANOUT,
            durable=False,
            auto_delete=True
        )

        # 바인딩 없이 mandatory=True로 발행 → 실패 예상
        message = aio_pika.Message(
            body=b'{"test": "failure"}',
            delivery_mode=DeliveryMode.PERSISTENT
        )

        try:
            await exchange.publish(
                message,
                routing_key="nonexistent.key",
                mandatory=True
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

        await exchange.delete()

    finally:
        await connection.close()

    return result


async def test_publisher_confirm_under_load(
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    messages_per_second: int = 1000,
    duration_seconds: int = 10
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
            "stock.realtime.loadtest",
            ExchangeType.FANOUT,
            durable=True
        )

        queue = await channel.declare_queue("loadtest.sink", durable=True)
        await queue.bind(exchange)

        total_messages = messages_per_second * duration_seconds
        interval = 1.0 / messages_per_second

        print(f"[LOAD TEST] {messages_per_second}/초 × {duration_seconds}초 "
              f"= {total_messages}개 메시지")

        start_time = time.time()

        for seq in range(total_messages):
            stock_code = f"00{seq % 100:04d}"
            data = generate_stock_tick(stock_code, seq)

            message = aio_pika.Message(
                body=json.dumps(data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT
            )

            confirm_start = time.time()

            try:
                await exchange.publish(message, routing_key="")
                latency = time.time() - confirm_start
                metrics.total_published += 1
                metrics.total_confirmed += 1
                metrics.confirm_latencies.append(latency)

            except DeliveryError as e:
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
                print(f"  {(seq + 1) // messages_per_second}초 경과: "
                      f"실제 처리량 {current_rate:.0f}/초, "
                      f"평균 지연 {metrics.avg_latency_ms:.2f}ms")

        total_time = time.time() - start_time
        print(f"[완료] 총 {total_time:.2f}초 소요, "
              f"처리량: {total_messages / total_time:.0f}/초")

        # 정리
        await queue.delete()
        await exchange.delete()

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
    print(f"  결과: 성공률 {metrics1.success_rate:.1f}%, "
          f"평균 지연 {metrics1.avg_latency_ms:.2f}ms, "
          f"최대 지연 {metrics1.max_latency_ms:.2f}ms")

    # 테스트 2: 실패 감지
    print("\n[2/3] 실패 감지 테스트")
    result2 = await test_publisher_confirm_failure()
    print(f"  실패 감지: {'성공' if result2['failure_detected'] else '실패'}")
    if result2['failure_detected']:
        print(f"  에러 타입: {result2['error_type']}")

    # 테스트 3: 부하 테스트
    print("\n[3/3] 부하 상황 테스트 (500/초 × 10초)")
    metrics3 = await test_publisher_confirm_under_load(
        messages_per_second=500,
        duration_seconds=10
    )
    print(f"  결과: 성공률 {metrics3.success_rate:.1f}%, "
          f"평균 지연 {metrics3.avg_latency_ms:.2f}ms, "
          f"최대 지연 {metrics3.max_latency_ms:.2f}ms")

    # 종합 결과
    print("\n" + "=" * 60)
    print("테스트 종합 결과")
    print("=" * 60)

    all_passed = (
        metrics1.success_rate == 100 and
        result2['failure_detected'] and
        metrics3.success_rate == 100 and
        metrics3.avg_latency_ms < 10 and
        metrics3.max_latency_ms < 100
    )

    print(f"  기본 테스트: {'PASS' if metrics1.success_rate == 100 else 'FAIL'}")
    print(f"  실패 감지: {'PASS' if result2['failure_detected'] else 'FAIL'}")
    print(f"  부하 성공률: {'PASS' if metrics3.success_rate == 100 else 'FAIL'}")
    print(f"  부하 평균지연 (<10ms): {'PASS' if metrics3.avg_latency_ms < 10 else 'FAIL'}")
    print(f"  부하 최대지연 (<100ms): {'PASS' if metrics3.max_latency_ms < 100 else 'FAIL'}")
    print(f"\n  최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_publisher_confirm_tests())
```

---

### 3.2 시나리오 2: Consumer ACK 검증

**목적**: Consumer가 메시지를 정상 처리하고 ACK/NACK를 올바르게 전송하는지 확인

**테스트 절차**:

1. **정상 ACK**: 메시지 처리 성공 시 ACK 전송 확인
2. **Requeue 동작**: 처리 실패 시 메시지가 재큐잉되는지 확인
3. **NACK 후 DLQ**: Dead Letter Queue 동작 확인 (선택)

**검증 기준**:

| 항목 | 기준값 |
|------|--------|
| ACK 성공률 | 100% (정상 메시지) |
| Requeue 동작 | 실패 메시지 재처리 |
| 미처리 메시지 | 0개 (테스트 종료 후) |

**테스트 코드**: `tests/load/test_consumer_ack.py`

```python
"""
Consumer ACK 검증 테스트
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aio_pika
from aio_pika import ExchangeType, DeliveryMode


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
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    message_count: int = 500
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
            "test.consumer.ack",
            ExchangeType.FANOUT,
            durable=True
        )

        queue = await channel.declare_queue(
            "test.consumer.ack.queue",
            durable=True
        )
        await queue.bind(exchange)

        # 1단계: 메시지 발행
        print(f"[PRODUCER] {message_count}개 메시지 발행...")

        for seq in range(message_count):
            data = {
                "stock_code": f"00{seq % 10:04d}",
                "price": 50000 + seq,
                "volume": 100,
                "test_seq": seq,
                "timestamp": time.time()
            }

            message = aio_pika.Message(
                body=json.dumps(data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT
            )

            await exchange.publish(message, routing_key="")

        print(f"[PRODUCER] 발행 완료")

        # 2단계: 메시지 소비 및 ACK
        print(f"[CONSUMER] 메시지 소비 시작...")

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
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    message_count: int = 100,
    fail_rate: float = 0.2  # 20% 실패
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
        "all_processed": False
    }

    connection = await aio_pika.connect_robust(rabbitmq_url)

    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            "test.requeue",
            ExchangeType.FANOUT,
            durable=True
        )

        queue = await channel.declare_queue(
            "test.requeue.queue",
            durable=True
        )
        await queue.bind(exchange)

        # 실패 이력 추적
        attempt_counts: dict[int, int] = {}
        processed_seqs: set[int] = set()

        # 메시지 발행
        print(f"[PRODUCER] {message_count}개 메시지 발행...")

        for seq in range(message_count):
            data = {
                "test_seq": seq,
                "timestamp": time.time()
            }

            message = aio_pika.Message(
                body=json.dumps(data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT
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
                    attempt_counts[seq] == 1 and
                    seq < message_count * fail_rate
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
            print(f"  재시도된 메시지: {len(retry_counts)}개, "
                  f"평균 재시도: {sum(retry_counts) / len(retry_counts):.1f}회")

        # 정리
        await queue.delete()
        await exchange.delete()

    finally:
        await connection.close()

    return result


async def test_consumer_prefetch(
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    message_count: int = 1000,
    prefetch_count: int = 100
) -> dict:
    """
    시나리오 2-3: Prefetch (QoS) 동작 테스트

    prefetch_count 설정이 올바르게 적용되는지 확인
    """
    result = {
        "prefetch_count": prefetch_count,
        "max_unacked": 0,
        "total_processed": 0,
        "prefetch_respected": False
    }

    connection = await aio_pika.connect_robust(rabbitmq_url)

    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=prefetch_count)

        exchange = await channel.declare_exchange(
            "test.prefetch",
            ExchangeType.FANOUT,
            durable=True
        )

        queue = await channel.declare_queue(
            "test.prefetch.queue",
            durable=True
        )
        await queue.bind(exchange)

        # 메시지 발행
        for seq in range(message_count):
            message = aio_pika.Message(
                body=json.dumps({"seq": seq}).encode(),
                delivery_mode=DeliveryMode.PERSISTENT
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

        print(f"  최대 unacked: {result['max_unacked']}, "
              f"prefetch 준수: {result['prefetch_respected']}")

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
    print(f"  결과: ACK율 {metrics1.ack_rate:.1f}%, "
          f"평균 처리시간 {metrics1.avg_processing_ms:.2f}ms")

    # 테스트 2: Requeue
    print("\n[2/3] Requeue 동작 테스트")
    result2 = await test_consumer_requeue(message_count=100, fail_rate=0.2)
    print(f"  초기 실패: {result2['initial_failures']}개, "
          f"재큐잉: {result2['requeue_attempts']}회, "
          f"최종 성공: {result2['final_success']}개")
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
        metrics1.ack_rate == 100 and
        result2['all_processed'] and
        result3['prefetch_respected']
    )

    print(f"  기본 ACK: {'PASS' if metrics1.ack_rate == 100 else 'FAIL'}")
    print(f"  Requeue 처리: {'PASS' if result2['all_processed'] else 'FAIL'}")
    print(f"  Prefetch: {'PASS' if result3['prefetch_respected'] else 'FAIL'}")
    print(f"\n  최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_consumer_ack_tests())
```

---

### 3.3 시나리오 3: 데이터 일관성 검증

**목적**: 발행된 메시지와 데이터베이스에 저장된 데이터의 일치 확인

**테스트 절차**:

1. **고유 시퀀스 포함 메시지 발행**
2. **tick-writer 가동 (또는 테스트용 Consumer)**
3. **TimescaleDB에서 저장된 데이터 조회**
4. **발행 데이터 vs 저장 데이터 비교**

**검증 기준**:

| 항목 | 기준값 |
|------|--------|
| 데이터 손실률 | 0% |
| 데이터 중복률 | 0% (upsert 제외) |
| 필드 일치율 | 100% |

**테스트 코드**: `tests/load/test_data_consistency.py`

```python
"""
데이터 일관성 검증 테스트
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import aio_pika
import asyncpg
from aio_pika import ExchangeType, DeliveryMode


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
    await pool.execute(f"""
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
    """)

    # 인덱스 생성
    await pool.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_batch
        ON {table_name} (test_batch_id)
    """)


async def drop_test_table(pool: asyncpg.Pool, table_name: str):
    """테스트 테이블 삭제"""
    await pool.execute(f"DROP TABLE IF EXISTS {table_name}")


async def test_data_consistency(
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres",
    message_count: int = 1000,
    batch_size: int = 100
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
                "test.consistency",
                ExchangeType.FANOUT,
                durable=True
            )

            queue = await channel.declare_queue(
                "test.consistency.queue",
                durable=True
            )
            await queue.bind(exchange)

            # ===== 1단계: 메시지 발행 =====
            print(f"\n[1/4] 메시지 발행...")

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
                    "test_seq": seq
                }

                published_data[seq] = {
                    **data,
                    "time_dt": msg_time
                }

                message = aio_pika.Message(
                    body=json.dumps(data).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT
                )

                await exchange.publish(message, routing_key="")
                metrics.total_published += 1

                if (seq + 1) % 200 == 0:
                    print(f"  발행: {seq + 1}/{message_count}")

            print(f"  발행 완료: {metrics.total_published}개")

            # ===== 2단계: 메시지 소비 및 저장 =====
            print(f"\n[2/4] 메시지 소비 및 저장...")

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
                                d["test_seq"]
                            )
                            for d in buffer
                        ]
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
                        microsecond = int(time_str[6:]) * 1000 if len(time_str) > 6 else 0

                        data["time_dt"] = base_time.replace(
                            hour=hour, minute=minute, second=second,
                            microsecond=microsecond
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
            print(f"\n[3/4] 데이터 검증...")

            async with db_pool.acquire() as conn:
                # 저장된 데이터 조회
                rows = await conn.fetch(
                    f"""
                    SELECT stock_code, symbol, time, price, volume, test_seq
                    FROM {table_name}
                    WHERE test_batch_id = $1
                    ORDER BY test_seq
                    """,
                    batch_id
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
                    metrics.field_mismatches.append({
                        "seq": seq, "field": "stock_code",
                        "expected": pub_data["stock_code"],
                        "actual": stored["stock_code"]
                    })

                if abs(float(pub_data["price"]) - float(stored["price"])) > 0.01:
                    matched = False
                    metrics.field_mismatches.append({
                        "seq": seq, "field": "price",
                        "expected": pub_data["price"],
                        "actual": float(stored["price"])
                    })

                if pub_data["volume"] != stored["volume"]:
                    matched = False
                    metrics.field_mismatches.append({
                        "seq": seq, "field": "volume",
                        "expected": pub_data["volume"],
                        "actual": stored["volume"]
                    })

                if matched:
                    metrics.total_matched += 1

            print(f"  검증 완료")

            # ===== 4단계: 결과 출력 =====
            print(f"\n[4/4] 결과 분석...")
            print(f"  발행: {metrics.total_published}개")
            print(f"  저장: {metrics.total_stored}개")
            print(f"  일치: {metrics.total_matched}개 ({metrics.match_rate:.1f}%)")
            print(f"  누락: {metrics.total_missing}개 ({metrics.loss_rate:.1f}%)")
            print(f"  중복: {metrics.total_duplicates}개")
            print(f"  필드 불일치: {len(metrics.field_mismatches)}건")

            if metrics.missing_sequences and len(metrics.missing_sequences) <= 10:
                print(f"  누락 시퀀스: {metrics.missing_sequences}")

            if metrics.field_mismatches and len(metrics.field_mismatches) <= 5:
                print(f"  불일치 샘플:")
                for m in metrics.field_mismatches[:5]:
                    print(f"    seq={m['seq']}, {m['field']}: "
                          f"{m['expected']} → {m['actual']}")

            # 정리
            await queue.delete()
            await exchange.delete()

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
        metrics.loss_rate == 0 and
        metrics.total_duplicates == 0 and
        len(metrics.field_mismatches) == 0
    )

    print(f"  손실률 (0%): {'PASS' if metrics.loss_rate == 0 else 'FAIL'}")
    print(f"  중복 (0개): {'PASS' if metrics.total_duplicates == 0 else 'FAIL'}")
    print(f"  필드 일치 (100%): {'PASS' if len(metrics.field_mismatches) == 0 else 'FAIL'}")
    print(f"\n  최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_data_consistency_tests())
```

---

### 3.4 시나리오 4: 종합 부하 테스트

**목적**: 실제 운영 환경과 유사한 부하에서 전체 시스템 검증

**테스트 구성**:

| 항목 | 설정값 |
|------|--------|
| 동시 종목 수 | 40개 (KIS 제한) |
| 초당 메시지 | 400개 (종목당 10개) |
| 테스트 시간 | 5분 |
| 총 메시지 수 | 120,000개 |

**테스트 코드**: `tests/load/test_full_load.py`

```python
"""
종합 부하 테스트
"""
import asyncio
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import aio_pika
import asyncpg
from aio_pika import ExchangeType, DeliveryMode


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
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres",
    stock_count: int = 40,
    messages_per_second: int = 400,
    duration_seconds: int = 60,
    consumer_batch_size: int = 200
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
        await db_pool.execute(f"""
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
        """)

        # RabbitMQ 연결
        rmq_connection = await aio_pika.connect_robust(rabbitmq_url)

        try:
            # Publisher 채널
            pub_channel = await rmq_connection.channel(publisher_confirms=True)

            exchange = await pub_channel.declare_exchange(
                "test.loadtest",
                ExchangeType.FANOUT,
                durable=True
            )

            queue = await pub_channel.declare_queue(
                "test.loadtest.queue",
                durable=True,
                arguments={
                    "x-max-length": 1000000
                }
            )
            await queue.bind(exchange)

            # Consumer 채널
            con_channel = await rmq_connection.channel()
            await con_channel.set_qos(prefetch_count=consumer_batch_size)

            # 제어 플래그
            publishing_done = asyncio.Event()
            consuming_done = asyncio.Event()

            # ===== Producer Task =====
            async def producer():
                nonlocal metrics

                interval = 1.0 / messages_per_second
                metrics.start_time = time.time()

                print(f"\n[PRODUCER] 시작...")

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
                        "publish_time": publish_time
                    }

                    message = aio_pika.Message(
                        body=json.dumps(data).encode(),
                        delivery_mode=DeliveryMode.PERSISTENT
                    )

                    confirm_start = time.time()

                    try:
                        await exchange.publish(message, routing_key="")
                        metrics.publish_latencies.append(time.time() - confirm_start)
                        metrics.total_published += 1
                        metrics.publish_confirmed += 1

                    except Exception as e:
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
                        print(f"  [PUB] {(seq + 1) // messages_per_second}초: "
                              f"{current_rate:.0f}/초, "
                              f"확인율 {metrics.publish_confirmed / metrics.total_published * 100:.1f}%")

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
                            (stock_code, time, price, volume, test_batch_id, test_seq, publish_time)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT DO NOTHING
                            """,
                            buffer
                        )

                    metrics.db_latencies.append(time.time() - db_start)
                    metrics.total_stored += len(buffer)
                    buffer.clear()

                print(f"\n[CONSUMER] 시작...")

                async with queue.iterator(no_ack=False) as queue_iter:
                    async for message in queue_iter:
                        consume_time = time.time()

                        async with message.process():
                            data = json.loads(message.body)

                            # E2E 지연 계산
                            publish_time = data.get("publish_time", consume_time)
                            metrics.consume_latencies.append(consume_time - publish_time)
                            metrics.total_consumed += 1

                            # 시간 파싱
                            time_str = data["time"]
                            msg_time = datetime.now().replace(
                                hour=int(time_str[:2]),
                                minute=int(time_str[2:4]),
                                second=int(time_str[4:6]),
                                microsecond=int(time_str[6:]) * 1000 if len(time_str) > 6 else 0
                            )

                            buffer.append((
                                data["stock_code"],
                                msg_time,
                                Decimal(str(data["price"])),
                                data["volume"],
                                uuid.UUID(data["test_batch_id"]),
                                data["test_seq"],
                                publish_time
                            ))

                            if len(buffer) >= consumer_batch_size:
                                await save_batch()

                        # 10초마다 진행 상황
                        if metrics.total_consumed % (messages_per_second * 10) == 0:
                            print(f"  [CON] 소비: {metrics.total_consumed}개, "
                                  f"저장: {metrics.total_stored}개")

                        # 모든 메시지 처리 완료
                        if publishing_done.is_set() and metrics.total_consumed >= metrics.total_published:
                            break

                # 남은 버퍼 저장
                await save_batch()

                consuming_done.set()
                metrics.end_time = time.time()

                print(f"[CONSUMER] 완료: {metrics.total_consumed}개 소비, "
                      f"{metrics.total_stored}개 저장")

            # ===== 병렬 실행 =====
            await asyncio.gather(
                producer(),
                consumer()
            )

            # ===== 결과 분석 =====
            print("\n" + "=" * 60)
            print("테스트 결과")
            print("=" * 60)

            print(f"\n[시간]")
            print(f"  총 소요 시간: {metrics.duration_seconds:.2f}초")

            print(f"\n[Publisher]")
            print(f"  발행: {metrics.total_published}개")
            print(f"  확인: {metrics.publish_confirmed}개 "
                  f"({metrics.publish_confirmed / metrics.total_published * 100:.1f}%)")
            print(f"  실패: {metrics.publish_failed}개")
            print(f"  처리량: {metrics.publish_rate:.0f}/초")
            if metrics.publish_latencies:
                print(f"  확인 지연 (평균): {sum(metrics.publish_latencies) / len(metrics.publish_latencies) * 1000:.2f}ms")

            print(f"\n[Consumer]")
            print(f"  소비: {metrics.total_consumed}개")
            print(f"  저장: {metrics.total_stored}개")
            print(f"  처리량: {metrics.consume_rate:.0f}/초")
            print(f"  E2E 지연 (평균): {metrics.avg_e2e_latency_ms:.2f}ms")
            print(f"  E2E 지연 (P99): {metrics.p99_e2e_latency_ms:.2f}ms")

            if metrics.db_latencies:
                print(f"\n[Database]")
                print(f"  배치 저장 횟수: {len(metrics.db_latencies)}")
                print(f"  저장 지연 (평균): {sum(metrics.db_latencies) / len(metrics.db_latencies) * 1000:.2f}ms")

            # 검증
            print(f"\n[검증]")
            loss_count = metrics.total_published - metrics.total_consumed
            loss_rate = loss_count / metrics.total_published * 100 if metrics.total_published > 0 else 0
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
        stock_count=10,
        messages_per_second=100,
        duration_seconds=60
    )

    # 테스트 2: 중간 부하 (1분)
    print("\n" + "=" * 70)
    print("테스트 2: 중간 부하 (300/초 × 60초)")
    print("=" * 70)

    metrics2 = await run_full_load_test(
        stock_count=30,
        messages_per_second=300,
        duration_seconds=60
    )

    # 테스트 3: 고부하 (30초)
    print("\n" + "=" * 70)
    print("테스트 3: 고부하 (500/초 × 30초)")
    print("=" * 70)

    metrics3 = await run_full_load_test(
        stock_count=40,
        messages_per_second=500,
        duration_seconds=30
    )

    # 종합 결과
    print("\n" + "=" * 70)
    print("종합 결과 요약")
    print("=" * 70)

    results = [
        ("경량 (100/초)", metrics1),
        ("중간 (300/초)", metrics2),
        ("고부하 (500/초)", metrics3)
    ]

    print(f"\n{'테스트':<15} {'발행':<10} {'소비':<10} {'손실률':<10} {'E2E P99':<12}")
    print("-" * 60)

    for name, m in results:
        loss_rate = (m.total_published - m.total_consumed) / m.total_published * 100
        print(f"{name:<15} {m.total_published:<10} {m.total_consumed:<10} "
              f"{loss_rate:<10.2f}% {m.p99_e2e_latency_ms:<12.2f}ms")

    # 합격 기준
    all_passed = all(
        (m.total_published - m.total_consumed) / m.total_published < 0.01 and  # 손실률 < 1%
        m.p99_e2e_latency_ms < 1000  # P99 < 1초
        for _, m in results
    )

    print(f"\n최종 결과: {'ALL PASS' if all_passed else 'SOME FAILED'}")

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_load_test_suite())
```

---

## 4. 테스트 실행 방법

### 4.1 단일 테스트 실행

```bash
# 가상환경 활성화
source .venv/bin/activate

# Publisher Confirm 테스트
python tests/load/test_publisher_confirm.py

# Consumer ACK 테스트
python tests/load/test_consumer_ack.py

# 데이터 일관성 테스트
python tests/load/test_data_consistency.py

# 종합 부하 테스트
python tests/load/test_full_load.py
```

### 4.2 전체 테스트 스위트 실행

```bash
# pytest로 실행
pytest tests/load/ -v --tb=short

# 특정 테스트만
pytest tests/load/test_publisher_confirm.py -v
```

### 4.3 Docker 환경에서 실행

```bash
# 테스트 환경 시작
docker-compose up -d rabbitmq db

# 테스트 실행
docker-compose run --rm app python tests/load/test_full_load.py
```

---

## 5. 모니터링 및 디버깅

### 5.1 RabbitMQ Management UI

```
URL: http://localhost:15672
계정: guest / guest

확인 항목:
- Connections: 연결 수
- Channels: 채널 수 및 Confirm 상태
- Queues: 메시지 수, Consumer 수, ACK 비율
- Exchange: 메시지 발행 비율
```

### 5.2 실시간 모니터링 쿼리

```bash
# 큐 상태 확인
docker-compose exec rabbitmq rabbitmqctl list_queues name messages consumers

# 연결 상태
docker-compose exec rabbitmq rabbitmqctl list_connections name state

# 채널 상태 (Confirm 포함)
docker-compose exec rabbitmq rabbitmqctl list_channels connection confirm
```

### 5.3 TimescaleDB 확인

```sql
-- 저장된 데이터 수 확인
SELECT COUNT(*) FROM stock_ticks WHERE time > NOW() - INTERVAL '1 hour';

-- 종목별 데이터 수
SELECT stock_code, COUNT(*)
FROM stock_ticks
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY stock_code
ORDER BY COUNT(*) DESC;

-- 최근 저장 지연 확인
SELECT
    stock_code,
    MAX(time) as last_tick,
    NOW() - MAX(time) as delay
FROM stock_ticks
GROUP BY stock_code;
```

---

## 6. 예상 결과 및 기준값

### 6.1 성능 기준

| 지표 | 기준값 | 비고 |
|------|--------|------|
| Publisher Confirm 성공률 | ≥ 99.9% | 네트워크 일시적 오류 허용 |
| Consumer ACK 성공률 | 100% | 정상 메시지 |
| 데이터 손실률 | 0% | 손실 불허 |
| E2E 지연 (평균) | < 100ms | 발행→저장 |
| E2E 지연 (P99) | < 500ms | 최악의 경우 |
| 처리량 | ≥ 500/초 | 목표 처리량 |

### 6.2 실패 시 조치 사항

| 실패 유형 | 원인 | 조치 |
|-----------|------|------|
| Confirm 실패 | RabbitMQ 과부하 | prefetch 조절, 클러스터 확장 |
| ACK 실패 | Consumer 처리 지연 | 배치 크기 조절, Worker 수 증가 |
| 데이터 손실 | 큐 오버플로우 | x-max-length 증가, DLQ 설정 |
| 높은 지연 | DB 병목 | 인덱스 최적화, 배치 크기 조절 |

---

## 7. 테스트 체크리스트

### 7.1 테스트 전 확인

- [ ] RabbitMQ 서비스 정상 가동
- [ ] TimescaleDB 서비스 정상 가동
- [ ] Redis 서비스 정상 가동 (선택)
- [ ] 테스트 환경 변수 설정 (.env.test)
- [ ] 이전 테스트 데이터 정리

### 7.2 테스트 실행 중 확인

- [ ] RabbitMQ Management UI에서 큐 상태 모니터링
- [ ] 메모리 사용량 확인 (Docker stats)
- [ ] 에러 로그 확인

### 7.3 테스트 후 확인

- [ ] 모든 테스트 PASS 확인
- [ ] 테스트 데이터 정리 (테스트 테이블 삭제)
- [ ] 결과 기록 및 문서화

---

## 8. 참고 자료

- [RabbitMQ Publisher Confirms](https://www.rabbitmq.com/confirms.html)
- [aio-pika Documentation](https://aio-pika.readthedocs.io/)
- [TimescaleDB Best Practices](https://docs.timescale.com/timescaledb/latest/how-to-guides/write-data/best-practices/)
- 프로젝트 아키텍처: `docs/SYSTEM_ARCHITECTURE.md`
