# 모니터링 시스템 강화 계획서

## 📋 문서 정보
- **작성일**: 2026-01-23
- **대상 시스템**: 2025 Techeer Winter Bootcamp Backend
- **목적**: 로깅, 메트릭, 트레이싱을 포함한 종합 Observability 구축

---

## 1. 현재 상태 분석

### 1.1 기존 모니터링 구성

#### App Layer (Application Server)
| 컴포넌트 | 용도 | 상태 | 포트 |
|---------|------|------|------|
| Prometheus | 메트릭 수집 | ✅ 운영 중 | 9090 |
| Grafana | 메트릭 시각화 | ✅ 운영 중 | 3000 |
| Node Exporter | 시스템 메트릭 | ✅ 운영 중 | 9100 |
| cAdvisor | 컨테이너 메트릭 | ✅ 운영 중 | 8081 |
| Flower | Celery 작업 모니터링 | ✅ 운영 중 | 5555 |
| Portainer | Docker 컨테이너 관리 | ❌ 미설치 | 9000 |

#### Data Layer (Database Server)
| 컴포넌트 | 용도 | 상태 | 포트 |
|---------|------|------|------|
| Node Exporter | 시스템 메트릭 | ✅ 운영 중 | 9100 |
| Postgres Exporter | PostgreSQL 메트릭 | ✅ 운영 중 | 9187 |
| Redis Exporter | Redis 메트릭 | ✅ 운영 중 | 9121 |

### 1.2 현재 Prometheus 수집 대상
```yaml
# deploy/app/prometheus.yml
scrape_configs:
  - job_name: 'prometheus'           # Prometheus 자체 메트릭
  - job_name: 'django-app'           # Django 애플리케이션 메트릭
  - job_name: 'node-exporter-app'    # App Layer 시스템 메트릭
  # - job_name: 'data-node-exporter' # ❌ Data Layer 미연결 (주석 처리됨)
```

### 1.3 문제점 및 개선 필요 사항

#### 🔴 심각 (Critical)
1. **로그 중앙화 부재** - Docker 컨테이너 로그가 분산되어 있음
2. **분산 트레이싱 부재** - 마이크로서비스 간 요청 추적 불가
3. **알림 시스템 부재** - Prometheus Alertmanager 미구성

#### 🟡 중요 (High)
4. **Data Layer 메트릭 미연결** - Postgres/Redis Exporter가 Prometheus에 연결되지 않음
5. **OpenSearch 모니터링 부재** - 검색 엔진 상태 파악 불가
6. **애플리케이션 로그 구조화 부재** - JSON 로그 포맷 미사용
7. **SLI/SLO 정의 부재** - 서비스 수준 목표 미설정

#### 🟢 보통 (Medium)
8. **Celery 메트릭 부족** - Flower만으로는 세밀한 모니터링 어려움
9. **네트워크 레이턴시 추적 부재** - 서비스 간 통신 병목 파악 어려움
10. **장기 메트릭 저장 부재** - Prometheus는 단기 저장용 (기본 15일)

---

## 2. 목표 아키텍처: Observability + Management

```
┌───────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY & MANAGEMENT                      │
├───────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │   LOGGING    │  │   METRICS    │  │   TRACING    │            │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤            │
│  │              │  │              │  │              │            │
│  │  Loki        │  │  Prometheus  │  │  Tempo       │            │
│  │  + Promtail  │  │  + Exporters │  │  + OTEL      │            │
│  │              │  │              │  │              │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│         └─────────────────┼─────────────────┘                     │
│                           │                                       │
│         ┌─────────────────┼─────────────────┐                     │
│         │                 │                 │                     │
│  ┌──────▼────────┐ ┌──────▼────────┐ ┌──────▼────────┐           │
│  │   Grafana     │ │  Portainer    │ │  Alertmanager │           │
│  │ (시각화/대시보드)│ │ (컨테이너 관리)│ │  (알림 발송)   │           │
│  └───────────────┘ └───────────────┘ └───────────────┘           │
│                                                                    │
└───────────────────────────────────────────────────────────────────┘

                          ▼ 수집 대상 ▼

┌─────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                        │
├─────────────────────────────────────────────────────────────────┤
│  Django │ Celery │ Nginx │ KIS Publisher │ Persistence Worker   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                             │
├─────────────────────────────────────────────────────────────────┤
│         PostgreSQL │ Redis │ OpenSearch │ RabbitMQ              │
└─────────────────────────────────────────────────────────────────┘
```

### 기술 스택 선정 이유

#### Logging: **Grafana Loki**
- ✅ Prometheus와 같은 레이블 기반 쿼리
- ✅ Grafana 네이티브 통합 (기존 대시보드 활용)
- ✅ 낮은 리소스 사용량 (인덱싱 최소화)
- ✅ S3 호환 스토리지 지원 (장기 보관)
- ❌ ELK 대비 검색 기능 제한적 (트레이드오프)

#### Tracing: **Grafana Tempo**
- ✅ Jaeger/Zipkin 대비 스토리지 효율적
- ✅ Grafana/Loki/Prometheus와 완벽 통합
- ✅ OpenTelemetry 표준 지원
- ✅ 메트릭-로그-트레이스 상관관계 분석 가능

#### Metrics: **Prometheus** (기존 유지)
- ✅ 이미 구축 완료
- ✅ 강력한 쿼리 언어 (PromQL)
- ⚠️ 장기 저장을 위해 Thanos/Mimir 고려

---

## 3. 구현 계획

### Phase 0: Docker 관리 도구 구축 (우선순위: 🟢 보통, 선행 작업)

#### 3.0 Portainer 도입

**추가할 컴포넌트:**

```yaml
# deploy/app/docker-compose.yml 추가
services:
  portainer:
    image: portainer/portainer-ce:latest
    container_name: portainer
    ports:
      - "127.0.0.1:9000:9000"
      - "127.0.0.1:9443:9443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - portainer_data:/data
    networks:
      - app-network
    restart: always

volumes:
  portainer_data:
```

**Portainer 기능:**
1. **컨테이너 관리**
   - 컨테이너 시작/중지/재시작/삭제
   - 실시간 로그 확인 (Loki 도입 전 임시 대안)
   - 컨테이너 쉘 접속
   - 리소스 제한 설정

2. **스택 관리**
   - Docker Compose 스택 배포/업데이트
   - 환경 변수 관리
   - 네트워크/볼륨 관리

3. **이미지 관리**
   - 이미지 pull/push
   - 이미지 빌드
   - 레지스트리 연동 (GHCR)

4. **모니터링**
   - 컨테이너별 CPU/Memory 실시간 확인
   - 네트워크 트래픽 확인
   - 이벤트 로그 확인

**접속 방법:**
```
URL: http://<APP_SERVER_IP>:9000
초기 설정: 첫 접속 시 관리자 계정 생성
```

**보안 설정:**
- HTTPS 포트(9443) 사용 권장
- 강력한 비밀번호 설정
- 외부 접속 차단 (127.0.0.1 바인딩 또는 Nginx 리버스 프록시)

**Nginx 리버스 프록시 설정 (선택):**
```nginx
# deploy/app/nginx/conf.d/portainer.conf
location /portainer/ {
    proxy_pass http://portainer:9000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**예상 리소스:**
- CPU: 0.1 core
- Memory: 256MB
- Disk: 1GB

**장점:**
- ✅ Docker CLI 없이도 컨테이너 관리 가능
- ✅ 팀원 간 운영 지식 공유 용이
- ✅ 긴급 상황 시 빠른 대응 가능 (재시작, 로그 확인)
- ✅ Grafana 대시보드와 상호 보완

**단점:**
- ⚠️ Docker 소켓 접근 권한 필요 (보안 주의)
- ⚠️ 프로덕션 환경에서는 RBAC 설정 필수

---

### Phase 1: 로깅 시스템 구축 (우선순위: 🔴 최고)

#### 3.1 Loki + Promtail 도입

**추가할 컴포넌트:**

```yaml
# deploy/app/docker-compose.yml 추가
services:
  loki:
    image: grafana/loki:2.9.0
    container_name: loki
    ports:
      - "127.0.0.1:3100:3100"
    volumes:
      - ./loki-config.yml:/etc/loki/loki-config.yml
      - ./loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yml
    networks:
      - app-network
    restart: always

  promtail:
    image: grafana/promtail:2.9.0
    container_name: promtail
    volumes:
      - ./promtail-config.yml:/etc/promtail/promtail-config.yml
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock
    command: -config.file=/etc/promtail/promtail-config.yml
    networks:
      - app-network
    restart: always
```

**설정 작업:**
1. `loki-config.yml` 생성 - 로그 저장/보관 정책
2. `promtail-config.yml` 생성 - Docker 로그 수집 설정
3. Grafana Datasource 추가

**Django 애플리케이션 변경:**
```python
# config/settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
}
```

**필요한 패키지:**
```bash
pip install python-json-logger
```

**예상 리소스:**
- CPU: 0.5 core
- Memory: 512MB
- Disk: 10GB (7일 로그 보관 기준)

#### 3.2 로그 레벨 및 보관 정책

| 로그 레벨 | 대상 | 보관 기간 | 예시 |
|----------|------|----------|------|
| ERROR | 모든 서비스 | 30일 | 예외, 크래시 |
| WARNING | App, Celery | 14일 | 재시도, 지연 |
| INFO | 모든 서비스 | 7일 | 요청, 작업 완료 |
| DEBUG | 비활성화 | - | 개발 환경만 |

---

### Phase 2: 분산 트레이싱 구축 (우선순위: 🔴 최고)

#### 3.3 Tempo + OpenTelemetry 도입

**추가할 컴포넌트:**

```yaml
# deploy/app/docker-compose.yml 추가
services:
  tempo:
    image: grafana/tempo:latest
    container_name: tempo
    ports:
      - "127.0.0.1:3200:3200"   # Tempo
      - "127.0.0.1:4317:4317"   # OTLP gRPC
      - "127.0.0.1:4318:4318"   # OTLP HTTP
    volumes:
      - ./tempo-config.yml:/etc/tempo.yml
      - ./tempo_data:/tmp/tempo
    command: -config.file=/etc/tempo.yml
    networks:
      - app-network
    restart: always
```

**Django 애플리케이션 계측:**
```python
# requirements.txt 추가
opentelemetry-api
opentelemetry-sdk
opentelemetry-instrumentation-django
opentelemetry-instrumentation-psycopg2
opentelemetry-instrumentation-redis
opentelemetry-instrumentation-celery
opentelemetry-exporter-otlp

# config/settings.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Tracer 설정
trace.set_tracer_provider(TracerProvider())
otlp_exporter = OTLPSpanExporter(endpoint="http://tempo:4317", insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

# 자동 계측 활성화
from opentelemetry.instrumentation.django import DjangoInstrumentor
DjangoInstrumentor().instrument()
```

**추적할 작업:**
1. HTTP 요청 → Django → PostgreSQL → Redis
2. Celery 작업 체인
3. KIS API 호출 (kis-publisher)
4. DART API 호출 (django-app)
5. OpenSearch 쿼리

**예상 리소스:**
- CPU: 0.5 core
- Memory: 1GB
- Disk: 20GB (14일 트레이스 보관 기준)

---

### Phase 3: 메트릭 강화 (우선순위: 🟡 높음)

#### 3.4 Data Layer 메트릭 연결

**Prometheus 설정 업데이트:**

```yaml
# deploy/app/prometheus.yml 수정
scrape_configs:
  # 기존 설정 유지
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'django-app'
    metrics_path: /internal/metrics
    static_configs:
      - targets: ['app:8000']

  - job_name: 'node-exporter-app'
    static_configs:
      - targets: ['node-exporter:9100']

  # ✅ Data Layer 메트릭 추가
  - job_name: 'node-exporter-data'
    static_configs:
      - targets: ['${DATA_NODE_IP}:9100']

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['${DATA_NODE_IP}:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['${DATA_NODE_IP}:9121']

  # ✅ 컨테이너 메트릭 추가
  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']
```

**환경 변수 설정:**
```bash
# deploy/app/.env
DATA_NODE_IP=<Data Layer EC2 Private IP>
```

#### 3.5 OpenSearch Exporter 추가

**Data Layer에 추가:**

```yaml
# deploy/data/docker-compose.yml 추가
services:
  opensearch-exporter:
    image: prometheuscommunity/opensearch-exporter:latest
    container_name: opensearch-exporter
    environment:
      - OPENSEARCH_URI=https://admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}@opensearch:9200
      - OPENSEARCH_SSL_VERIFY=false
    ports:
      - "9114:9114"
    networks:
      - data-network
    depends_on:
      opensearch:
        condition: service_healthy
    restart: always
```

**Prometheus에 추가:**
```yaml
  - job_name: 'opensearch-exporter'
    static_configs:
      - targets: ['${DATA_NODE_IP}:9114']
```

#### 3.6 Celery Prometheus Exporter 추가

**App Layer에 추가:**

```yaml
# deploy/app/docker-compose.yml 수정
services:
  celery-exporter:
    image: danihodovic/celery-exporter:latest
    container_name: celery-exporter
    command: --broker-url=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:6379/0
    ports:
      - "127.0.0.1:9808:9808"
    networks:
      - app-network
    restart: always
```

**Prometheus에 추가:**
```yaml
  - job_name: 'celery-exporter'
    static_configs:
      - targets: ['celery-exporter:9808']
```

---

### Phase 4: 알림 시스템 구축 (우선순위: 🟡 높음)

#### 3.7 Alertmanager 도입

**추가할 컴포넌트:**

```yaml
# deploy/app/docker-compose.yml 추가
services:
  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - ./alertmanager_data:/alertmanager
    ports:
      - "127.0.0.1:9093:9093"
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    networks:
      - app-network
    restart: always
```

**알림 규칙 예시:**

```yaml
# deploy/app/prometheus-alerts.yml
groups:
  - name: infrastructure
    interval: 30s
    rules:
      # 시스템 리소스
      - alert: HighCPUUsage
        expr: 100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "CPU 사용률 80% 초과"

      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100 > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "메모리 사용률 85% 초과"

      - alert: HighDiskUsage
        expr: (node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes * 100 > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "디스크 사용률 90% 초과"

      # 데이터베이스
      - alert: PostgreSQLDown
        expr: up{job="postgres-exporter"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL 다운"

      - alert: RedisDown
        expr: up{job="redis-exporter"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis 다운"

      # 애플리케이션
      - alert: HighErrorRate
        expr: rate(django_http_responses_total_by_status_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "5xx 에러율 10% 초과"

      - alert: CeleryTaskFailureRate
        expr: rate(celery_task_failed_total[5m]) / rate(celery_task_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Celery 작업 실패율 10% 초과"
```

**알림 채널 설정:**

```yaml
# deploy/app/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'slack-notifications'

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#alerts'
        title: '🚨 {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'
```

---

### Phase 5: SLI/SLO 정의 및 대시보드 (우선순위: 🟢 보통)

#### 3.8 서비스 수준 목표 설정

| SLI (Service Level Indicator) | SLO (Service Level Objective) | 측정 방법 |
|-------------------------------|-------------------------------|----------|
| API 가용성 | 99.5% (월간) | `(성공 요청 / 전체 요청) * 100` |
| API 응답 시간 (P95) | < 500ms | `histogram_quantile(0.95, ...)` |
| Celery 작업 처리율 | 99% (일간) | `(성공 작업 / 전체 작업) * 100` |
| 데이터베이스 쿼리 시간 (P95) | < 100ms | PostgreSQL slow query log |
| Redis 응답 시간 (P99) | < 10ms | `redis_commands_duration_seconds` |

#### 3.9 Grafana 대시보드 구성

**생성할 대시보드:**

1. **Infrastructure Overview** (기존 보강)
   - 시스템 리소스 (CPU, Memory, Disk, Network)
   - Docker 컨테이너 상태
   - 네트워크 트래픽

2. **Application Performance Monitoring (APM)** ⭐ 신규
   - HTTP 요청 처리량 (RPS)
   - 응답 시간 분포 (P50, P95, P99)
   - 에러율 (4xx, 5xx)
   - 활성 사용자 수

3. **Database & Cache** ⭐ 신규
   - PostgreSQL: Connection Pool, Query Performance, Replication Lag
   - Redis: Hit/Miss Ratio, Memory Usage, Command Stats
   - TimescaleDB: Chunk Stats, Compression Ratio

4. **Celery Tasks** ⭐ 신규
   - 작업 큐 길이
   - 작업 처리 시간
   - Worker 상태
   - 실패율 및 재시도 현황

5. **Distributed Tracing** ⭐ 신규
   - 서비스 의존성 그래프
   - 레이턴시 히트맵
   - 에러 트레이스 목록

6. **Logs Explorer** ⭐ 신규
   - 통합 로그 검색
   - 에러 로그 대시보드
   - 로그 볼륨 추이

7. **Business Metrics** ⭐ 신규
   - DART API 호출 통계
   - KIS WebSocket 연결 상태
   - 재무제표 동기화 현황
   - 뉴스 크롤링 통계

---

## 4. 제거/최적화 항목

### 4.1 삭제할 컴포넌트
없음 - 현재 구성은 모두 유용함

### 4.2 최적화할 설정

#### Prometheus 데이터 보관 정책
```yaml
# deploy/app/docker-compose.yml
services:
  prometheus:
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'  # 15일로 제한
      - '--storage.tsdb.retention.size=10GB'  # 10GB로 제한
```

#### Loki 로그 압축 및 보관
```yaml
# loki-config.yml
limits_config:
  retention_period: 168h  # 7일

compactor:
  working_directory: /loki/compactor
  shared_store: filesystem
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
```

#### Docker 로그 로테이션
```yaml
# deploy/app/docker-compose.yml
# 모든 서비스에 추가
services:
  app:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 5. 구현 우선순위 및 일정

### Phase 0: Docker 관리 도구 (주차: 사전 작업, 0.5일)
- [ ] Portainer 설치
- [ ] Nginx 리버스 프록시 설정 (선택)
- [ ] 관리자 계정 생성 및 보안 설정
- [ ] 팀원 계정 추가 및 권한 설정

### Phase 1: 로깅 시스템 (주차: 1-2주)
- [ ] Loki + Promtail 설치
- [ ] Django JSON 로그 포맷 적용
- [ ] Grafana Loki Datasource 연결
- [ ] 기본 로그 대시보드 생성

### Phase 2: 분산 트레이싱 (주차: 3-4주)
- [ ] Tempo 설치
- [ ] OpenTelemetry SDK 통합
- [ ] Django/Celery 자동 계측
- [ ] Grafana Tempo Datasource 연결

### Phase 3: 메트릭 강화 (주차: 5주)
- [ ] Data Layer Prometheus 연결
- [ ] OpenSearch Exporter 추가
- [ ] Celery Exporter 추가
- [ ] 통합 메트릭 대시보드 생성

### Phase 4: 알림 시스템 (주차: 6주)
- [ ] Alertmanager 설치
- [ ] 알림 규칙 작성
- [ ] Slack 연동
- [ ] 온콜 로테이션 설정

### Phase 5: 최적화 및 SLO (주차: 7-8주)
- [ ] SLI/SLO 대시보드 생성
- [ ] 데이터 보관 정책 적용
- [ ] 성능 튜닝
- [ ] 문서화 완료

---

## 6. 예상 리소스 요구사항

### App Layer 추가 리소스

| 컴포넌트 | CPU | Memory | Disk |
|---------|-----|--------|------|
| Loki | 0.5 core | 512MB | 10GB |
| Promtail | 0.1 core | 128MB | 1GB |
| Tempo | 0.5 core | 1GB | 20GB |
| Alertmanager | 0.2 core | 256MB | 2GB |
| Celery Exporter | 0.1 core | 128MB | - |
| Portainer | 0.1 core | 256MB | 1GB |
| **총계** | **1.5 core** | **2.25GB** | **34GB** |

### Data Layer 추가 리소스

| 컴포넌트 | CPU | Memory | Disk |
|---------|-----|--------|------|
| OpenSearch Exporter | 0.1 core | 128MB | - |

### 기존 서버 요구사항 확인

**App Layer 서버:**
- 현재 사양: t3.medium (2 vCPU, 4GB RAM) 권장
- 추가 필요: 1.5 core, 2.25GB RAM, 34GB Disk
- **권장 업그레이드**: t3.medium → t3.large (2 vCPU, 8GB RAM) ⚠️

**Data Layer 서버:**
- 현재 사양: 충분 (OpenSearch Exporter는 경량)

---

## 7. 비용 예측 (AWS 기준)

### EC2 인스턴스 업그레이드
- t3.medium → t3.large: **+$30/월**

### 추가 스토리지 (EBS gp3)
- 50GB 추가: **+$5/월**

### 네트워크 트래픽
- 메트릭/로그 전송: 무시 가능 (프라이빗 네트워크)

**총 예상 비용: +$35/월**

---

## 8. 성공 지표

### 기술적 지표
- [ ] 모든 서비스의 로그가 Loki에 수집됨 (100%)
- [ ] HTTP 요청의 트레이스가 Tempo에 기록됨 (95% 이상)
- [ ] Data Layer 메트릭이 Prometheus에 수집됨 (100%)
- [ ] 알림이 5분 이내에 Slack으로 전달됨 (99% 이상)

### 운영적 지표
- [ ] 장애 탐지 시간 감소: 평균 10분 → **3분 이하**
- [ ] 장애 원인 파악 시간 감소: 평균 30분 → **10분 이하**
- [ ] 로그 검색 시간 단축: 평균 5분 → **30초 이하**
- [ ] 서비스 가용성 향상: 99% → **99.5% 이상**

---

## 9. 리스크 및 대응 방안

### 리스크 1: 리소스 부족으로 인한 성능 저하
**대응:**
- Phase별 점진적 도입
- 리소스 모니터링 후 필요시 서버 업그레이드
- 데이터 보관 기간 단축 (7일 → 3일)

### 리스크 2: 로그/메트릭 폭증으로 인한 비용 증가
**대응:**
- 샘플링 비율 조정 (트레이스 1% 샘플링)
- 불필요한 DEBUG 로그 비활성화
- 로그 압축 활성화

### 리스크 3: OpenTelemetry 계측으로 인한 성능 오버헤드
**대응:**
- Batch Span Processor 사용 (비동기 전송)
- 샘플링 전략 적용 (헤드 기반 샘플링)
- 성능 테스트 후 롤백 계획 준비

---

## 10. 참고 자료

### 공식 문서
- [Grafana Loki Documentation](https://grafana.com/docs/loki/latest/)
- [Grafana Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)

### 유사 사례
- [How we scaled our observability platform (Spotify)](https://engineering.atspotify.com/2020/10/how-we-scaled-our-observability-platform/)
- [Observability at Reddit](https://www.reddit.com/r/RedditEng/comments/qkfqpw/observability_at_reddit/)

---

## 11. 부록: Portainer 빠른 설치 가이드

### 설치 (5분)

```bash
# 1. docker-compose.yml에 서비스 추가 (위 Phase 0 참조)

# 2. Portainer 시작
cd ~/techeer-deploy/deploy/app
docker compose up -d portainer

# 3. 접속 확인
curl http://localhost:9000

# 4. 브라우저에서 초기 설정
# URL: http://<APP_SERVER_IP>:9000
# - 관리자 계정 생성 (8자 이상 비밀번호)
# - "Get Started" 클릭
# - "local" 환경 선택
```

### Nginx 리버스 프록시 설정 (선택)

```bash
# 1. Nginx 설정 파일 생성
cat > ~/techeer-deploy/deploy/app/nginx/conf.d/portainer.conf << 'EOF'
location /portainer/ {
    proxy_pass http://portainer:9000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # WebSocket 지원
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
EOF

# 2. Nginx 재시작
docker compose restart nginx

# 3. 외부 접속
# URL: http://<APP_SERVER_IP>/portainer/
```

### 주요 사용법

#### 1. 컨테이너 로그 확인
```
Containers → <컨테이너 선택> → Logs
- Auto-refresh 활성화
- Timestamps 표시
- Lines: 1000줄
```

#### 2. 컨테이너 재시작
```
Containers → <컨테이너 선택> → Restart
```

#### 3. 컨테이너 쉘 접속
```
Containers → <컨테이너 선택> → Console → /bin/sh
```

#### 4. Docker Compose 스택 업데이트
```
Stacks → <스택 선택> → Editor → Update the stack
```

### 보안 체크리스트
- [ ] 강력한 비밀번호 사용 (12자 이상, 특수문자 포함)
- [ ] HTTPS 사용 (Nginx 리버스 프록시 + Let's Encrypt)
- [ ] 외부 접속 차단 (127.0.0.1 바인딩 또는 방화벽)
- [ ] 정기적인 비밀번호 변경 (3개월마다)
- [ ] 팀원별 개별 계정 생성 (관리자 계정 공유 금지)

---

## 12. 문서 이력

| 버전 | 날짜 | 작성자 | 변경 내용 |
|-----|------|--------|----------|
| 1.0 | 2026-01-23 | Claude | 최초 작성 |
| 1.1 | 2026-01-23 | Claude | Portainer 추가 |
