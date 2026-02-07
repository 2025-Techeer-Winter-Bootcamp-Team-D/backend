# 모니터링 시스템 구축 계획

## 문서 정보
- **작성일**: 2026-01-19
- **버전**: 1.1
- **최종 수정**: 2026-01-19
- **목적**: 서비스 운영 및 개발을 위한 포괄적인 모니터링 시스템 구축

## ✅ 구축 진행 상태

### 완료된 Phase
- ✅ **Phase 0: 긴급 문제 해결** (2026-01-19 완료)
  - Django 메트릭 수집 활성화
  - cAdvisor 대시보드 구축

- 🔄 **Phase 1: 기본 모니터링 강화** (진행 중 - 대시보드 구축 완료)
  - ✅ Grafana Provisioning 설정
  - ✅ 5개 대시보드 배포 완료
  - ⏳ AlertManager 및 알림 규칙 (다음 단계)

### 배포된 대시보드
1. **Docker + System Dashboard** - 컨테이너 리소스 모니터링
2. **Django Prometheus** - Django 애플리케이션 성능
3. **PostgreSQL Database** - 데이터베이스 성능
4. **Redis Dashboard** - Redis 캐시 서버
5. **Node Exporter Full** - 시스템 리소스

### 다음 단계
- AlertManager 설치 및 설정
- 기본 알림 규칙 작성 (Critical/High 우선순위)
- Slack 알림 채널 설정

---

## 1. 개요

### 1.1 목적
본 문서는 Django 기반 금융 데이터 플랫폼의 안정적인 운영과 효율적인 개발을 위한 모니터링 시스템 구축 계획을 정의합니다.

### 1.2 목표
- **가용성**: 99.9% 이상의 서비스 업타임 달성
- **성능**: 실시간 성능 문제 감지 및 대응
- **안정성**: 장애 발생 시 5분 이내 감지 및 알림
- **최적화**: 데이터 기반 리소스 사용 최적화
- **개발 효율**: 개발 중 성능 이슈 사전 파악

### 1.3 범위
- 인프라 모니터링 (컨테이너, 호스트)
- 애플리케이션 모니터링 (Django, Celery)
- 데이터베이스 모니터링 (PostgreSQL/TimescaleDB, Redis)
- 비즈니스 메트릭 모니터링
- 로그 수집 및 분석
- 알림 및 경보 시스템

---

## 2. 현재 인프라 현황

### 2.1 이미 구축된 컴포넌트

#### 메트릭 수집
- ✅ **Prometheus**: 메트릭 수집 및 저장 (15초 간격)
- ✅ **django-prometheus**: Django 애플리케이션 메트릭 수집
  - Middleware 설정 완료
  - `/metrics` 엔드포인트 노출
- ✅ **cAdvisor**: 컨테이너 리소스 메트릭
- ✅ **node-exporter**: 호스트 시스템 메트릭
- ✅ **postgres-exporter**: PostgreSQL 메트릭
- ✅ **redis-exporter**: Redis 메트릭

#### 시각화
- ✅ **Grafana**: 대시보드 및 시각화 플랫폼
  - 포트: 3000
  - 초기 관리자: admin/admin

#### 작업 모니터링
- ✅ **Flower**: Celery 작업 모니터링 및 관리
  - 포트: 5555
  - 실시간 작업 상태 확인

#### 검색 및 로그
- ✅ **OpenSearch**: 로그 및 검색 엔진
  - 포트: 9200 (REST API), 9600 (Performance Analyzer)
  - 개발 환경: 보안 플러그인 비활성화

### 2.2 서비스 구성

#### 애플리케이션 서비스

| 서비스 | 컨테이너명 | 포트 | 설명 |
|--------|-----------|------|------|
| Django App | django | 8000 | 메인 API 서버 (Daphne ASGI) |
| Celery Worker | celery-worker | - | 비동기 작업 처리 |
| Celery Beat | celery-beat | - | 주기적 작업 스케줄러 |
| Subscribe Handler | tick-broadcaster | - | 실시간 구독 처리 |

#### 데이터 처리 서비스

| 서비스 | 컨테이너명 | 포트 | 설명 |
|--------|-----------|------|------|
| KIS Publisher | kis-publisher | - | 주식 시세 데이터 수집 |
| Persistence Worker | tick-writer | - | 시계열 데이터 저장 |
| KIS Mock Server | kis-mock-server | 8080 | 테스트용 Mock 서버 |

#### 데이터 저장소

| 서비스 | 컨테이너명 | 포트 | 설명 |
|--------|-----------|------|------|
| TimescaleDB | postgres-timescaledb | 5432 | 시계열 데이터베이스 |
| Redis | redis | 6379 | 캐시 및 메시지 브로커 |
| OpenSearch | opensearch | 9200, 9600 | 검색 및 로그 분석 |

### 2.3 기존 설정 파일

```text
prometheus/
└── prometheus.yml      # Prometheus 설정 (scrape 대상 정의)
```

### 2.4 ⚠️ 현재 문제점 및 우선 해결 과제

#### 문제 1: django-prometheus 메트릭 미수집
**현상**: Grafana에서 Django 메트릭이 "No data"로 표시됨

**원인**:
- Django 애플리케이션에 `/metrics` 엔드포인트가 설정되지 않음
- Prometheus가 Django 앱에서 메트릭을 수집하지 못함

**해결 방안**:
1. `config/urls.py`에 django-prometheus URL 패턴 추가
   ```python
   path('', include('django_prometheus.urls')),
   ```
2. `prometheus/prometheus.yml`에 Django 스크랩 설정 추가
   ```yaml
   - job_name: 'django-app'
     static_configs:
       - targets: ['app:8000']
   ```
3. 서비스 재시작 및 메트릭 확인

**우선순위**: 🔴 **Critical** - Phase 1의 첫 번째 작업

#### 문제 2: cAdvisor 메트릭 "No data"
**현상**: Grafana 대시보드에서 컨테이너 메트릭이 표시되지 않음

**원인**:
- macOS Docker Desktop 환경에서 cAdvisor의 제한적인 컨테이너 메타데이터 수집
- 기본 대시보드가 `name`, `image` 레이블을 기대하지만, 현재는 `id` 레이블만 존재
- Docker API를 통한 컨테이너 정보 수집 실패

**해결 방안**:

#### 옵션 1: 현재 메트릭 구조에 맞는 대시보드 사용 (권장)

- 현재 수집 중인 메트릭 확인:
  ```bash
  curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{id=~"/docker/.*"}'
  ```
- `id` 레이블 기반 쿼리로 대시보드 생성:
  ```promql
  # 메모리 사용량
  container_memory_usage_bytes{id=~"/docker/.*"}

  # CPU 사용률
  rate(container_cpu_usage_seconds_total{id=~"/docker/.*"}[5m])
  ```

#### 옵션 2: 커스텀 대시보드 생성

- Grafana Provisioning을 통한 자동 대시보드 배포
- `grafana/provisioning/dashboards/` 디렉토리 설정
- 컨테이너 ID 기반 패널 구성

#### 옵션 3: 외부 cAdvisor 대시보드 활용 불가
- 공식 대시보드(ID: 193)는 Docker 메타데이터가 필요
- macOS Docker Desktop 제약으로 인해 제한적

**우선순위**: 🟡 **High** - Phase 1의 두 번째 작업

#### 문제 해결 타임라인

```
Week 1
├─ Day 1-2: Django 메트릭 활성화 ✅
│  ├─ URL 설정
│  ├─ Prometheus 설정
│  └─ 메트릭 수집 확인
│
├─ Day 3-4: cAdvisor 대시보드 수정 ✅
│  ├─ 현재 메트릭 구조 분석
│  ├─ 커스텀 쿼리 작성
│  └─ Grafana 패널 생성
│
└─ Day 5-7: 기본 알림 설정
   ├─ AlertManager 설정
   └─ 핵심 알림 규칙 추가
```

---

## 3. 모니터링 전략

### 3.1 4가지 골든 시그널 (Four Golden Signals)

#### 1. Latency (지연시간)
- **대상**: API 응답 시간, DB 쿼리 시간
- **목표**: P95 < 500ms, P99 < 1000ms
- **메트릭**:
  - `django_http_requests_latency_seconds`
  - `django_db_query_duration_seconds`

#### 2. Traffic (트래픽)
- **대상**: 초당 요청 수 (RPS)
- **메트릭**:
  - `django_http_requests_total_by_view_transport_method`
  - `django_http_requests_total_by_method`

#### 3. Errors (에러)
- **대상**: HTTP 4xx/5xx 에러율
- **목표**: 에러율 < 1%
- **메트릭**:
  - `django_http_responses_total_by_status`
  - `celery_task_failed_total`

#### 4. Saturation (포화도)
- **대상**: CPU, 메모리, 디스크, 네트워크 사용률
- **목표**: CPU < 80%, 메모리 < 85%
- **메트릭**:
  - `container_cpu_usage_seconds_total`
  - `container_memory_usage_bytes`
  - `node_filesystem_avail_bytes`

### 3.2 모니터링 계층

```
┌─────────────────────────────────────────────────────────┐
│                    비즈니스 메트릭                        │
│  (사용자 수, 거래량, API 호출 패턴)                       │
└─────────────────────────────────────────────────────────┘
                           ▲
┌─────────────────────────────────────────────────────────┐
│                 애플리케이션 메트릭                        │
│  (Django, Celery, WebSocket)                            │
└─────────────────────────────────────────────────────────┘
                           ▲
┌─────────────────────────────────────────────────────────┐
│                  데이터베이스 메트릭                       │
│  (PostgreSQL, Redis, OpenSearch)                        │
└─────────────────────────────────────────────────────────┘
                           ▲
┌─────────────────────────────────────────────────────────┐
│                   인프라 메트릭                           │
│  (컨테이너, 호스트, 네트워크)                             │
└─────────────────────────────────────────────────────────┘
```

---

## 4. 구축 단계별 계획

### Phase 0: 🚨 긴급 문제 해결 (우선 작업, 1-2일)

#### 0.1 Django 메트릭 수집 활성화 (🔴 Critical)
**현재 상태**: `/metrics` 엔드포인트 미설정으로 메트릭 수집 불가

**작업 내용**:
- [ ] `config/urls.py`에 django-prometheus URL 패턴 추가
  ```python
  from django.urls import path, include

  urlpatterns = [
      # 기존 URL 패턴들...
      path('', include('django_prometheus.urls')),
  ]
  ```

- [ ] `prometheus/prometheus.yml` 업데이트
  ```yaml
  scrape_configs:
    - job_name: 'django-app'
      static_configs:
        - targets: ['app:8000']
      metrics_path: '/metrics'
  ```

- [ ] 서비스 재시작 및 확인
  ```bash
  docker-compose restart app prometheus
  # 메트릭 확인
  curl http://localhost:8000/metrics
  # Prometheus 타겟 확인
  curl http://localhost:9090/api/v1/targets | jq
  ```

**검증 기준**:
- ✅ `http://localhost:8000/metrics`에서 메트릭 노출 확인
- ✅ Prometheus Targets에서 `django-app`이 UP 상태
- ✅ Grafana에서 Django 메트릭 쿼리 가능

**예상 소요 시간**: 30분

#### 0.2 cAdvisor 대시보드 문제 해결 (🟡 High)
**현재 상태**: macOS 환경에서 컨테이너 메타데이터 부족으로 기본 대시보드 사용 불가

**작업 내용**:
- [ ] 현재 수집 가능한 메트릭 확인
  ```bash
  # Docker 컨테이너 메트릭 확인
  curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{id=~"/docker/.*"}' | jq
  ```

- [ ] 컨테이너 ID 기반 커스텀 Grafana 대시보드 생성
  - 메모리 사용량 패널: `container_memory_usage_bytes{id=~"/docker/.*"}`
  - CPU 사용률 패널: `rate(container_cpu_usage_seconds_total{id=~"/docker/.*"}[5m])`
  - 네트워크 I/O 패널: `rate(container_network_receive_bytes_total{id=~"/docker/.*"}[5m])`
  - 컨테이너 수 패널: `count(container_last_seen{id=~"/docker/.*"})`

- [ ] (옵션) Grafana Provisioning 설정
  ```bash
  mkdir -p grafana/provisioning/dashboards/json
  # 커스텀 대시보드 JSON 파일 생성
  ```

**검증 기준**:
- ✅ Grafana 대시보드에서 컨테이너 메트릭 시각화 확인
- ✅ 모든 Docker 컨테이너의 리소스 사용량 표시
- ✅ "No data" 문제 해결

**예상 소요 시간**: 1-2시간

---

### Phase 1: 기본 모니터링 강화 (1-2주)

#### 1.1 커스텀 비즈니스 메트릭 추가
**작업 내용**:
- [ ] 비즈니스 메트릭 정의 및 구현
- [ ] Prometheus Counter/Gauge/Histogram 활용

**설정 예시**:
```python
# config/urls.py
urlpatterns = [
    path('', include('django_prometheus.urls')),
]

# prometheus/prometheus.yml
scrape_configs:
  - job_name: 'django-app'
    static_configs:
      - targets: ['app:8000']
```

**비즈니스 메트릭**:
- 활성 사용자 수
- API 엔드포인트별 요청 수
- 주식 시세 업데이트 빈도
- 캐시 적중률

#### 1.2 Grafana 대시보드 구성
**대시보드 목록**:

1. **시스템 개요 대시보드**
   - 전체 서비스 상태
   - 컨테이너 리소스 사용량
   - 네트워크 트래픽

2. **Django 애플리케이션 대시보드**
   - HTTP 요청/응답 메트릭
   - API 엔드포인트별 성능
   - 에러율 및 상태 코드 분포

3. **데이터베이스 대시보드**
   - PostgreSQL 연결 수, 쿼리 성능
   - Redis 메모리 사용량, 명령 처리율
   - 슬로우 쿼리 분석

4. **Celery 작업 대시보드**
   - 작업 처리 속도
   - 큐 길이
   - 실패한 작업

5. **비즈니스 메트릭 대시보드**
   - 일별 활성 사용자
   - API 사용 패턴
   - 실시간 데이터 처리량

#### 1.3 Prometheus AlertManager 설정
**알림 채널**:
- Slack (권장)
- Email
- Webhook

**알림 규칙 예시**:
```yaml
groups:
  - name: critical
    rules:
      - alert: HighErrorRate
        expr: rate(django_http_responses_total_by_status{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "높은 서버 에러율 감지"
          description: "5분간 5xx 에러율이 5%를 초과했습니다."

      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes{name="django"} / container_spec_memory_limit_bytes{name="django"} > 0.85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Django 컨테이너 메모리 사용량 높음"
```

### Phase 2: 로그 수집 및 분석 (2-3주)

#### 2.1 로그 구조화
**로깅 레벨 정책**:
- **DEBUG**: 개발 환경 전용
- **INFO**: 정상 작동 이벤트
- **WARNING**: 주의가 필요한 이벤트
- **ERROR**: 에러 발생
- **CRITICAL**: 즉시 대응 필요

**구조화 로깅 필드**:
```json
{
  "timestamp": "2026-01-19T12:00:00Z",
  "level": "ERROR",
  "service": "django",
  "container": "django-app",
  "trace_id": "abc123",
  "user_id": "user_456",
  "endpoint": "/api/companies/",
  "method": "GET",
  "status_code": 500,
  "duration_ms": 1234,
  "error": "DatabaseConnectionError",
  "message": "Failed to connect to TimescaleDB"
}
```

#### 2.2 OpenSearch 로그 수집
**방법 1: Filebeat (권장)**
- Docker 로그 수집
- OpenSearch로 전송
- 경량 에이전트

**방법 2: Fluentd**
- 더 복잡한 로그 처리
- 필터링 및 변환

**설정 작업**:
- [ ] Filebeat 컨테이너 추가
- [ ] Docker 로그 드라이버 설정
- [ ] OpenSearch 인덱스 매핑 정의
- [ ] 로그 보존 정책 설정 (30일)

#### 2.3 Django 로깅 설정
```python
# config/settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### Phase 3: 고급 모니터링 (3-4주)

#### 3.1 분산 추적 (Distributed Tracing)
**도구**: Jaeger 또는 Zipkin

**목적**:
- API 요청의 전체 흐름 추적
- 마이크로서비스 간 의존성 파악
- 성능 병목 지점 식별

**설정**:
- [ ] OpenTelemetry SDK 설치
- [ ] Django 미들웨어 추가
- [ ] Celery 태스크 추적
- [ ] Jaeger 컨테이너 추가

#### 3.2 프로파일링
**도구**: Django Debug Toolbar, py-spy

**목적**:
- 슬로우 쿼리 식별
- N+1 쿼리 문제 감지
- CPU/메모리 프로파일링

#### 3.3 성능 테스트 통합
**도구**: Locust, k6

**목적**:
- 부하 테스트 자동화
- 성능 기준선 설정
- CI/CD 파이프라인 통합

### Phase 4: 운영 자동화 (4-5주)

#### 4.1 자동 스케일링
- Celery worker 자동 스케일링
- 메트릭 기반 알림

#### 4.2 장애 복구 자동화
- 헬스 체크 기반 재시작
- 자동 백업 및 복구

#### 4.3 성능 최적화
- 쿼리 최적화 권장 사항
- 캐싱 전략 개선

---

## 5. 대시보드 설계

### 5.1 시스템 개요 대시보드

**패널 구성**:

1. **서비스 상태 (Service Health)**
   - 모든 컨테이너의 Up/Down 상태
   - 헬스 체크 결과
   - 메트릭: `up{job="서비스명"}`

2. **리소스 사용량 (Resource Usage)**
   - CPU 사용률 (컨테이너별)
   - 메모리 사용률 (컨테이너별)
   - 디스크 사용률
   - 네트워크 I/O

3. **주요 메트릭 (Key Metrics)**
   - 초당 요청 수 (RPS)
   - 평균 응답 시간
   - 에러율
   - 활성 사용자 수

### 5.2 Django 애플리케이션 대시보드

**패널 구성**:

1. **HTTP 요청 메트릭**
   ```promql
   # 초당 요청 수
   rate(django_http_requests_total_by_method[5m])

   # 평균 응답 시간
   rate(django_http_requests_latency_seconds_sum[5m]) /
   rate(django_http_requests_latency_seconds_count[5m])

   # P95 응답 시간
   histogram_quantile(0.95,
     rate(django_http_requests_latency_seconds_bucket[5m]))
   ```

2. **에러율**
   ```promql
   # 5xx 에러율
   sum(rate(django_http_responses_total_by_status{status=~"5.."}[5m])) /
   sum(rate(django_http_responses_total_by_status[5m]))

   # 4xx 에러율
   sum(rate(django_http_responses_total_by_status{status=~"4.."}[5m])) /
   sum(rate(django_http_responses_total_by_status[5m]))
   ```

3. **데이터베이스 연결**
   ```promql
   # DB 연결 수
   django_db_new_connections_total

   # 쿼리 실행 시간
   rate(django_db_query_duration_seconds_sum[5m]) /
   rate(django_db_query_duration_seconds_count[5m])
   ```

### 5.3 Celery 작업 대시보드

**패널 구성**:

1. **작업 처리율**
   ```promql
   # 초당 처리된 작업 수
   rate(celery_task_succeeded_total[5m])

   # 실패한 작업 수
   rate(celery_task_failed_total[5m])
   ```

2. **큐 길이**
   ```promql
   # Redis 큐 길이
   redis_list_length{key=~"celery.*"}
   ```

3. **작업 실행 시간**
   - 태스크별 평균 실행 시간
   - 슬로우 태스크 식별

### 5.4 데이터베이스 대시보드

**PostgreSQL 패널**:
```promql
# 활성 연결 수
pg_stat_activity_count

# 쿼리 처리율
rate(pg_stat_database_xact_commit[5m])

# 캐시 적중률
pg_stat_database_blks_hit /
(pg_stat_database_blks_hit + pg_stat_database_blks_read)

# 슬로우 쿼리
pg_stat_statements_mean_time_seconds > 1
```

**Redis 패널**:
```promql
# 메모리 사용량
redis_memory_used_bytes / redis_memory_max_bytes

# 명령 처리율
rate(redis_commands_processed_total[5m])

# 키 개수
redis_db_keys

# 적중률
redis_keyspace_hits_total /
(redis_keyspace_hits_total + redis_keyspace_misses_total)
```

### 5.5 비즈니스 메트릭 대시보드

**커스텀 메트릭 예시**:

```python
from prometheus_client import Counter, Histogram, Gauge

# 사용자 활동
active_users = Gauge('active_users', 'Number of active users')

# API 호출
api_calls = Counter('api_calls_total', 'Total API calls',
                    ['endpoint', 'method', 'status'])

# 데이터 처리
stock_price_updates = Counter('stock_price_updates_total',
                               'Total stock price updates',
                               ['symbol'])

# 응답 시간
api_latency = Histogram('api_latency_seconds',
                        'API request latency',
                        ['endpoint'])
```

---

## 6. 알림 전략

### 6.1 알림 등급

| 등급 | 설명 | 대응 시간 | 통보 대상 |
|------|------|----------|----------|
| **Critical** | 서비스 중단 | 즉시 | 전체 팀 + On-call |
| **High** | 성능 저하 | 30분 이내 | 개발팀 + DevOps |
| **Medium** | 리소스 경고 | 2시간 이내 | DevOps |
| **Low** | 일반 경고 | 24시간 이내 | 로그만 기록 |

### 6.2 알림 규칙

#### Critical 알림

```yaml
# 서비스 다운
- alert: ServiceDown
  expr: up{job=~"django-app|postgres|redis"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "{{ $labels.job }} 서비스 다운"
    description: "{{ $labels.job }}이(가) 1분 이상 응답하지 않습니다."

# 높은 에러율
- alert: HighErrorRate
  expr: |
    sum(rate(django_http_responses_total_by_status{status=~"5.."}[5m])) /
    sum(rate(django_http_responses_total_by_status[5m])) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "높은 서버 에러율"
    description: "5분간 5xx 에러율이 5%를 초과했습니다. (현재: {{ $value | humanizePercentage }})"

# 데이터베이스 연결 실패
- alert: DatabaseConnectionFailure
  expr: pg_up == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "PostgreSQL 연결 실패"
```

#### High 알림

```yaml
# 높은 응답 시간
- alert: HighLatency
  expr: |
    histogram_quantile(0.95,
      rate(django_http_requests_latency_seconds_bucket[5m])) > 1
  for: 10m
  labels:
    severity: high
  annotations:
    summary: "높은 API 응답 시간"
    description: "P95 응답 시간이 1초를 초과했습니다. (현재: {{ $value }}s)"

# Celery 작업 적체
- alert: CeleryQueueBacklog
  expr: redis_list_length{key=~"celery.*"} > 1000
  for: 15m
  labels:
    severity: high
  annotations:
    summary: "Celery 큐 적체"
    description: "큐에 {{ $value }}개의 작업이 대기 중입니다."
```

#### Medium 알림

```yaml
# 높은 CPU 사용률
- alert: HighCPUUsage
  expr: |
    rate(container_cpu_usage_seconds_total[5m]) > 0.8
  for: 15m
  labels:
    severity: medium
  annotations:
    summary: "높은 CPU 사용률"
    description: "{{ $labels.name }} 컨테이너의 CPU 사용률이 80%를 초과했습니다."

# 높은 메모리 사용률
- alert: HighMemoryUsage
  expr: |
    container_memory_usage_bytes /
    container_spec_memory_limit_bytes > 0.85
  for: 15m
  labels:
    severity: medium
  annotations:
    summary: "높은 메모리 사용률"
    description: "{{ $labels.name }} 컨테이너의 메모리 사용률이 85%를 초과했습니다."

# 디스크 사용률
- alert: HighDiskUsage
  expr: |
    (node_filesystem_size_bytes - node_filesystem_avail_bytes) /
    node_filesystem_size_bytes > 0.8
  for: 30m
  labels:
    severity: medium
  annotations:
    summary: "높은 디스크 사용률"
```

### 6.3 알림 채널 설정

#### Slack 통합
```yaml
# alertmanager.yml
receivers:
  - name: 'slack-critical'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts-critical'
        title: '🚨 Critical Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ .Annotations.description }}\n{{ end }}'

  - name: 'slack-high'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts-high'
        title: '⚠️ High Priority Alert'
```

### 6.4 On-Call 로테이션
- PagerDuty 또는 Opsgenie 통합
- 주간 로테이션 스케줄
- 에스컬레이션 정책

---

## 7. 로그 관리 전략

### 7.1 로그 수집 아키텍처

```
┌─────────────────┐
│ Docker Logs     │
│ (JSON Driver)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Filebeat      │
│ (Log Shipper)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  OpenSearch     │
│ (Log Storage)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ OpenSearch      │
│ Dashboards      │
│ (Visualization) │
└─────────────────┘
```

### 7.2 로그 보존 정책

| 로그 유형 | 보존 기간 | 인덱스 패턴 |
|----------|----------|------------|
| 애플리케이션 로그 | 30일 | logs-app-* |
| 에러 로그 | 90일 | logs-error-* |
| 감사 로그 | 1년 | logs-audit-* |
| 접근 로그 | 30일 | logs-access-* |

### 7.3 로그 검색 쿼리 예시

```
# 5xx 에러 검색
status_code:5* AND service:django

# 특정 사용자 활동
user_id:"user_123" AND timestamp:[now-1h TO now]

# 슬로우 요청
duration_ms:>1000 AND endpoint:"/api/*"

# 특정 태스크 실패
task_name:"companies.tasks.dart_sync" AND level:ERROR
```

---

## 8. 성능 최적화 가이드

### 8.1 데이터베이스 최적화

#### 슬로우 쿼리 모니터링
```sql
-- PostgreSQL 슬로우 쿼리 로깅
ALTER SYSTEM SET log_min_duration_statement = 1000; -- 1초 이상
SELECT pg_reload_conf();

-- 슬로우 쿼리 조회
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

#### 인덱스 최적화
```sql
-- 누락된 인덱스 식별
SELECT schemaname, tablename, attname
FROM pg_stats
WHERE n_distinct > 100
  AND tablename NOT IN (
    SELECT tablename
    FROM pg_indexes
    WHERE indexname LIKE '%' || attname || '%'
  );
```

### 8.2 캐싱 전략

#### Redis 캐시 계층
```python
# 자주 조회되는 데이터 캐싱
from django.core.cache import cache

def get_company_info(company_id):
    cache_key = f'company:{company_id}'
    data = cache.get(cache_key)

    if data is None:
        data = Company.objects.get(id=company_id)
        cache.set(cache_key, data, timeout=3600)  # 1시간

    return data
```

#### 캐시 워밍 (Cache Warming)
- 서비스 시작 시 인기 데이터 사전 로드
- Celery 주기적 태스크로 캐시 갱신

### 8.3 Celery 작업 최적화

#### 작업 우선순위
```python
# celery.py
CELERY_TASK_ROUTES = {
    'companies.tasks.dart_sync': {'queue': 'high_priority'},
    'news.tasks.crawl_news': {'queue': 'low_priority'},
}
```

#### 작업 재시도 전략
```python
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def sync_financial_data(self, company_id):
    pass
```

---

## 9. 보안 고려사항

### 9.1 메트릭 엔드포인트 보안

```python
# 프로덕션 환경에서 /metrics 엔드포인트 보호
from django.http import HttpResponseForbidden

def metrics_view(request):
    # IP 화이트리스트
    allowed_ips = ['10.0.0.0/8', 'prometheus_server_ip']

    if request.META.get('REMOTE_ADDR') not in allowed_ips:
        return HttpResponseForbidden()

    # 또는 Basic Auth
    if not check_basic_auth(request):
        return HttpResponse('Unauthorized', status=401)
```

### 9.2 Grafana 보안
- 강력한 관리자 비밀번호 설정
- HTTPS 사용 (프로덕션)
- 역할 기반 접근 제어 (RBAC)
- SSO 통합 (옵션)

### 9.3 로그 민감 정보 마스킹
```python
import re

def mask_sensitive_data(log_message):
    # 이메일 마스킹
    log_message = re.sub(r'\b[\w\.-]+@[\w\.-]+\.\w+\b', '***@***.***', log_message)

    # 전화번호 마스킹
    log_message = re.sub(r'\d{3}-\d{4}-\d{4}', '***-****-****', log_message)

    # 카드번호 마스킹
    log_message = re.sub(r'\d{4}-\d{4}-\d{4}-\d{4}', '****-****-****-****', log_message)

    return log_message
```

---

## 10. 구현 체크리스트

### Phase 0: 🚨 긴급 문제 해결 (최우선)
- [ ] **Django 메트릭 수집 활성화** (🔴 Critical)
  - [ ] `config/urls.py`에 django-prometheus URL 추가
  - [ ] `prometheus/prometheus.yml`에 django-app 스크랩 설정
  - [ ] 서비스 재시작
  - [ ] `/metrics` 엔드포인트 확인
  - [ ] Prometheus Targets에서 UP 상태 확인

- [ ] **cAdvisor 대시보드 수정** (🟡 High)
  - [ ] 현재 메트릭 구조 분석 (id 레이블 확인)
  - [ ] 컨테이너 ID 기반 커스텀 쿼리 작성
  - [ ] Grafana 대시보드 생성 (메모리, CPU, 네트워크, 컨테이너 수)
  - [ ] "No data" 문제 해결 확인

### Phase 1: 기본 모니터링 강화
- [ ] 커스텀 비즈니스 메트릭 추가
- [ ] Grafana 데이터 소스 연결
- [ ] 시스템 개요 대시보드 생성
- [ ] Django 애플리케이션 대시보드 생성
- [ ] 데이터베이스 대시보드 생성
- [ ] Celery 대시보드 생성
- [ ] AlertManager 설치 및 설정
- [ ] 기본 알림 규칙 작성
- [ ] Slack 알림 채널 설정

### Phase 2: 로그 수집 및 분석
- [ ] Django 구조화 로깅 설정
- [ ] Filebeat 컨테이너 추가
- [ ] OpenSearch 인덱스 매핑 정의
- [ ] 로그 보존 정책 설정
- [ ] OpenSearch Dashboards 대시보드 생성
- [ ] 로그 검색 쿼리 템플릿 작성

### Phase 3: 고급 모니터링
- [ ] OpenTelemetry 설치
- [ ] 분산 추적 설정
- [ ] Jaeger 또는 Zipkin 배포
- [ ] Django Debug Toolbar 설정 (개발 환경)
- [ ] 성능 테스트 도구 설정 (Locust/k6)

### Phase 4: 운영 자동화
- [ ] 자동 스케일링 스크립트
- [ ] 장애 복구 자동화
- [ ] 성능 리포트 자동 생성
- [ ] 주간 리뷰 리포트

---

## 11. 예상 리소스 요구사항

### 11.1 추가 컨테이너

| 서비스 | CPU | 메모리 | 디스크 |
|--------|-----|--------|--------|
| AlertManager | 0.1 core | 128MB | 1GB |
| Filebeat | 0.1 core | 64MB | - |
| Jaeger (옵션) | 0.5 core | 512MB | 5GB |

### 11.2 스토리지

| 항목 | 예상 크기 | 보존 기간 |
|------|----------|----------|
| Prometheus 메트릭 | ~500MB/일 | 30일 |
| OpenSearch 로그 | ~1GB/일 | 30일 |
| Jaeger 트레이스 | ~2GB/일 | 7일 |

**총 예상 디스크**: ~100GB

---

## 12. 운영 가이드

### 12.1 일일 모니터링 체크리스트
- [ ] 전체 서비스 상태 확인
- [ ] 지난 24시간 알림 검토
- [ ] 주요 메트릭 추세 확인
- [ ] 에러 로그 검토

### 12.2 주간 리뷰
- [ ] 성능 트렌드 분석
- [ ] 리소스 사용량 분석
- [ ] 슬로우 쿼리 최적화
- [ ] 알림 규칙 조정

### 12.3 월간 리뷰
- [ ] 용량 계획 (Capacity Planning)
- [ ] 모니터링 시스템 성능 평가
- [ ] 대시보드 개선
- [ ] 문서 업데이트

### 12.4 장애 대응 절차

1. **알림 수신**
   - 알림 심각도 확인
   - 영향 범위 파악

2. **초기 대응**
   - 관련 대시보드 확인
   - 로그 검토
   - 근본 원인 파악

3. **조치**
   - 임시 조치 (재시작, 스케일 아웃 등)
   - 근본 원인 해결
   - 변경 사항 문서화

4. **사후 검토**
   - 장애 보고서 작성
   - 재발 방지 대책 수립
   - 모니터링 개선

---

## 13. 참고 자료

### 13.1 공식 문서
- [Prometheus 공식 문서](https://prometheus.io/docs/)
- [Grafana 공식 문서](https://grafana.com/docs/)
- [django-prometheus](https://github.com/korfuri/django-prometheus)
- [OpenSearch 공식 문서](https://opensearch.org/docs/)

### 13.2 모범 사례
- [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [The Four Golden Signals](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)

### 13.3 유용한 Grafana 대시보드
- [Django Prometheus Dashboard](https://grafana.com/grafana/dashboards/9528)
- [PostgreSQL Dashboard](https://grafana.com/grafana/dashboards/9628)
- [Redis Dashboard](https://grafana.com/grafana/dashboards/763)

---

## 14. 다음 단계

### 🚨 즉시 시작해야 할 작업 (Phase 0)
1. **Django 메트릭 수집 활성화** (30분, 🔴 Critical)
   - `config/urls.py`에 django-prometheus URL 추가
   - `prometheus/prometheus.yml`에 django-app 스크랩 설정 추가
   - 서비스 재시작 및 메트릭 확인

2. **cAdvisor 대시보드 문제 해결** (1-2시간, 🟡 High)
   - 현재 메트릭 구조 분석 (`id` 레이블 기반)
   - 커스텀 Grafana 대시보드 생성
   - 컨테이너 리소스 모니터링 활성화

### 우선순위 작업
1. **Day 1-2**: Phase 0 완료 (긴급 문제 해결)
2. **Week 1-2**: Phase 1 완료 (기본 모니터링 강화)
3. **Week 3-4**: AlertManager 설정 및 알림 규칙
4. **Week 5-6**: 로그 수집 시스템 구축

### 장기 목표
- 완전 자동화된 모니터링 시스템
- AI 기반 이상 탐지
- 성능 예측 및 용량 계획

---

**문서 버전**: 1.0
**최종 수정일**: 2026-01-19
**작성자**: Claude Code Assistant
