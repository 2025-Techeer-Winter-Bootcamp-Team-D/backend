# Celery Broker: Redis → RabbitMQ 전환 문서

## 목적
Celery 태스크 브로커를 **Redis**에서 **RabbitMQ**로 변경하여
메시지 브로커의 역할 분리와 안정성을 확보한다.

---

## 1) 배경 지식: RabbitMQ

### 1.1 RabbitMQ란?
- **AMQP(Advanced Message Queuing Protocol)** 기반의 메시지 브로커
- Erlang으로 작성되어 높은 안정성과 동시성 처리
- 엔터프라이즈 환경에서 널리 사용되는 메시지 큐 시스템

### 1.2 핵심 개념

| 개념 | 설명 |
|------|------|
| **Producer** | 메시지를 발행하는 주체 (Celery 클라이언트) |
| **Exchange** | 메시지를 받아 Queue에 라우팅하는 라우터 |
| **Queue** | 메시지가 저장되는 버퍼 |
| **Consumer** | Queue에서 메시지를 소비하는 주체 (Celery Worker) |
| **Binding** | Exchange와 Queue를 연결하는 규칙 |

### 1.3 Exchange 타입

| 타입 | 라우팅 방식 |
|------|------------|
| **Direct** | routing_key가 정확히 일치하는 Queue로 전달 |
| **Fanout** | 연결된 모든 Queue에 브로드캐스트 |
| **Topic** | 패턴 매칭 (*.error, logs.#) |
| **Headers** | 헤더 속성 기반 라우팅 |

Celery는 기본적으로 **Direct Exchange**를 사용함.

### 1.4 메시지 흐름

```
Producer (Django)
    ↓
  Exchange
    ↓ (routing_key 기반)
  Queue (celery, celery.priority 등)
    ↓
Consumer (Celery Worker)
```

---

## 2) Redis vs RabbitMQ 비교

| 항목 | Redis | RabbitMQ |
|------|-------|----------|
| **주 용도** | 캐시, 세션, 임시 데이터 | 메시지 브로커 전용 |
| **프로토콜** | 자체 프로토콜 | AMQP (표준) |
| **메시지 보장** | 제한적 | ACK, Nack, 재전송 |
| **라우팅** | 단순 (채널/키) | 복잡한 라우팅 가능 |
| **클러스터링** | 복잡 | 네이티브 지원 |
| **모니터링** | 별도 도구 필요 | 관리 UI 내장 |
| **메모리 사용** | 효율적 | 상대적으로 높음 |

### 2.1 전환 이유

1. **역할 분리**
   - Redis: 캐시 + Redis Streams (실시간 주가)
   - RabbitMQ: Celery 태스크 브로커 전용

2. **메시지 보장 강화**
   - RabbitMQ는 메시지 영속성, ACK, Dead Letter Queue 등 지원
   - 태스크 유실 방지

3. **모니터링**
   - RabbitMQ Management UI로 큐 상태, 메시지 흐름 시각화
   - http://localhost:15672 (기본 포트)

4. **확장성**
   - RabbitMQ 클러스터링으로 고가용성 구성 가능

---

## 3) 현재 구조

```
Django App
  → task.delay()
  → Redis (CELERY_BROKER_URL=redis://redis:6379/0)
  → Celery Worker
```

### 3.1 현재 설정 위치
- `docker-compose.yml`: CELERY_BROKER_URL 환경변수
- `config/settings.py`: CELERY_BROKER_URL 설정
- `config/celery.py`: Celery 앱 설정

---

## 4) 목표 구조

```
Django App
  → task.delay()
  → RabbitMQ (amqp://guest:guest@rabbitmq:5672//)
  → Celery Worker
```

---

## 5) 변경 범위

### 5.1 docker-compose.yml
- RabbitMQ 서비스 추가
- CELERY_BROKER_URL 환경변수 변경
- CELERY_RESULT_BACKEND은 Redis 유지 (결과 저장용)

### 5.2 config/settings.py
- CELERY_BROKER_URL 변경
- RabbitMQ 관련 설정 추가 (선택)

### 5.3 requirements.txt
- 의존성 확인 (celery는 이미 amqp 지원)

---

## 6) 세부 구현 계획

### 6.1 docker-compose.yml 변경

```yaml
services:
  rabbitmq:
    image: rabbitmq:3-management
    container_name: rabbitmq
    ports:
      - "5672:5672"    # AMQP 포트
      - "15672:15672"  # Management UI 포트
    environment:
      - RABBITMQ_DEFAULT_USER=guest
      - RABBITMQ_DEFAULT_PASS=guest
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmqctl", "status"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  rabbitmq_data:
```

### 6.2 환경변수 변경

| 서비스 | 변경 전 | 변경 후 |
|--------|---------|---------|
| celery-worker | `redis://redis:6379/0` | `amqp://guest:guest@rabbitmq:5672//` |
| celery-beat | `redis://redis:6379/0` | `amqp://guest:guest@rabbitmq:5672//` |
| backend | `redis://redis:6379/0` | `amqp://guest:guest@rabbitmq:5672//` |

### 6.3 CELERY_RESULT_BACKEND
- Redis 유지: `redis://redis:6379/0`
- 태스크 결과는 Redis에 저장 (캐시 역할)

---

## 7) 단계별 적용 순서

1. **docker-compose.yml에 RabbitMQ 서비스 추가**
2. **CELERY_BROKER_URL 환경변수 변경**
3. **서비스 재시작 및 테스트**
4. **RabbitMQ Management UI 접속 확인**

---

## 8) 리스크 및 대응

- **연결 실패**
  - healthcheck로 RabbitMQ 준비 상태 확인
  - depends_on + condition: service_healthy

- **메모리 사용량 증가**
  - RabbitMQ는 Redis보다 메모리 사용량 높음
  - 필요시 메모리 제한 설정

- **기존 태스크 유실**
  - 전환 전 기존 Redis 큐 비우기 (태스크 완료 대기)

---

## 9) 테스트 계획

- **연결 테스트**
  - Celery Worker가 RabbitMQ에 연결되는지 확인
- **태스크 실행 테스트**
  - 간단한 태스크 호출 후 정상 실행 확인
- **Management UI 테스트**
  - http://localhost:15672 접속
  - Queue, Exchange 상태 확인

---

## 10) 체크리스트

- [ ] docker-compose.yml에 RabbitMQ 서비스 추가
- [ ] CELERY_BROKER_URL 환경변수 변경 (모든 서비스)
- [ ] depends_on 설정 업데이트
- [ ] 서비스 재시작 및 연결 테스트
- [ ] Management UI 접속 확인
