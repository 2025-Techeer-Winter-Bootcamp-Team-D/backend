# 메시지 브로커 통합: Redis → RabbitMQ 마이그레이션 계획

## 목적
프로젝트의 모든 메시지 브로커를 **RabbitMQ**로 통합하여 단일 메시지 인프라를 구축하고,
**Redis**는 캐시/세션/Channels Layer 전용으로 역할을 명확히 분리한다.

---

## 1) 배경 지식

### 1.1 현재 메시지 브로커 사용 현황

| 시스템 | 현재 브로커 | 용도 | 전환 대상 |
|--------|-------------|------|-----------|
| **실시간 주가 통신** | Redis Streams | kis-publisher → tick-writer, tick-broadcaster | ✅ **RabbitMQ** |
| **Celery 태스크 큐** | Redis | 백그라운드 작업 큐 (뉴스 크롤링, DART 동기화 등) | ✅ **RabbitMQ** |
| **Celery Result Backend** | Redis | 작업 결과 저장 | ✅ **Redis 유지** |
| **Django Cache** | Redis | API 응답, 쿼리 캐싱 | ✅ **Redis 유지** |
| **Django Session** | Redis | 사용자 세션 | ✅ **Redis 유지** |
| **Django Channels Layer** | Redis | WebSocket 통신 | ✅ **Redis 유지** |

### 1.2 Redis vs RabbitMQ

| 항목 | Redis | RabbitMQ |
|------|-------|----------|
| **주 용도** | 캐시, 세션, Pub/Sub | 메시지 큐/브로커 전용 |
| **프로토콜** | Redis 프로토콜 | AMQP (표준) |
| **메시지 보장** | ACK 지원 (Streams) | ACK, NACK, 재전송 |
| **라우팅** | 단순 | 복잡한 라우팅 (Exchange, Routing Key) |
| **Dead Letter Queue** | 미지원 | 지원 |
| **관리 UI** | 별도 도구 필요 | Management Plugin 내장 |
| **클러스터링** | Cluster 복잡 | 네이티브 지원 |

### 1.3 전환 이유

#### 1.3.1 실시간 주가 통신 (Redis Streams → RabbitMQ)

1. **유연한 라우팅**: Fanout Exchange로 다중 Queue 브로드캐스트
2. **표준 프로토콜**: AMQP 사용으로 에코시스템 풍부
3. **모니터링**: Management UI로 실시간 모니터링
4. **확장성**: 클러스터링으로 고가용성 구성

#### 1.3.2 Celery (Redis → RabbitMQ)

1. **단일 브로커 통합**: RabbitMQ 하나로 모든 메시지 처리
2. **Celery 공식 지원**: RabbitMQ는 Celery의 권장 브로커
3. **작업 우선순위**: Priority Queue 지원
4. **Dead Letter Queue**: 실패한 작업 관리 용이
5. **라우팅 유연성**: 작업별 Queue 분리 가능

#### 1.3.3 Redis 역할 명확화

**RabbitMQ로 전환 후 Redis 역할**:
- ✅ **Cache**: API 응답, 쿼리 결과 캐싱 (빠른 응답 속도)
- ✅ **Session**: 사용자 로그인 세션 (자동 만료 TTL)
- ✅ **Channels Layer**: WebSocket 통신 (Pub/Sub 패턴 최적화)
- ✅ **Celery Result Backend**: 작업 결과 저장 (빠른 조회)

**메시지 처리는 RabbitMQ로 완전 이관**:
- ✅ 실시간 주가 메시징
- ✅ Celery 태스크 큐

---

## 2) 현재 구조

### 2.1 실시간 주가 통신 (Redis Streams)

```
KIS WebSocket
  → kis-publisher
  → Redis Stream: stock:realtime
    → Consumer Group 1: stock_ticks_ingest
      → tick-writer → TimescaleDB
    → Consumer Group 2: django_channels_group
      → tick-broadcaster → Django Channels → WebSocket 클라이언트
```

### 2.2 Celery 백그라운드 작업 (Redis)

```
Django App / Management Command
  → Celery Task (apply_async)
  → Redis Queue (celery)
    → Celery Worker
      → 작업 실행 (뉴스 크롤링, DART 동기화 등)
      → Redis Result Backend (결과 저장)
```

**Celery 태스크 종류**:
- **indices**: 코스피/코스닥 지수 동기화
- **news**: 뉴스 크롤링, 본문 추출, 정제, 요약, 임베딩, 클러스터링
- **companies**: DART 동기화, 재무지표 계산, 시가총액, 순위, 보고서 처리
- **core**: 주가 동기화, yfinance 데이터 수집

---

## 3) 목표 구조 (RabbitMQ)

### 3.1 실시간 주가 통신 (RabbitMQ)

```
KIS WebSocket
  → kis-publisher
  → RabbitMQ Exchange: stock.realtime (Fanout)
    → Queue 1: stock.ticks.persistence
      → tick-writer → TimescaleDB
    → Queue 2: stock.ticks.channels
      → tick-broadcaster → Django Channels → WebSocket 클라이언트
```

### 3.2 Celery 백그라운드 작업 (RabbitMQ)

```
Django App / Management Command
  → Celery Task (apply_async)
  → RabbitMQ Exchange: celery (Default Direct Exchange)
    → Queue: celery (Default Queue)
      → Celery Worker
        → 작업 실행
        → Redis Result Backend (결과 저장)
```

### 3.3 RabbitMQ 토폴로지

| Exchange | Type | Queue | Consumer | 용도 |
|----------|------|-------|----------|------|
| `stock.realtime` | Fanout | `stock.ticks.persistence` | tick-writer | TimescaleDB 적재 |
| `stock.realtime` | Fanout | `stock.ticks.channels` | tick-broadcaster | WebSocket 브로드캐스트 |
| `celery` (default) | Direct | `celery` (default) | celery-worker | Celery 태스크 처리 |

---

## 4) 변경 범위

### 4.1 실시간 주가 통신 (✅ 완료)

- docker-compose.yml에 RabbitMQ 서비스 추가
- kis-publisher → RabbitMQ 전환
- tick-writer → RabbitMQ 전환
- tick-broadcaster → RabbitMQ 전환

### 4.2 Celery (신규 작업)

#### 4.2.1 config/settings.py

**변경 전**:
```python
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
```

**변경 후**:
```python
# RabbitMQ를 Celery 브로커로 사용
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", RABBITMQ_URL)

# Redis는 Result Backend로만 사용 (빠른 결과 조회)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
```

#### 4.2.2 docker-compose.yml

**celery-worker, celery-beat, celery-flower 환경변수 변경**:
```yaml
environment:
  - CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672/
  - CELERY_RESULT_BACKEND=redis://redis:6379/0
  - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
depends_on:
  rabbitmq:
    condition: service_healthy
```

---

## 5) 구현 계획

### Phase 1: 실시간 주가 통신 (✅ 완료)

1. ✅ docker-compose.yml에 RabbitMQ 서비스 추가
2. ✅ kis-publisher → RabbitMQ 전환
3. ✅ tick-writer → RabbitMQ 전환
4. ✅ tick-broadcaster → RabbitMQ 전환
5. ✅ 테스트 완료

**테스트 결과**:
- RabbitMQ Exchange: `stock.realtime` (Fanout) 생성 완료
- Queue: `stock.ticks.persistence` (1 consumer), `stock.ticks.channels` (1 consumer)
- kis-publisher: 메시지 발행 정상
- tick-writer: DB 저장 정상 (150+ messages processed)
- tick-broadcaster: RabbitMQ 연결 정상

### Phase 2: Celery → RabbitMQ 전환 (✅ 완료)

#### Step 1: Django Settings 변경
1. `config/settings.py` 수정
   - `CELERY_BROKER_URL`을 RabbitMQ로 변경
   - `CELERY_RESULT_BACKEND`는 Redis 유지
   - `RABBITMQ_URL` 환경변수 추가

#### Step 2: docker-compose.yml 변경
1. `celery-worker`, `celery-beat`, `celery-flower` 서비스 환경변수 변경
2. `rabbitmq` 의존성 추가

#### Step 3: 서비스 재시작
1. Celery 서비스 중단
2. Django 앱 재시작 (settings.py 변경 반영)
3. Celery 서비스 재시작

#### Step 4: 테스트
1. Celery Worker 로그 확인
2. RabbitMQ Management UI에서 `celery` Queue 확인
3. 테스트 태스크 실행 (예: `sync_indices_daily`)
4. 작업 결과 확인

---

## 6) 테스트 계획

### 6.1 Celery 기능 테스트

1. **Worker 연결 테스트**
   ```bash
   docker-compose logs celery-worker | grep -i rabbitmq
   ```

2. **Queue 생성 테스트**
   - RabbitMQ Management UI (http://localhost:15672)
   - Queue `celery` 생성 확인

3. **태스크 실행 테스트**
   ```bash
   docker-compose exec app python manage.py shell
   ```
   ```python
   from indices.tasks import sync_indices_daily
   result = sync_indices_daily.delay()
   print(result.id)
   ```

4. **Result Backend 테스트**
   ```python
   from celery.result import AsyncResult
   result = AsyncResult(task_id)
   print(result.status)  # SUCCESS, FAILURE, PENDING
   ```

---

## 7) 체크리스트

### Phase 1: 실시간 주가 통신 (✅ 완료)
- [x] docker-compose.yml에 RabbitMQ 서비스 추가
- [x] kis-publisher → RabbitMQ 전환
- [x] tick-writer → RabbitMQ 전환
- [x] tick-broadcaster → RabbitMQ 전환
- [x] 테스트 완료

### Phase 2: Celery → RabbitMQ 전환 (✅ 완료)
- [x] config/settings.py 수정
  - [x] CELERY_BROKER_URL → RabbitMQ
  - [x] RABBITMQ_URL 추가
- [x] docker-compose.yml 수정
  - [x] celery-worker 환경변수 변경
  - [x] celery-beat 환경변수 변경
  - [x] celery-flower 환경변수 변경
  - [x] app 환경변수 변경
- [x] 서비스 재시작
- [x] Celery Worker 로그 확인
- [x] RabbitMQ Queue 확인
- [x] 테스트 태스크 실행
- [x] Result Backend(Redis) 확인

---

## 8) 최종 아키텍처

### 8.1 RabbitMQ 역할

```
RabbitMQ (메시지 브로커 전용)
├── Exchange: stock.realtime (Fanout)
│   ├── Queue: stock.ticks.persistence → tick-writer
│   └── Queue: stock.ticks.channels → tick-broadcaster
└── Exchange: celery (Direct)
    └── Queue: celery → celery-worker
```

### 8.2 Redis 역할

```
Redis (캐시/세션/Channels 전용)
├── Cache (django.core.cache.backends.redis.RedisCache)
│   └── API 응답, 쿼리 결과 캐싱
├── Session (django.contrib.sessions.backends.cache)
│   └── 사용자 로그인 세션
├── Channels Layer (channels_redis.core.RedisChannelLayer)
│   └── WebSocket 연결 간 통신
└── Celery Result Backend
    └── 작업 결과 저장 (빠른 조회)
```

---

**작성일**: 2026-01-23
**작성자**: Claude Code
**버전**: 2.0 (Celery 통합)
