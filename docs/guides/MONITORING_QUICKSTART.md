# 모니터링 시스템 빠른 시작 가이드

## ✅ 구축 완료 상태 (2026-01-19)

**Phase 0 및 Phase 1 완료!**

### 완료된 작업
- ✅ **Django 메트릭 수집 활성화**
  - `/metrics` 엔드포인트 정상 작동
  - Prometheus에서 20개 이상의 Django 메트릭 수집 중

- ✅ **Grafana Provisioning 설정**
  - 자동 대시보드 배포 시스템 구축
  - Prometheus 데이터 소스 자동 설정

- ✅ **5개의 대시보드 배포**
  1. Docker + System Dashboard
  2. Django Prometheus
  3. PostgreSQL Database
  4. Redis Dashboard
  5. Node Exporter Full

### 접속 방법
- **Grafana UI**: http://localhost:3000
  - Username: `admin`
  - Password: `admin`
- **Prometheus UI**: http://localhost:9090
- **Django Metrics**: http://localhost:8000/metrics

---

## 목차
1. [모니터링 시스템 확인](#1-모니터링-시스템-확인)
2. [대시보드 사용 가이드](#2-대시보드-사용-가이드)
3. [추가 대시보드 설정](#3-추가-대시보드-설정)
4. [기본 알림 설정](#4-기본-알림-설정)
5. [로그 확인](#5-로그-확인)
6. [참고: 초기 구축 과정](#6-참고-초기-구축-과정)

---

## 1. 모니터링 시스템 확인

### 1.1 Grafana 대시보드 접속

1. 브라우저에서 http://localhost:3000 접속
2. 로그인 (Username: `admin`, Password: `admin`)
3. 좌측 메뉴 → **Dashboards** 클릭

### 1.2 사용 가능한 대시보드 목록

| 대시보드 | 설명 | 주요 메트릭 |
|---------|------|-----------|
| **Docker + System Dashboard** | Docker 컨테이너 및 시스템 리소스 | 컨테이너 메모리/CPU, 네트워크 I/O |
| **Django Prometheus** | Django 애플리케이션 성능 | HTTP 요청/응답, DB 쿼리, 에러율 |
| **PostgreSQL Database** | PostgreSQL 데이터베이스 | 연결 수, 쿼리 성능, 캐시 적중률 |
| **Redis Dashboard** | Redis 캐시 서버 | 메모리 사용량, 명령 처리율, 키 개수 |
| **Node Exporter Full** | 호스트 시스템 리소스 | CPU, 메모리, 디스크, 네트워크 |

### 1.3 Prometheus 메트릭 확인

```bash
# Django 메트릭 확인
curl http://localhost:8000/metrics | head -20

# Prometheus Targets 확인
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# 수집 중인 Django 메트릭 개수
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | \
  jq '.data[] | select(. | startswith("django"))' | wc -l
```

---

## 2. 대시보드 사용 가이드

### 2.1 Django Prometheus 대시보드

**주요 패널**:
- **Request Rate**: 초당 HTTP 요청 수
- **Response Time**: P50/P95/P99 응답 시간
- **Error Rate**: 4xx/5xx 에러율
- **Database Queries**: DB 쿼리 실행 시간

**확인 방법**:
1. Grafana → Dashboards → "a Django Prometheus" 선택
2. Time Range를 조정하여 원하는 기간의 데이터 확인 (기본: Last 24 hours)

### 2.2 PostgreSQL Database 대시보드

**주요 패널**:
- **Active Connections**: 현재 활성 연결 수
- **Transaction Rate**: 초당 트랜잭션 수
- **Cache Hit Ratio**: 캐시 적중률 (높을수록 좋음)
- **Slow Queries**: 느린 쿼리 목록

### 2.3 Redis Dashboard 대시보드

**주요 패널**:
- **Memory Usage**: 메모리 사용량 및 최대값
- **Commands Processed**: 초당 처리되는 명령 수
- **Keys**: 현재 저장된 키 개수
- **Hit Rate**: 캐시 적중률

### 2.4 Docker + System Dashboard

**주요 패널**:
- **Container Memory**: 각 컨테이너의 메모리 사용량
- **Container CPU**: 각 컨테이너의 CPU 사용률
- **Network I/O**: 컨테이너별 네트워크 트래픽

### 2.5 Node Exporter Full 대시보드

**주요 패널**:
- **CPU Usage**: 호스트 CPU 사용률
- **Memory Usage**: 호스트 메모리 사용량
- **Disk I/O**: 디스크 읽기/쓰기 속도
- **Network Traffic**: 네트워크 수신/송신 속도

---

## 3. 추가 대시보드 설정

새로운 대시보드를 추가하려면 다음 단계를 따르세요:

### 3.1 Grafana.com에서 대시보드 찾기

1. https://grafana.com/grafana/dashboards/ 방문
2. 원하는 대시보드 검색 (예: "Celery", "Nginx" 등)
3. 대시보드 ID 확인 (예: ID: 12345)

### 3.2 대시보드 다운로드 및 추가

```bash
# 대시보드 다운로드 (ID: 12345, revision: 1)
curl -s https://grafana.com/api/dashboards/12345/revisions/1/download \
  -o grafana/provisioning/dashboards/json/my-dashboard.json

# Grafana 재시작
docker-compose restart grafana
```

---

## 4. 기본 알림 설정

**(준비 중 - Phase 1 다음 단계)**

AlertManager 설정 및 알림 규칙은 Phase 1의 다음 단계에서 구축됩니다.

---

## 5. 로그 확인

### 5.1 서비스 로그 확인

```bash
# 모든 서비스 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f app
docker-compose logs -f prometheus
docker-compose logs -f grafana

# 최근 50줄 로그
docker-compose logs --tail 50 app
```

### 5.2 Prometheus 상태 확인

```bash
# Prometheus 타겟 상태
curl http://localhost:9090/api/v1/targets | jq

# Prometheus 설정 확인
curl http://localhost:9090/api/v1/status/config | jq
```

---

## 6. 참고: 초기 구축 과정

이 섹션은 이미 완료된 구축 과정을 참고용으로 기록합니다.

### 6.1 Django 메트릭 활성화

### 1.1 URL 설정

`config/urls.py`에 다음 내용을 추가:

```python
from django.urls import path, include

urlpatterns = [
    # 기존 URL 패턴들...

    # Prometheus 메트릭 엔드포인트
    path('', include('django_prometheus.urls')),
]
```

### 1.2 Prometheus 설정 업데이트

`prometheus/prometheus.yml`에 Django 앱 추가:

```yaml
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'django-app'
    static_configs:
      - targets: ['app:8000']
    metrics_path: '/metrics'

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter:9121']
```

### 1.3 Prometheus 재시작

```bash
docker-compose restart prometheus
```

### 1.4 메트릭 확인

브라우저에서 다음 URL 접속:
- Django 메트릭: http://localhost:8000/metrics
- Prometheus UI: http://localhost:9090

Prometheus UI에서 Status → Targets 확인하여 `django-app`이 UP 상태인지 확인.

---

---

## 2. cAdvisor 대시보드 수정

### 2.1 현재 문제 확인

cAdvisor는 메트릭을 수집하고 있지만, macOS 환경에서 컨테이너 메타데이터(`name`, `image` 레이블)가 누락되어 기본 대시보드를 사용할 수 없습니다.

**메트릭 확인**:
```bash
# 현재 수집 중인 메트릭 확인
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{id=~"/docker/.*"}' | jq

# 메트릭 개수 확인
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes' | \
  jq '.data.result | length'
```

### 2.2 커스텀 대시보드 생성

Grafana에서 컨테이너 ID 기반 대시보드를 생성합니다.

#### 단계 1: 새 대시보드 생성
1. Grafana (http://localhost:3000) 접속
2. 좌측 메뉴 → **Dashboards** → **New** → **New dashboard**
3. **Add visualization** 클릭
4. 데이터 소스로 **Prometheus** 선택

#### 단계 2: 패널 추가

**패널 1: 컨테이너 메모리 사용량**
```promql
container_memory_usage_bytes{id=~"/docker/.*"}
```
- Panel title: "Container Memory Usage"
- Legend: "{{id}}"
- Unit: "bytes"

**패널 2: 컨테이너 CPU 사용률**
```promql
rate(container_cpu_usage_seconds_total{id=~"/docker/.*"}[5m])
```
- Panel title: "Container CPU Usage"
- Legend: "{{id}}"
- Unit: "percentunit"

**패널 3: 네트워크 I/O**
```promql
# 수신
rate(container_network_receive_bytes_total{id=~"/docker/.*"}[5m])
# 송신
rate(container_network_transmit_bytes_total{id=~"/docker/.*"}[5m])
```
- Panel title: "Container Network I/O"
- Unit: "Bps" (bytes per second)

**패널 4: 실행 중인 컨테이너 수**
```promql
count(container_last_seen{id=~"/docker/.*"})
```
- Panel title: "Running Docker Containers"
- Visualization: Stat

#### 단계 3: 대시보드 저장
- 우측 상단 **Save dashboard** 클릭
- 이름: "Docker Container Monitoring"
- 저장

### 2.3 검증

대시보드에서 다음을 확인:
- ✅ 모든 Docker 컨테이너의 메모리 사용량 표시
- ✅ CPU 사용률 그래프
- ✅ 네트워크 트래픽 시각화
- ✅ "No data" 문제 해결

---

## 3. Grafana 추가 대시보드 생성

### 3.1 Grafana 접속

http://localhost:3000 접속 후 로그인 (admin/admin)

### 3.2 데이터 소스 추가

1. 좌측 메뉴 → **Connections** → **Data sources**
2. **Add data source** 클릭
3. **Prometheus** 선택
4. 다음 정보 입력:
   - **Name**: Prometheus
   - **URL**: `http://prometheus:9090`
5. **Save & test** 클릭

### 3.3 Django 메트릭 대시보드 생성

#### Django 요청 메트릭 대시보드

1. 좌측 메뉴 → **Dashboards** → **New** → **New dashboard**
2. **Add visualization** 클릭
3. 데이터 소스로 **Prometheus** 선택

#### 패널 1: 초당 요청 수 (RPS)

**쿼리**:
```promql
sum(rate(django_http_requests_total_by_method[5m]))
```

**설정**:
- Panel title: "Requests per Second"
- Legend: "RPS"
- Unit: "reqps" (requests per second)

#### 패널 2: 평균 응답 시간

**쿼리**:
```promql
rate(django_http_requests_latency_seconds_sum[5m]) /
rate(django_http_requests_latency_seconds_count[5m])
```

**설정**:
- Panel title: "Average Response Time"
- Unit: "s" (seconds)

#### 패널 3: HTTP 상태 코드 분포

**쿼리**:
```promql
sum by (status) (rate(django_http_responses_total_by_status[5m]))
```

**설정**:
- Panel title: "HTTP Status Codes"
- Legend: "{{status}}"
- Visualization: Pie chart 또는 Bar gauge

#### 패널 4: 에러율

**쿼리**:
```promql
sum(rate(django_http_responses_total_by_status{status=~"5.."}[5m])) /
sum(rate(django_http_responses_total_by_status[5m])) * 100
```

**설정**:
- Panel title: "Error Rate (%)"
- Unit: "percent (0-100)"
- Thresholds: Yellow at 1%, Red at 5%

### 3.4 대시보드 저장

- 우측 상단 **Save dashboard** 클릭
- 이름: "Django Application Metrics"
- 저장

---

## 4. 기본 알림 설정

### 4.1 AlertManager 설치

`docker-compose.yml`에 AlertManager 추가:

```yaml
services:
  # 기존 서비스들...

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./prometheus/alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    networks:
      - django-network
    restart: always

volumes:
  # 기존 볼륨들...
  alertmanager_data:
```

### 4.2 AlertManager 설정 파일 생성

`prometheus/alertmanager.yml` 생성:

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'slack-notifications'

  routes:
    - match:
        severity: critical
      receiver: 'slack-critical'
      continue: true

    - match:
        severity: high
      receiver: 'slack-high'

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#monitoring'
        title: 'Monitoring Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ .Annotations.description }}\n{{ end }}'

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
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ .Annotations.description }}\n{{ end }}'
```

### 4.3 알림 규칙 생성

`prometheus/alert_rules.yml` 생성:

```yaml
groups:
  - name: django_alerts
    interval: 30s
    rules:
      # Critical: 서비스 다운
      - alert: DjangoServiceDown
        expr: up{job="django-app"} == 0
        for: 1m
        labels:
          severity: critical
          service: django
        annotations:
          summary: "Django 서비스가 다운되었습니다"
          description: "Django 애플리케이션이 1분 이상 응답하지 않습니다."

      # Critical: 높은 에러율
      - alert: HighErrorRate
        expr: |
          sum(rate(django_http_responses_total_by_status{status=~"5.."}[5m])) /
          sum(rate(django_http_responses_total_by_status[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
          service: django
        annotations:
          summary: "높은 서버 에러율 감지"
          description: "5분간 5xx 에러율이 5%를 초과했습니다. (현재: {{ $value | humanizePercentage }})"

      # High: 높은 응답 시간
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            rate(django_http_requests_latency_seconds_bucket[5m])) > 1
        for: 10m
        labels:
          severity: high
          service: django
        annotations:
          summary: "높은 API 응답 시간"
          description: "P95 응답 시간이 1초를 초과했습니다. (현재: {{ $value }}s)"

      # Medium: 높은 메모리 사용률
      - alert: HighMemoryUsage
        expr: |
          container_memory_usage_bytes{name="django"} /
          container_spec_memory_limit_bytes{name="django"} > 0.85
        for: 15m
        labels:
          severity: medium
          service: django
        annotations:
          summary: "Django 컨테이너 메모리 사용률 높음"
          description: "메모리 사용률이 85%를 초과했습니다. (현재: {{ $value | humanizePercentage }})"

  - name: database_alerts
    interval: 30s
    rules:
      # Critical: PostgreSQL 다운
      - alert: PostgreSQLDown
        expr: pg_up == 0
        for: 1m
        labels:
          severity: critical
          service: postgresql
        annotations:
          summary: "PostgreSQL 연결 실패"
          description: "PostgreSQL 데이터베이스가 응답하지 않습니다."

      # High: 많은 활성 연결
      - alert: TooManyConnections
        expr: pg_stat_activity_count > 80
        for: 10m
        labels:
          severity: high
          service: postgresql
        annotations:
          summary: "PostgreSQL 연결 수 높음"
          description: "활성 연결이 {{ $value }}개입니다."

  - name: redis_alerts
    interval: 30s
    rules:
      # Critical: Redis 다운
      - alert: RedisDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: critical
          service: redis
        annotations:
          summary: "Redis 연결 실패"
          description: "Redis 서버가 응답하지 않습니다."

      # High: 높은 메모리 사용률
      - alert: RedisHighMemory
        expr: |
          redis_memory_used_bytes /
          redis_memory_max_bytes > 0.9
        for: 10m
        labels:
          severity: high
          service: redis
        annotations:
          summary: "Redis 메모리 사용률 높음"
          description: "메모리 사용률이 90%를 초과했습니다."
```

### 4.4 Prometheus 설정 업데이트

`prometheus/prometheus.yml`에 AlertManager와 규칙 파일 추가:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# AlertManager 설정
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# 알림 규칙 파일
rule_files:
  - 'alert_rules.yml'

scrape_configs:
  # 기존 scrape_configs...
```

### 4.5 서비스 재시작

```bash
docker-compose up -d alertmanager
docker-compose restart prometheus
```

### 4.6 알림 확인

- AlertManager UI: http://localhost:9093
- Prometheus Alerts: http://localhost:9090/alerts

---

## 5. 로그 확인

### 5.1 컨테이너 로그 확인

```bash
# Django 애플리케이션 로그
docker-compose logs -f app

# Celery Worker 로그
docker-compose logs -f celery-worker

# PostgreSQL 로그
docker-compose logs -f db

# 모든 서비스 로그
docker-compose logs -f
```

### 5.2 특정 시간대 로그

```bash
# 최근 100줄
docker-compose logs --tail 100 app

# 최근 1시간
docker-compose logs --since 1h app

# 특정 시간 이후
docker-compose logs --since 2026-01-19T10:00:00 app
```

### 5.3 에러 로그만 필터링

```bash
# ERROR 레벨 로그만
docker-compose logs app | grep ERROR

# 5xx 에러 로그
docker-compose logs app | grep "status=5"

# 예외 스택 트레이스
docker-compose logs app | grep -A 10 "Traceback"
```

### 5.4 로그 파일로 저장

```bash
# 로그를 파일로 저장
docker-compose logs app > app.log

# 실시간 로그를 파일에 저장하면서 화면에도 출력
docker-compose logs -f app | tee app.log
```

---

## 6. 다음 단계

### 6.1 커스텀 메트릭 추가

Django 애플리케이션에 비즈니스 메트릭 추가:

```python
# companies/views.py
from prometheus_client import Counter, Histogram
import time

# 메트릭 정의
api_calls = Counter(
    'company_api_calls_total',
    'Total company API calls',
    ['endpoint', 'method']
)

api_latency = Histogram(
    'company_api_latency_seconds',
    'Company API latency',
    ['endpoint']
)

class CompanyViewSet(viewsets.ModelViewSet):
    def list(self, request, *args, **kwargs):
        # 메트릭 기록
        api_calls.labels(endpoint='list', method='GET').inc()

        start_time = time.time()
        response = super().list(request, *args, **kwargs)
        duration = time.time() - start_time

        api_latency.labels(endpoint='list').observe(duration)

        return response
```

### 6.2 추가 대시보드

다음 대시보드들을 추가로 생성해보세요:

1. **시스템 리소스 대시보드**
   - CPU, 메모리, 디스크, 네트워크

2. **데이터베이스 대시보드**
   - 쿼리 성능, 연결 수, 캐시 적중률

3. **Celery 대시보드**
   - 작업 처리율, 큐 길이, 실패율

4. **비즈니스 메트릭 대시보드**
   - 사용자 활동, API 사용 패턴

### 6.3 로그 수집 시스템 구축

OpenSearch로 로그를 수집하여 검색 및 분석:

1. Filebeat 또는 Fluentd 설치
2. 로그 파싱 및 인덱싱
3. OpenSearch Dashboards에서 시각화

자세한 내용은 `docs/plans/MONITORING_SYSTEM.md` 참조.

---

## 7. 문제 해결

### 7.1 메트릭이 수집되지 않는 경우

```bash
# Prometheus 타겟 상태 확인
curl http://localhost:9090/api/v1/targets | jq

# Django 메트릭 엔드포인트 확인
curl http://localhost:8000/metrics

# Prometheus 로그 확인
docker-compose logs prometheus
```

### 7.2 Grafana 데이터 소스 연결 실패

- Prometheus URL이 `http://prometheus:9090`인지 확인 (Docker 네트워크 내부 주소)
- Prometheus가 실행 중인지 확인: `docker-compose ps prometheus`
- 네트워크 연결 확인: `docker-compose exec grafana ping prometheus`

### 7.3 알림이 전송되지 않는 경우

- Slack Webhook URL 확인
- AlertManager 설정 파일 문법 확인
- AlertManager 로그 확인: `docker-compose logs alertmanager`
- 알림 규칙 활성화 확인: http://localhost:9090/alerts

---

## 8. 유용한 명령어 모음

```bash
# 모니터링 스택 전체 재시작
docker-compose restart prometheus grafana alertmanager

# 특정 서비스만 재시작
docker-compose restart app

# 로그 실시간 모니터링 (여러 서비스)
docker-compose logs -f app celery-worker db redis

# 리소스 사용량 확인
docker stats

# 컨테이너 상태 확인
docker-compose ps

# Prometheus 설정 검증
docker-compose exec prometheus promtool check config /etc/prometheus/prometheus.yml

# AlertManager 설정 검증
docker-compose exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

---

## 9. 참고 자료

- [전체 모니터링 계획](../plans/MONITORING_SYSTEM.md)
- [Prometheus 공식 문서](https://prometheus.io/docs/)
- [Grafana 공식 문서](https://grafana.com/docs/)
- [django-prometheus GitHub](https://github.com/korfuri/django-prometheus)

---

**문서 버전**: 1.0
**최종 수정일**: 2026-01-19
