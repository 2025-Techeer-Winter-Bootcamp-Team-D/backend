# RabbitMQ 부하 테스트 분석 보고서

## 테스트 개요

| 항목 | 값 |
|------|-----|
| 테스트 일시 | 2026-02-07 |
| 테스트 유형 | 스트레스 테스트 |
| 목표 처리량 | 10,000 메시지/초 |
| 테스트 시간 | 30초 (목표) |
| 총 메시지 수 | 300,000개 |
| 종목 수 | 40개 |

## 테스트 결과

### 성능 요약

| 지표 | 목표 | 실제 | 달성률 |
|------|------|------|--------|
| 처리량 | 10,000/초 | 1,401/초 | 14% |
| 소요 시간 | 30초 | 214초 | - |
| 손실률 | 0% | 0% | ✅ |
| P99 지연 | <100ms | 3.11ms | ✅ |

### 상세 지연 분석

| 구간 | 평균 지연 | 비고 |
|------|----------|------|
| Publisher Confirm | 0.69ms | RabbitMQ ACK 대기 |
| E2E 지연 | 0.42ms | 발행→소비 전체 시간 |
| DB 배치 저장 | 8.44ms | **주요 병목** |

---

## 병목 원인 분석

### 1. 단일 Consumer 구조

**현재 아키텍처:**

```
[Publisher] ─────> [RabbitMQ Queue] ─────> [Consumer 1개] ─────> [DB]
   10,000/초            (대기열)              1,400/초
```

테스트 코드 구조:
- Producer: 단일 비동기 태스크 (`tests/load/test_full_load.py:211-267`)
- Consumer: 단일 비동기 태스크 (`tests/load/test_full_load.py:270-361`)
- `asyncio.gather(producer(), consumer())`로 병렬 실행

**문제점:**
- Consumer가 1개뿐이어서 처리 속도가 발행 속도를 따라가지 못함
- RabbitMQ 큐에 메시지가 쌓이면서 대기열 형성
- Producer가 전체 발행 완료 후에도 Consumer가 처리 중

### 2. 동기적 DB 저장

**배치 저장 로직:** (`tests/load/test_full_load.py:275-295`)

```python
async def save_batch():
    async with db_pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO ... VALUES ($1, $2, ...) ON CONFLICT DO NOTHING",
            buffer,  # 200개 배치
        )
```

**지연 분석:**
- 배치 크기: 200개
- 저장 지연: 8.44ms
- 이론적 최대 처리량: `200개 / 8.44ms = 23,700개/초`

**실제 병목:**
- DB 저장 중 Consumer는 블로킹됨
- 저장→ACK→다음 메시지 수신의 순차적 사이클
- 실제 처리량은 이론값보다 낮음 (오버헤드 포함)

### 3. Publisher Confirm 동기 대기

**발행 로직:** (`tests/load/test_full_load.py:240-248`)

```python
try:
    await exchange.publish(message, routing_key="")  # confirm 대기
    metrics.publish_latencies.append(time.time() - confirm_start)
```

**지연 분석:**
- Confirm 평균 지연: 0.69ms
- 이론적 최대 발행량: `1000ms / 0.69ms = 1,449개/초` (단일 스레드)

**실제 영향:**
- Publisher도 단일 태스크로 순차 발행
- 10,000/초 달성 불가능한 구조

### 4. 속도 조절 로직

**Throttling:** (`tests/load/test_full_load.py:250-254`)

```python
elapsed = time.time() - metrics.start_time
expected = (seq + 1) * interval  # interval = 1/10000 = 0.0001초
if elapsed < expected:
    await asyncio.sleep(expected - elapsed)
```

**문제점:**
- 목표 속도(10,000/초)로 발행하려 하지만
- Confirm 대기 시간이 interval보다 길어서 실제로는 throttling 되지 않음
- 오히려 Confirm 대기가 병목

---

## 처리량 한계 계산

### 이론적 최대값

| 구간 | 계산식 | 이론적 최대 |
|------|--------|-------------|
| Publisher (단일) | 1000ms / 0.69ms | 1,449/초 |
| Consumer (단일) | 계산 복잡 | ~1,500/초 |
| DB 저장 | 200개 / 8.44ms | 23,700/초 |

**병목 지점:** Publisher Confirm 대기 + 단일 Consumer 구조

### 실제 측정값

```
실제 처리량: 1,401/초
이론적 Publisher 한계: 1,449/초
효율: 96.7%
```

→ 현재 구조에서는 **이론적 한계에 근접한 성능**을 달성

---

## 개선 방안

### 방안 1: Consumer 다중화 (권장)

```
                              ┌─> [Consumer 1] ─┐
[Publisher] ─> [RabbitMQ] ────┼─> [Consumer 2] ─┼─> [DB]
                              └─> [Consumer 3] ─┘
```

**구현 예시:**
```python
consumers = [consumer() for _ in range(consumer_count)]
await asyncio.gather(producer(), *consumers)
```

**예상 효과:**
- 3개 Consumer: ~4,000/초
- 10개 Consumer: ~10,000/초 (목표 달성)

### 방안 2: Publisher 병렬화

```python
async def batch_publish(messages):
    await asyncio.gather(*[
        exchange.publish(msg, routing_key="")
        for msg in messages
    ])
```

**예상 효과:**
- 10개 동시 발행: ~10,000/초

### 방안 3: 비동기 DB 저장 (Write-Behind)

```python
# 저장 완료를 기다리지 않고 ACK
asyncio.create_task(save_batch())
await message.ack()
```

**주의:**
- 데이터 유실 위험 (저장 실패 시)
- 메모리 사용량 증가

### 방안 4: DB 배치 크기 조정

| 배치 크기 | 저장 지연 (예상) | 효율 |
|----------|-----------------|------|
| 200 | 8.44ms | 23,700/초 |
| 500 | ~15ms | 33,300/초 |
| 1000 | ~25ms | 40,000/초 |

→ 배치 크기 증가 시 단위당 오버헤드 감소

---

## 10,000/초 달성 구현 가이드

### 목표 아키텍처

```
                                    ┌─> [Consumer 1] ─┐
┌─> [Publisher 1] ─┐                │                 │
│                  │                ├─> [Consumer 2] ─┤
├─> [Publisher 2] ─┼─> [RabbitMQ] ──┤                 ├─> [DB Pool]
│                  │                ├─> [Consumer 3] ─┤
└─> [Publisher 3] ─┘                │                 │
                                    └─> [Consumer N] ─┘

목표: 10,000/초 = Publisher 3개 × Consumer 8개
```

### 필요 리소스 계산

| 구성 요소 | 현재 | 목표 | 처리량 |
|----------|------|------|--------|
| Publisher | 1개 (1,449/초) | 3개 병렬 | ~4,300/초 |
| Consumer | 1개 (1,400/초) | 8개 병렬 | ~11,200/초 |
| DB 연결 풀 | 10개 | 20개 | 충분 |
| RabbitMQ prefetch | 200 | 500 | 버퍼 여유 |

### 구현 방법 1: Docker Compose Replicas (권장)

**docker-compose.yml 수정:**

```yaml
services:
  tick-writer:
    image: tick-writer:latest
    deploy:
      replicas: 8  # Consumer 8개
    environment:
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
      - DATABASE_URL=postgresql://admin:password123@db:5432/stock_db
      - BATCH_SIZE=500
      - PREFETCH_COUNT=500
    depends_on:
      - rabbitmq
      - db

  kis-publisher:
    image: kis-publisher:latest
    deploy:
      replicas: 3  # Publisher 3개
    environment:
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
```

**장점:**
- 코드 수정 없이 스케일 아웃
- 컨테이너 오케스트레이션으로 관리 용이
- 개별 인스턴스 모니터링 가능

### 구현 방법 2: 애플리케이션 레벨 병렬화

**tick-writer/main.py 수정:**

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class TickWriter:
    def __init__(self, consumer_count: int = 8):
        self.consumer_count = consumer_count
        self.db_pool = None
        self.channel = None

    async def start(self):
        # DB 연결 풀 확장
        self.db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=self.consumer_count * 2,
            max_size=self.consumer_count * 3,
        )

        # RabbitMQ 연결
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self.channel = await connection.channel()
        await self.channel.set_qos(prefetch_count=500)

        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)

        # 다중 Consumer 시작
        consumers = [
            self.consume(queue, consumer_id=i)
            for i in range(self.consumer_count)
        ]

        await asyncio.gather(*consumers)

    async def consume(self, queue, consumer_id: int):
        """개별 Consumer 태스크"""
        buffer = []

        async for message in queue.iterator(no_ack=False):
            try:
                data = json.loads(message.body)
                buffer.append({"data": data, "message": message})

                if len(buffer) >= BATCH_SIZE:
                    await self.save_batch(buffer, consumer_id)
                    buffer = []

            except Exception as e:
                await message.nack(requeue=True)

    async def save_batch(self, buffer, consumer_id: int):
        """배치 저장 (Consumer별 독립 실행)"""
        messages = [item["message"] for item in buffer]
        records = [self.parse_record(item["data"]) for item in buffer]

        try:
            async with self.db_pool.acquire() as conn:
                await conn.executemany(INSERT_QUERY, records)

            # 성공 시 ACK
            for msg in messages:
                await msg.ack()

        except Exception as e:
            # 실패 시 NACK (재큐잉)
            for msg in messages:
                await msg.nack(requeue=True)
            raise
```

**kis-publisher/main.py 수정:**

```python
class KISPublisher:
    def __init__(self, publisher_count: int = 3):
        self.publisher_count = publisher_count
        self.message_queue = asyncio.Queue(maxsize=10000)

    async def start(self):
        connection = await aio_pika.connect_robust(RABBITMQ_URL)

        # 다중 Publisher 채널
        publishers = [
            self.publish_worker(connection, worker_id=i)
            for i in range(self.publisher_count)
        ]

        # WebSocket 수신 + 다중 Publisher
        await asyncio.gather(
            self.receive_from_kis(),
            *publishers
        )

    async def receive_from_kis(self):
        """KIS WebSocket에서 데이터 수신 → 내부 큐에 추가"""
        async for data in self.kis_websocket:
            await self.message_queue.put(data)

    async def publish_worker(self, connection, worker_id: int):
        """개별 Publisher 워커"""
        channel = await connection.channel(publisher_confirms=True)
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.FANOUT, durable=True
        )

        while True:
            data = await self.message_queue.get()

            message = aio_pika.Message(
                body=json.dumps(data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
            )

            try:
                await exchange.publish(message, routing_key="")
            except DeliveryError as e:
                # 실패 로깅
                logger.error(f"Publisher {worker_id} failed: {e}")
```

### 구현 방법 3: Kubernetes HPA

**deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tick-writer
spec:
  replicas: 8
  selector:
    matchLabels:
      app: tick-writer
  template:
    spec:
      containers:
      - name: tick-writer
        image: tick-writer:latest
        resources:
          requests:
            cpu: "250m"
            memory: "256Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: tick-writer-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: tick-writer
  minReplicas: 4
  maxReplicas: 16
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### 성능 튜닝 체크리스트

#### RabbitMQ 설정

```bash
# rabbitmq.conf
# 메모리 한계 증가
vm_memory_high_watermark.relative = 0.6

# 디스크 한계
disk_free_limit.relative = 1.5

# 채널 최대 수
channel_max = 2048
```

#### PostgreSQL/TimescaleDB 설정

```sql
-- postgresql.conf
-- 동시 연결 수 증가
max_connections = 200

-- 공유 버퍼 증가
shared_buffers = 2GB

-- 작업 메모리
work_mem = 64MB

-- 배치 INSERT 최적화
synchronous_commit = off  -- 약간의 데이터 손실 허용 시
```

#### 애플리케이션 설정

| 설정 | 현재 | 권장 (10K/초) |
|------|------|--------------|
| `BATCH_SIZE` | 200 | 500 |
| `PREFETCH_COUNT` | 200 | 500 |
| `DB_POOL_MIN` | 10 | 20 |
| `DB_POOL_MAX` | 20 | 40 |
| `FLUSH_INTERVAL` | 5초 | 2초 |

### 예상 비용 (AWS 기준)

| 구성 요소 | 인스턴스 | 수량 | 월 비용 (예상) |
|----------|---------|------|---------------|
| tick-writer | t3.medium | 8개 | $240 |
| kis-publisher | t3.small | 3개 | $45 |
| RabbitMQ | t3.large | 1개 | $60 |
| TimescaleDB | r6g.large | 1개 | $150 |
| **총합** | | | **~$500/월** |

### 단계별 적용 계획

| 단계 | 작업 | 예상 처리량 | 리스크 |
|------|------|------------|--------|
| 1단계 | Consumer 3개 확장 | 4,000/초 | 낮음 |
| 2단계 | Publisher 2개 추가 | 6,000/초 | 낮음 |
| 3단계 | Consumer 8개 확장 | 10,000/초 | 중간 |
| 4단계 | DB 튜닝 + 모니터링 | 12,000/초 | 낮음 |

---

## 운영 환경 적용 고려사항

### 현재 운영 시스템

| 컴포넌트 | 파일 | 현재 구조 |
|----------|------|-----------|
| kis-publisher | `kis-publisher/main.py` | 단일 Publisher |
| tick-writer | `tick-writer/main.py` | 단일 Consumer |
| tick-broadcaster | `tick_broadcaster.py` | 단일 Consumer |

### 예상 트래픽

| 시간대 | 예상 TPS | 현재 용량 |
|--------|---------|-----------|
| 장중 평상시 | 100~500/초 | ✅ 충분 |
| 장중 급등락 | 1,000~2,000/초 | ⚠️ 경계 |
| 동시호가 | 3,000~5,000/초 | ❌ 부족 |

### 권장 조치

1. **단기 (현재 유지 가능)**
   - 현재 구조로 1,400/초까지 처리 가능
   - 장중 평상시 트래픽 충분히 처리

2. **중기 (스케일 아웃 준비)**
   - tick-writer 인스턴스 3개로 확장 준비
   - Kubernetes HPA 설정 또는 Docker Compose replicas

3. **장기 (아키텍처 개선)**
   - Consumer 다중화
   - DB 배치 크기 동적 조정
   - 파티셔닝 (종목별 분산)

---

## 결론

### 테스트 결과 요약

| 항목 | 결과 |
|------|------|
| 데이터 무결성 | ✅ PASS (0% 손실) |
| 지연 시간 | ✅ PASS (P99 3.11ms) |
| 목표 처리량 | ❌ FAIL (14% 달성) |

### 주요 발견

1. **병목 원인**: 단일 Consumer 구조 + Publisher Confirm 동기 대기
2. **실제 한계**: 현재 구조로 ~1,400/초 (이론적 한계에 근접)
3. **DB는 병목 아님**: 23,700/초 처리 가능

### 권장 사항

1. 현재 트래픽(100~500/초)에는 **현재 구조 충분**
2. 1,000/초 이상 필요 시 **Consumer 다중화** 필수
3. 10,000/초 달성 시 **Publisher 병렬화 + Consumer 10개** 필요

---

## 테스트 환경

```
OS: macOS Darwin 25.2.0
Python: 3.12+
RabbitMQ: 3.13 (Docker)
PostgreSQL: 16 + TimescaleDB (Docker)
라이브러리: aio-pika 9.x, asyncpg 0.x
```

## 테스트 명령

```bash
# 환경변수 설정
export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
export DATABASE_URL="postgresql://admin:password123@localhost:5432/stock_db"

# 스트레스 테스트 실행
cd tests/load
python -c "
import asyncio
from test_full_load import run_full_load_test

asyncio.run(run_full_load_test(
    stock_count=40,
    messages_per_second=10000,
    duration_seconds=30,
    consumer_batch_size=200
))
"
```
