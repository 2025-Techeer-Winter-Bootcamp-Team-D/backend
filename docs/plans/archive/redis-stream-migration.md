# Redis Pub/Sub → Redis Streams 전환 문서

## 목적
실시간 주가 파이프라인에서 **Redis Pub/Sub** 대신 **Redis Streams**를 사용하여
메시지 유실 방지, 재처리 가능성, 소비자 상태 추적을 확보한다.

---

## 1) 배경 지식

### 1.1 Pub/Sub 특징
- **장점**: 매우 단순, 지연이 낮음
- **단점**
  - 구독자가 내려가면 메시지 유실
  - 소비 완료(ACK) 개념 없음
  - 재처리/재전송 불가
  - 적재 실패 시 복구 어려움

### 1.2 Streams 특징
- **메시지 로그** 기반 (XADD)
- **Consumer Group**으로 읽음 (XREADGROUP)
- **ACK/재처리** 가능 (XACK, XPENDING, XCLAIM)
- **보관 정책** 설정 가능 (MAXLEN)
- **복구/재처리**에 강함

### 1.3 전환 이유 (요약)
- 실시간 수집 파이프라인에서 **유실 방지**가 필요
- 적재 실패 시 **재처리**가 필요
- 향후 **여러 소비자 확장** 가능성 고려

---

## 2) 현재 구조 (Pub/Sub)

```
KIS WebSocket
  → kis-publisher (parse)
  → Redis Pub/Sub: stock:realtime:{종목코드}
  → persistence-worker (subscribe)
  → TimescaleDB stock_ticks
```

문제점: 구독자가 재시작되면 해당 구간 메시지 유실.

---

## 3) 목표 구조 (Streams)

```
KIS WebSocket
  → kis-publisher (parse)
  → Redis Stream: stock:realtime
  → persistence-worker (consumer group)
  → TimescaleDB stock_ticks
```

### 3.1 스트림 설계
- **Stream Key**: `stock:realtime`
- **Entry Fields**
  - `stock_code`
  - `symbol`
  - `time`
  - `price`
  - `volume`
- **Retention**
  - XADD MAXLEN으로 제한 (예: 1,000,000)
  - 정책은 운영 환경에 맞춰 조정

### 3.2 Consumer Group
- **Group**: `stock_ticks_ingest`
- **Consumer**: 인스턴스별 고유 이름 (예: hostname)
- **읽기 전략**
  - `XREADGROUP` (block + count)
  - 처리 성공 시 `XACK`
  - 실패 시 재처리(미ACK)

---

## 4) 변경 범위

### 4.1 kis-publisher (발행자)
- **Pub/Sub publish → XADD**
- 기존 채널 포맷 제거, 단일 스트림으로 집계

### 4.2 persistence-worker (소비자)
- **Redis Pub/Sub 구독 → Streams Consumer Group**
- 미ACK 메시지 재처리 로직 추가
- 메시지 ID 기반 중복 방지 고려

### 4.3 subscribe-handler (Django Channels용)
- 별도 Consumer Group: `django_channels_group`
- `XREADGROUP`으로 실시간 데이터 소비
- Django Channels WebSocket으로 클라이언트에게 전송

---

## 5) 세부 구현 계획

### 5.1 kis-publisher 변경
- Redis client로 `XADD stock:realtime * fields...`
- 필드 키는 JSON 직렬화 없이 단순 key/value 사용

### 5.2 persistence-worker 변경
- 시작 시 `XGROUP CREATE stock:realtime stock_ticks_ingest $ MKSTREAM`
- `XREADGROUP GROUP stock_ticks_ingest <consumer> BLOCK 2000 COUNT 200 STREAMS stock:realtime >`
- 처리 성공 → `XACK`
- 실패 시:
  - 로그 남기고 재시도
  - 오래된 PENDING은 `XPENDING` + `XCLAIM`으로 회수

### 5.3 데이터 적재
- 기존 UPSERT 로직은 유지
- 실패 시 ACK하지 않음 → 재처리 가능

---

## 6) 단계별 적용 순서

1. **Redis Streams 기반 publish 추가**
2. **persistence-worker Streams 소비 추가**
3. **Pub/Sub 제거**

---

## 7) 리스크 및 대응

- **Stream 길이 폭증**
  - XADD MAXLEN 설정
- **중복 처리**
  - UPSERT로 중복 방지
  - 필요 시 message_id 저장
- **PENDING 누적**
  - 주기적 재처리(XCLAIM)

---

## 8) 테스트 계획

- **기능 테스트**
  - 단일 메시지 적재/ACK 확인
  - worker 재시작 후 재처리 여부 확인
- **장애 테스트**
  - DB 오류 시 미ACK 유지 확인
  - 재시작 후 재처리 확인

---

## 9) 체크리스트
- [x] kis-publisher XADD 적용
- [x] persistence-worker XREADGROUP 적용
- [x] subscribe-handler XREADGROUP 적용
- [x] Consumer Group 초기화 로직 추가
- [x] Pub/Sub 제거
- [ ] 문서/운영 가이드 업데이트
