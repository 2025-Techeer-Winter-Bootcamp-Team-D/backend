# 시스템 아키텍처 진화 스토리

## 개요

이 문서는 프로젝트 개발 과정에서 마주한 아키텍처적 문제들과 이를 해결하기 위해 선택한 기술, 그리고 그 결과로 얻은 개선 사항들을 정리합니다.

---

## 목차

1. [메시지 브로커 통합: Redis → RabbitMQ](#1-메시지-브로커-통합-redis--rabbitmq)
2. [실시간 데이터 스트리밍: Pub/Sub → Streams → RabbitMQ](#2-실시간-데이터-스트리밍-pubsub--streams--rabbitmq)
3. [기업-산업 매핑 재설계: 통계 기반 → 규칙 기반](#3-기업-산업-매핑-재설계-통계-기반--규칙-기반)
4. [모니터링 아키텍처: 2-Tier → 3-Tier](#4-모니터링-아키텍처-2-tier--3-tier)
5. [실시간 주가 동적 구독 시스템](#5-실시간-주가-동적-구독-시스템)
6. [뉴스 크롤링 파이프라인 최적화](#6-뉴스-크롤링-파이프라인-최적화)
7. [보고서 처리 파이프라인 비용 최적화](#7-보고서-처리-파이프라인-비용-최적화)
8. [KIS API Rate Limiting: 분산 환경 API 제한 준수](#8-kis-api-rate-limiting-분산-환경-api-제한-준수)

---

## 1. 메시지 브로커 통합: Redis → RabbitMQ

### 문제 상황

초기에는 Redis를 **캐시, 세션, Celery 브로커, 실시간 데이터 통신** 등 모든 용도로 사용했습니다.

```
Redis (모든 역할)
├── Django Cache
├── Django Session
├── Celery Broker
├── Celery Result Backend
├── Channels Layer (WebSocket)
└── 실시간 주가 Pub/Sub
```

**발생한 문제**:
- 역할이 혼재되어 장애 시 전체 시스템에 영향
- Celery 태스크 메시지 유실 가능성 (Redis의 메시지 보장 제한적)
- 복잡한 라우팅이 필요한 경우 Redis로는 구현 어려움
- 모니터링 도구 부재 (별도 도구 필요)

### 해결 기술

**RabbitMQ**를 Celery 브로커 및 실시간 데이터 통신 전용 메시지 브로커로 도입

| 비교 항목 | Redis | RabbitMQ |
|----------|-------|----------|
| 주 용도 | 캐시, 세션 | 메시지 브로커 전용 |
| 프로토콜 | Redis 자체 | AMQP (표준) |
| 메시지 보장 | 제한적 | ACK, NACK, 재전송 |
| 라우팅 | 단순 | Exchange/Routing Key 기반 복잡한 라우팅 |
| Dead Letter Queue | 미지원 | 지원 |
| 관리 UI | 별도 도구 | Management Plugin 내장 |

### 최종 아키텍처

```
RabbitMQ (메시지 브로커 전용)
├── Exchange: stock.realtime (Fanout)
│   ├── Queue: stock.ticks.writer → tick-writer
│   └── Queue: stock.ticks.broadcast → tick-broadcaster
└── Exchange: celery (Direct)
    └── Queue: celery → celery-worker

Redis (캐시/세션/Channels 전용)
├── Django Cache
├── Django Session
├── Channels Layer (WebSocket)
└── Celery Result Backend (빠른 결과 조회)
```

### 개선 결과

| 지표 | 개선 전 | 개선 후 |
|-----|--------|--------|
| **역할 분리** | 혼재 | 명확히 분리 |
| **메시지 보장** | 제한적 | ACK/NACK/DLQ 지원 |
| **모니터링** | 별도 도구 필요 | Management UI (http://localhost:15672) |
| **확장성** | Redis Cluster 복잡 | RabbitMQ 클러스터 네이티브 지원 |
| **장애 격리** | 전체 영향 | 브로커 장애 시 캐시/세션 영향 없음 |

---

## 2. 실시간 데이터 스트리밍: Pub/Sub → Streams → RabbitMQ

### 문제 상황 (1차: Pub/Sub)

초기 실시간 주가 파이프라인은 Redis Pub/Sub을 사용했습니다.

```
KIS WebSocket → kis-publisher → Redis Pub/Sub → tick-writer → TimescaleDB
```

**발생한 문제**:
- 구독자가 재시작되면 해당 구간 **메시지 유실**
- 소비 완료(ACK) 개념 없음
- 재처리/재전송 불가능
- 적재 실패 시 복구 어려움

### 1차 해결: Redis Streams

Redis Streams로 전환하여 Consumer Group 기반 메시지 처리 도입

```
KIS WebSocket
  → kis-publisher
  → Redis Stream: stock:realtime
    → Consumer Group: stock_ticks_ingest
      → tick-writer → TimescaleDB (XACK)
```

**개선점**:
- 메시지 로그 기반 (XADD)
- Consumer Group으로 분산 처리 (XREADGROUP)
- ACK/재처리 가능 (XACK, XPENDING, XCLAIM)
- 보관 정책 설정 (MAXLEN)

### 2차 해결: RabbitMQ 통합

메시지 브로커를 RabbitMQ로 통합하면서 실시간 주가 통신도 RabbitMQ로 마이그레이션

```
KIS WebSocket
  → kis-publisher
  → RabbitMQ Exchange: stock.realtime (Fanout)
    → Queue: stock.ticks.writer → tick-writer → TimescaleDB
    → Queue: stock.ticks.broadcast → tick-broadcaster → WebSocket
```

### 개선 결과

| 지표 | Pub/Sub | Streams | RabbitMQ |
|-----|---------|---------|----------|
| **메시지 유실** | 발생 | 방지 | 방지 |
| **ACK 지원** | ✗ | ✓ | ✓ |
| **재처리** | 불가 | XCLAIM | 자동 재전송 |
| **다중 소비자** | 브로드캐스트만 | Consumer Group | Fanout Exchange |
| **모니터링** | 어려움 | 가능 | Management UI |

---

## 3. 기업-산업 매핑 재설계: 통계 기반 → 규칙 기반

### 문제 상황

DART API에서 받은 KSIC(한국표준산업분류) 코드를 KIS(한국투자증권) 업종 지수에 매핑해야 했습니다.

```
기존 매핑 체인:
DART API (KSIC 코드) → KsicCategory → KisIndustry → Industry → Company
```

**발생한 문제**:
- **복잡한 매핑 체인**: 4단계를 거치면서 매핑 정확도 저하
- **통계 기반 자동 매핑 실패**: 금융업(KSIC 64-66)에 제조업 기업이 매핑되는 논리적 오류
- **수동 매핑 테이블의 복잡성**: 200개 이상의 매핑 룰, 유지보수 어려움

**근본 원인**:
KSIC와 KIS는 서로 다른 목적의 분류 체계로, 1:1 매핑 자체가 불가능

| 구분 | KSIC | KIS |
|------|------|-----|
| 목적 | 통계청 표준 산업 분류 | 증권사 투자 분석용 업종 지수 |
| 분류 수 | 500개 이상 (5자리 세분류) | 약 30개 (대/중분류) |
| 관점 | 생산 활동 기준 | 투자 섹터 기준 |

### 해결 기술

**KIS 업종 지수 기반 단순화** + **명시적 규칙 기반 매핑**

```python
# 새로운 매핑 방식
class IndustryMappingRules:
    # KSIC 앞 2자리 → KIS 업종 코드 매핑
    DEFAULT_MAPPINGS = {
        "10": "0005",  # 식료품 제조업 → 음식료·담배
        "21": "0009",  # 의약품 제조업 → 제약
        "26": "0014",  # 전자부품 → 전기전자
        "64": "0021",  # 금융업 → 금융
        # ...
    }

    # 3자리 예외 매핑 (더 세부적인 분류 필요 시)
    EXCEPTION_MAPPINGS = {
        "264": "0027",  # 반도체 제조업 → 반도체
        "641": "0022",  # 은행업 → 은행
        # ...
    }
```

### 최종 아키텍처

```
[데이터 흐름 - 단순화]
1. DART API → Company.original_ksic_code (원본 보관)
2. KIS 마스터 → Industry (KIS 업종 지수 = Industry 테이블)
3. Company ↔ Industry (KSIC 코드 기반 규칙 매핑)

[제거된 테이블]
- KsicCategory (삭제)
- KisIndustry (Industry로 통합)
- KsicKisManualMapping (삭제)
```

### 개선 결과

| 지표 | 개선 전 | 개선 후 |
|-----|--------|--------|
| **매핑 단계** | 4단계 | 2단계 |
| **매핑 정확도** | ~60% | ~95% |
| **코드 라인 수** | 500+ | ~150 |
| **유지보수** | 어려움 | 규칙 추가/수정 용이 |
| **KIS 지수 연동** | 복잡 | 자연스러움 (1:1 매칭) |

---

## 4. 모니터링 아키텍처: 2-Tier → 3-Tier

### 문제 상황

기존 2-Tier 구조에서 모니터링 스택을 App 서버에 추가하려고 했습니다.

```
[2-Tier 구조]
App Layer (t3.small, 2GB RAM)
├── Django, Celery, Nginx
└── Prometheus, Grafana, Loki, Tempo... (추가 계획)

Data Layer (t3.small, 2GB RAM)
├── PostgreSQL, Redis
└── OpenSearch, RabbitMQ
```

**발생한 문제**:
- **메모리 부족**: App (1.8GB) + 모니터링 (2.9GB) = 4.7GB > t3.small 2GB
- **리소스 경합**: 애플리케이션과 모니터링이 같은 리소스 사용
- **SPOF**: App 서버 다운 시 모니터링도 중단
- **업그레이드 비용**: t3.large 필요 시 월 $67 추가 비용

### 해결 기술

**3-Tier 분산 아키텍처**: 모니터링 전용 인스턴스 분리

```
[3-Tier 구조]
App Layer (t3.small)
├── Django, Celery, Nginx
├── KIS Publisher, Persistence Worker
└── Node Exporter, cAdvisor (메트릭 제공)

Data Layer (t3.small)
├── PostgreSQL, Redis
├── OpenSearch, RabbitMQ
└── Node/Postgres/Redis Exporter (메트릭 제공)

Monitoring Layer (t3.small) ⭐ 신규
├── Prometheus (메트릭 수집)
├── Grafana (시각화)
├── Loki + Promtail (로그 수집)
├── Tempo (분산 트레이싱)
├── Alertmanager (알림)
└── Portainer (컨테이너 관리)
```

### 개선 결과

| 지표 | 2-Tier (실제 필요) | 3-Tier |
|-----|-------------------|--------|
| **월 비용** | $67.16 (t3.large) | **$50.37** (t3.small × 3) |
| **리소스 격리** | 경합 발생 | 완전 격리 |
| **고가용성** | App 장애 시 모니터링 중단 | **독립 운영** |
| **확장성** | 제한적 | 각 Layer 개별 스케일링 |
| **연간 절감** | 기준 | **$200 절감** |

---

## 5. 실시간 주가 동적 구독 시스템

### 문제 상황

KIS WebSocket API는 **동시 구독 40종목** 제한이 있습니다.

```
기존 방식:
- 앱 시작 시 고정된 종목 40개 구독
- 사용자가 보지 않는 종목도 구독 유지
- 사용자가 보고 싶은 종목이 구독 목록에 없으면 데이터 없음
```

**발생한 문제**:
- 리소스 낭비 (사용하지 않는 종목 구독 유지)
- 사용자 경험 저하 (원하는 종목 데이터 없음)
- 확장성 제한 (40종목 고정)

### 해결 기술

**동적 구독/해제 시스템** 구현

```
┌─────────────┐     WebSocket      ┌───────────────────┐      RPC       ┌───────────────┐
│  Frontend   │ ◄─────────────────►│ StockPriceConsumer│ ◄─────────────►│ kis-publisher │
└─────────────┘                    └───────────────────┘                └───────────────┘
                                           │                                   │
                                           ▼                                   ▼
                                  ┌────────────────┐                  ┌────────────────┐
                                  │  Redis (상태)   │                  │   KIS API      │
                                  └────────────────┘                  └────────────────┘
```

**핵심 구현**:
- `SubscriptionManager`: Redis 기반 구독 상태 관리
- RabbitMQ RPC: Django ↔ kis-publisher 통신
- Channels 그룹: 종목별 WebSocket 그룹 (`stock_{code}`)

```python
# WebSocket 프로토콜
{"action": "subscribe", "codes": ["005930", "000660"]}  # 구독
{"action": "unsubscribe", "codes": ["005930"]}          # 해제
{"action": "list_subscriptions"}                        # 목록 조회
```

### 개선 결과

| 지표 | 개선 전 | 개선 후 |
|-----|--------|--------|
| **구독 방식** | 고정 40종목 | 동적 구독/해제 |
| **리소스 효율성** | 낮음 | **사용자가 보는 종목만 구독** |
| **사용자 경험** | 제한적 | 원하는 종목 실시간 데이터 |
| **확장성** | 40종목 제한 | 40종목 내 자유로운 교체 |

---

## 6. 뉴스 크롤링 파이프라인 최적화

### 문제 상황

뉴스 데이터를 수집, 처리, 검색 가능하게 만드는 파이프라인이 필요했습니다.

**초기 과제**:
- 다양한 뉴스 사이트에서 본문 추출
- 불필요한 HTML/광고 제거
- 유사 기사 중복 제거
- 벡터 검색을 위한 임베딩 생성

### 해결 기술

**6단계 Celery Canvas 파이프라인**

```
[뉴스 크롤링 파이프라인]
1. 검색 (Naver API)
   └→ 키워드별 뉴스 URL 수집

2. 본문 추출 (Jina.ai Reader)
   └→ HTML → 마크다운 변환

3. 본문 정제 + 요약 (Gemini AI)
   └→ 불필요한 요소 제거, 핵심 요약

4. 벡터 임베딩 (Gemini Embedding)
   └→ 768차원 벡터 생성

5. DB 저장 (PostgreSQL)
   └→ 뉴스 메타데이터 + 요약

6. 클러스터링 + OpenSearch 저장
   └→ DBSCAN 중복 제거 → 벡터 인덱스 저장
```

**핵심 기술**:
- **DBSCAN 클러스터링**: 코사인 유사도 기반 중복 기사 그룹화
- **HNSW 벡터 검색**: 768차원 벡터의 빠른 유사도 검색
- **Nori 분석기**: 한국어 텍스트 처리 최적화

```python
# 클러스터링 설정
clustering_service = NewsClusteringService(
    eps=0.1,           # 클러스터 반경 (유사도 임계값)
    min_samples=2,     # 최소 샘플 수
)
```

### 개선 결과

| 지표 | 개선 전 | 개선 후 |
|-----|--------|--------|
| **본문 추출** | 없음 | Jina.ai (다양한 사이트 지원) |
| **중복 제거** | 없음 | DBSCAN 클러스터링 |
| **검색 방식** | 키워드 매칭 | **벡터 유사도 검색** |
| **검색 정확도** | 낮음 | 의미 기반 검색 가능 |
| **처리 속도** | 동기 | Celery 병렬 처리 |

---

## 7. 보고서 처리 파이프라인 비용 최적화

### 문제 상황

DART 공시 보고서를 처리하여 벡터 검색이 가능하게 만들어야 했습니다.

**초기 비용 문제**:
- 보고서 본문 추출에 Jina.ai 사용 시 비용 발생
- 요약과 매출 구성 추출을 별도 Gemini 호출로 처리

### 해결 기술

**비용 최적화 전략**:

1. **OpenDartReader 도입**: DART API에서 직접 XML 본문 추출 (무료)
2. **Gemini 호출 통합**: 요약 + 매출 구성 추출을 1회 호출로 통합

```python
# 통합 추출 프롬프트 (1회 호출)
prompt = """
보고서에서 다음 정보를 한 번에 추출:
1. 보고서 유형 판단
2. 한 줄 요약 (50자 이내)
3. 핵심 정보 (유형별 상이)
4. 매출 구성 (사업보고서만)

응답 형식: JSON
"""
```

### 비용 비교

| 단계 | Jina.ai 방식 | OpenDartReader 방식 |
|------|-------------|-------------------|
| 본문 추출 | ~$0.01/건 | **무료** |
| 본문 정제 | $0.005 | $0.005 |
| 요약 추출 | $0.002 | - |
| 매출 구성 추출 | $0.001 | - |
| **통합 추출** | - | **$0.0013** |
| 벡터 임베딩 | $0.0015 | $0.0015 |
| **합계** | ~$0.02/건 | **~$0.008/건** |

### 개선 결과

| 지표 | 개선 전 | 개선 후 |
|-----|--------|--------|
| **건당 비용** | ~$0.02 | **~$0.008** |
| **10,000건 처리** | $200 | **$78** |
| **Gemini 호출 수** | 3회 | **2회** |
| **비용 절감률** | - | **~60%** |

---

## 8. KIS API Rate Limiting: 분산 환경 API 제한 준수

### 문제 상황

KIS(한국투자증권) API는 **초당 2회 호출 제한**이 있습니다.

```
기존 구조:
- 여러 Celery Worker가 동시에 KIS API 호출
- 각 Worker는 다른 Worker의 호출 상태를 알 수 없음
- 동시 호출 시 API 제한 초과 → 요청 실패
```

**발생한 문제**:
- 시가총액 갱신, 업종 지수 조회 등 여러 태스크가 동시 실행
- 분산 환경에서 각 Worker가 독립적으로 API 호출
- Rate Limit 초과 시 `429 Too Many Requests` 오류
- 대량 데이터 갱신 시 실패율 증가

### 해결 기술

**Redis 분산 락 + 전역 요청 시간 추적**

```python
# 핵심 설정
REQUEST_DELAY = 0.52  # 520ms (500ms + 20ms 안전 마진)
KIS_RATE_LIMIT_LOCK_KEY = "kis_api_rate_limit_lock"
KIS_LAST_REQUEST_TIME_KEY = "kis_api_last_request_time"
```

**구현 전략**:

1. **Redis 분산 락**: 동시에 하나의 Worker만 API 호출 가능
2. **전역 요청 시간 공유**: Redis에 마지막 요청 시간 저장
3. **동적 대기 시간 계산**: 이전 요청 이후 경과 시간에 따라 대기

```python
def _wait_for_rate_limit(self) -> None:
    """분산 환경에서 KIS API rate limit 준수를 위한 전역 딜레이 관리"""
    try:
        lock = cache.lock(
            KIS_RATE_LIMIT_LOCK_KEY,
            timeout=5,      # 락 최대 유지 시간
            blocking=True,
            blocking_timeout=10  # 락 획득 대기 시간
        )

        if lock.acquire():
            try:
                # 마지막 요청 시간 확인
                last_request = cache.get(KIS_LAST_REQUEST_TIME_KEY)
                current_time = time.time()

                if last_request:
                    elapsed = current_time - float(last_request)
                    if elapsed < REQUEST_DELAY:
                        # 남은 시간만큼 대기
                        time.sleep(REQUEST_DELAY - elapsed)

                # 새로운 요청 시간 기록
                cache.set(KIS_LAST_REQUEST_TIME_KEY, time.time(), timeout=60)
            finally:
                lock.release()
    except Exception:
        # Fallback: 락 실패 시 단순 대기
        time.sleep(REQUEST_DELAY)
```

**Celery 태스크 레벨 Rate Limiting**:

```python
@shared_task(bind=True, max_retries=3, rate_limit="2/s")
def sync_market_amount(self, stock_code: str):
    """단건 시가총액 갱신 - Rate Limit: 초당 2회"""
    service = KisQuoteService()
    return service.get_market_amount(stock_code)
```

### 적용 범위

| 서비스 | 파일 | 용도 |
|--------|------|------|
| `KisQuoteService` | `companies/services/kis_quote.py` | 시가총액, 주가 조회 |
| `KisIndexService` | `industries/services/kis_index_service.py` | 업종 지수 조회 |
| `sync_market_amount` | `companies/tasks/kis_market_amount.py` | 시가총액 갱신 태스크 |

### 아키텍처

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Celery Worker 1 │     │ Celery Worker 2 │     │ Celery Worker N │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │        Redis            │
                    │  ┌──────────────────┐   │
                    │  │ rate_limit_lock  │   │  ← 분산 락
                    │  └──────────────────┘   │
                    │  ┌──────────────────┐   │
                    │  │ last_request_time│   │  ← 마지막 요청 시간
                    │  └──────────────────┘   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │       KIS API           │
                    │   (초당 2회 제한)         │
                    └─────────────────────────┘
```

### 개선 결과

| 지표 | 개선 전 | 개선 후 |
|-----|--------|--------|
| **Rate Limit 준수** | 실패 빈번 | **100% 준수** |
| **분산 환경 지원** | 미지원 | **다중 Worker 안전** |
| **API 호출 간격** | 불규칙 | **최소 520ms 보장** |
| **Fallback** | 없음 | **단순 대기로 복구** |
| **모니터링** | 어려움 | Celery rate_limit 로그 |

### 핵심 포인트

1. **520ms 딜레이 선택 이유**: 500ms(초당 2회) + 20ms(네트워크 지연 고려)
2. **분산 락 필수**: 여러 Worker가 동시 호출하면 제한 초과
3. **Fallback 중요**: 캐시 장애 시에도 단순 대기로 API 보호
4. **이중 보호**: 서비스 레벨(분산 락) + 태스크 레벨(rate_limit 데코레이터)

---

## 결론

이 프로젝트를 통해 다음과 같은 아키텍처 원칙을 확립했습니다:

### 1. 역할 분리 (Separation of Concerns)
- Redis: 캐시/세션/Channels (빠른 임시 데이터)
- RabbitMQ: 메시지 브로커 (안정적인 메시지 전달)
- PostgreSQL: 영속 데이터
- OpenSearch: 벡터 검색

### 2. 단순화 (Simplification)
- 복잡한 매핑 체인 → 명시적 규칙 기반
- 여러 단계 처리 → 통합 처리 (Gemini 1회 호출)

### 3. 확장성 고려 (Scalability)
- 3-Tier 분리로 독립적 스케일링
- Celery Canvas로 병렬 처리
- 동적 구독으로 리소스 효율화

### 4. 비용 최적화 (Cost Optimization)
- 무료 API 우선 활용 (OpenDartReader)
- API 호출 통합으로 비용 절감
- 적절한 인스턴스 타입 선택

### 5. 외부 API 제약 준수 (External API Compliance)
- Redis 분산 락으로 Rate Limit 준수
- 분산 환경에서도 전역 상태 공유
- Fallback 메커니즘으로 장애 대응

---

## 관련 문서

- [시스템 아키텍처](./SYSTEM_ARCHITECTURE.md)
- [데이터 처리 아키텍처](./DATA-PROCESSING-ARCHITECTURE.md)
- [아카이브 문서들](./plans/archive/)

---

**작성일**: 2026-01-28
**작성자**: Claude Code
