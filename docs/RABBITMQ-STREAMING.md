# RabbitMQ 실시간 주가 스트리밍 아키텍처

## 개요

KIS WebSocket API에서 수신한 실시간 주가 데이터를 RabbitMQ를 통해 분산 처리하는 시스템입니다.

```
┌─────────────────┐      ┌─────────────┐      ┌─────────────────────┐
│  KIS WebSocket  │ ───▶ │ RabbitMQ    │ ───▶ │ tick-writer  │ ───▶ TimescaleDB
│  (kis-publisher)│      │ (Exchange)  │      └─────────────────────┘
└─────────────────┘      │             │      ┌─────────────────────┐
                         │  FANOUT     │ ───▶ │ tick-broadcaster   │ ───▶ Django Channels
                         └─────────────┘      └─────────────────────┘            │
                                                                                 ▼
                                                                          WebSocket 클라이언트
```

## 컴포넌트

### 1. kis-publisher (Producer)

**역할**: KIS WebSocket에서 실시간 체결 데이터를 수신하여 RabbitMQ로 발행

**위치**: `kis-publisher/main.py`

**주요 설정**:
```python
Exchange: "stock.realtime" (FANOUT)
Delivery Mode: PERSISTENT (디스크 저장)
```

**메시지 형식**:
```json
{
  "stock_code": "005930",
  "symbol": "삼성전자",
  "time": "093000",
  "price": 71500,
  "volume": 1000
}
```

### 2. tick-writer (Consumer #1)

**역할**: RabbitMQ에서 메시지를 구독하여 TimescaleDB에 배치 저장

**위치**: `tick-writer/main.py`

**주요 설정**:
```python
Queue: "stock.ticks.persistence"
Prefetch: 200 (배치 크기와 동일)
Batch Size: 200
Flush Interval: 5초
TTL: 없음 (메시지 자동 삭제 방지)
Max Length: 1,000,000 (디스크 보호용)
```

**배치 처리**:
- 200개 메시지 도달 또는 5초 경과 시 DB에 일괄 저장
- `executemany()`로 성능 최적화
- `ON CONFLICT` 처리로 중복 데이터 병합

### 3. tick-broadcaster (Consumer #2)

**역할**: RabbitMQ에서 메시지를 구독하여 Django Channels WebSocket으로 브로드캐스트

**위치**: `core/management/commands/tick_broadcaster.py`

**주요 설정**:
```python
Queue: "stock.ticks.channels"
Prefetch: 100
Max Length: 100,000
```

**브로드캐스트**:
- 종목별 그룹 (`stock_{code}`)으로 선택적 전송
- 구독 중인 클라이언트에게만 실시간 데이터 전달

---

## 메시지 보증 메커니즘

### 현재 상태

| 구분 | 상태 | 설명 |
|------|------|------|
| **Publisher Confirm** | ✅ 구현됨 | 메시지 발행 확인 + 메트릭 추적 |
| **Consumer ACK** | ✅ 구현됨 | 처리 완료 시 ACK, 실패 시 NACK+재큐잉 |
| **Message Persistence** | ✅ 구현됨 | `PERSISTENT` 모드로 디스크 저장 |
| **Durable Queue** | ✅ 구현됨 | RabbitMQ 재시작 후에도 큐 유지 |

### Consumer ACK 동작

```python
# tick-writer
async with message.process(requeue=True):
    # 정상 완료 → 자동 ACK
    # 예외 발생 → 자동 NACK + 재큐잉

except json.JSONDecodeError:
    await message.ack()  # 파싱 불가 메시지는 버림
```

| 상황 | 동작 | 결과 |
|------|------|------|
| 정상 처리 | ACK | 큐에서 제거 |
| JSON 파싱 실패 | ACK | 큐에서 제거 (버림) |
| DB 저장 실패 | NACK + requeue | 재시도 |
| 기타 예외 | NACK + requeue | 재시도 |

### 데이터 유실 위험 지점

1. ~~**kis-publisher → RabbitMQ**~~ ✅ 해결됨
   - Publisher Confirm으로 메시지 전달 확인
   - 실패 시 메트릭 기록 및 로그 출력

2. ~~**RabbitMQ TTL**~~ ✅ 해결됨
   - TTL 제거하여 메시지 자동 삭제 방지
   - x-max-length(100만 개)로 디스크 공간만 보호

3. **JSON 파싱 실패** ⚠️
   - 손상된 메시지 추적 불가 (DLQ 없음)
   - 권장: Dead Letter Queue 도입

---

## Publisher Confirm 구현 (✅ 완료)

### 구현 내용

kis-publisher에서 RabbitMQ로 메시지 발행 시 확인(confirm)을 받아 메시지 전달 보장

### 변경 파일

- `kis-publisher/main.py`

### 구현된 기능

#### 1. Publisher Confirms 활성화

```python
# kis-publisher/main.py:398-399
rabbitmq_channel = await rabbitmq_connection.channel()
await rabbitmq_channel.set_publisher_confirms(True)
```

#### 2. 발행 시 mandatory 플래그

```python
# kis-publisher/main.py:516-520
await rabbitmq_exchange.publish(
    rabbitmq_message,
    routing_key="",
    mandatory=True  # 라우팅 실패 시 예외 발생
)
```

#### 3. 메트릭 추적 클래스

```python
# kis-publisher/main.py:49-82
class PublishMetrics:
    def __init__(self):
        self.published = 0
        self.confirmed = 0
        self.failed = 0
        self.report_interval = 60  # 60초마다 메트릭 출력

    def record_success(self):
        self.published += 1
        self.confirmed += 1

    def record_failure(self, stock_code: str, error: str):
        self.published += 1
        self.failed += 1
        print(f"[CONFIRM FAILED] stock={stock_code}, error={error}")

    def report(self):
        success_rate = (self.confirmed / self.published * 100) if self.published > 0 else 0
        print(f"[METRICS] published={self.published}, confirmed={self.confirmed}, "
              f"failed={self.failed}, success_rate={success_rate:.2f}%")
```

#### 4. 예외 처리

```python
# kis-publisher/main.py:514-532
try:
    await rabbitmq_exchange.publish(...)
    publish_metrics.record_success()
except DeliveryError as e:
    publish_metrics.record_failure(stock_code, f"DeliveryError: {e}")
except Exception as e:
    publish_metrics.record_failure(stock_code, str(e))
```

### 로그 출력 예시

```
[INIT] Publisher Confirms enabled
[PROD] PUBLISH: stock.realtime exchange, stock=005930, price=71500
[METRICS] published=1000, confirmed=998, failed=2, success_rate=99.80%
[CONFIRM FAILED] stock=035720, error=DeliveryError: ...
[SHUTDOWN] Final metrics:
[METRICS] published=50000, confirmed=49995, failed=5, success_rate=99.99%
```

### 향후 개선 계획

1. **Phase 2**: 실패 메시지 버퍼링 및 재시도
2. **Phase 3**: Prometheus 메트릭 노출
3. **Phase 4**: Dead Letter Queue 연동

---

## 설정 참조

### 환경 변수

```bash
# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# kis-publisher
KIS_SYMBOL_LIMIT=5          # 구독 종목 수
KIS_MAX_RECONNECT=10        # 최대 재연결 시도
KIS_PING_INTERVAL=30        # PINGPONG 간격 (초)

# tick-writer
# (하드코딩됨 - 환경변수화 권장)
BATCH_SIZE=200
FLUSH_INTERVAL=5
```

### RabbitMQ 큐 설정

| 큐 | x-max-length | x-message-ttl | 용도 |
|----|--------------|---------------|------|
| stock.ticks.persistence | 1,000,000 | 없음 | DB 저장 |
| stock.ticks.channels | 100,000 | 없음 | WebSocket 브로드캐스트 |

---

## 모니터링

### RabbitMQ 큐 상태 확인

```bash
# 큐 목록 및 메시지 수
docker-compose exec rabbitmq rabbitmqctl list_queues name messages consumers

# 상세 정보
docker-compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

### 로그 모니터링

```bash
# kis-publisher 발행 로그
docker-compose logs -f kis-publisher | grep PUBLISH

# tick-writer 저장 로그
docker-compose logs -f tick-writer | grep -E "\[RECV\]|\[DB\]"

# tick-broadcaster 브로드캐스트 로그
docker-compose logs -f app | grep BROADCAST
```

### 데이터 검증 쿼리

```sql
-- 최근 저장된 데이터 확인
SELECT stock_code, COUNT(*), MIN(time), MAX(time)
FROM stock_ticks
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY stock_code
ORDER BY COUNT(*) DESC;

-- 시간대별 데이터 수
SELECT time_bucket('1 minute', time) AS bucket, COUNT(*)
FROM stock_ticks
WHERE time > NOW() - INTERVAL '10 minutes'
GROUP BY bucket
ORDER BY bucket;
```

---

## 참고 문서

- [RabbitMQ Publisher Confirms](https://www.rabbitmq.com/confirms.html)
- [aio-pika Documentation](https://aio-pika.readthedocs.io/)
- [TimescaleDB Hypertables](https://docs.timescale.com/use-timescale/latest/hypertables/)
