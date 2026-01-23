# Monitoring Layer 배포 가이드

## 📋 문서 정보
- **작성일**: 2026-01-23
- **대상**: Monitoring Layer 3-Tier 아키텍처 배포
- **소요 시간**: 약 2시간

---

## 목차
1. [사전 준비](#1-사전-준비)
2. [보안 그룹 설정](#2-보안-그룹-설정)
3. [Monitoring Layer 배포](#3-monitoring-layer-배포)
4. [App Layer 수정](#4-app-layer-수정)
5. [검증 및 테스트](#5-검증-및-테스트)
6. [Grafana 대시보드 구성](#6-grafana-대시보드-구성)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. 사전 준비

### 1.1 필요한 정보 수집

다음 정보를 미리 확인하고 메모해두세요:

```bash
# App Layer 정보
APP_PUBLIC_IP=<App Layer 퍼블릭 IP>
APP_PRIVATE_IP=<App Layer 프라이빗 IP>

# Data Layer 정보
DATA_PRIVATE_IP=<Data Layer 프라이빗 IP>

# Monitoring Layer 정보 (신규 생성한 인스턴스)
MONITORING_PUBLIC_IP=<Monitoring Layer 퍼블릭 IP>
MONITORING_PRIVATE_IP=<Monitoring Layer 프라이빗 IP>
```

**Private IP 확인 방법:**
```bash
# EC2 인스턴스 내부에서 실행
hostname -I | awk '{print $1}'

# 또는 AWS Console에서 확인
# EC2 → Instances → 인스턴스 선택 → Private IPv4 addresses
```

### 1.2 SSH 키 설정

Monitoring Layer 서버에 SSH로 접속할 수 있는지 확인:

```bash
# 로컬 머신에서 실행
ssh -i ~/.ssh/your-key.pem ubuntu@${MONITORING_PUBLIC_IP}
```

---

## 2. 보안 그룹 설정

### 2.1 Monitoring Layer 보안 그룹 설정

**AWS Console → EC2 → Security Groups → Monitoring Layer SG**

#### Inbound Rules

| Type | Protocol | Port Range | Source | Description |
|------|----------|------------|--------|-------------|
| SSH | TCP | 22 | My IP | SSH 접속 (관리용) |
| Custom TCP | TCP | 9090 | My IP | Prometheus Web UI |
| Custom TCP | TCP | 3000 | My IP | Grafana Web UI |
| Custom TCP | TCP | 9000 | My IP | Portainer Web UI |
| Custom TCP | TCP | 9093 | My IP | Alertmanager Web UI |

#### Outbound Rules

| Type | Protocol | Port Range | Destination | Description |
|------|----------|------------|-------------|-------------|
| All traffic | All | All | 0.0.0.0/0 | 모든 아웃바운드 허용 |

### 2.2 App Layer 보안 그룹 수정

**Inbound Rules 추가:**

| Type | Protocol | Port Range | Source | Description |
|------|----------|------------|--------|-------------|
| Custom TCP | TCP | 9100 | Monitoring Layer SG | Node Exporter |
| Custom TCP | TCP | 8081 | Monitoring Layer SG | cAdvisor |
| Custom TCP | TCP | 8000 | Monitoring Layer SG | Django Metrics |

### 2.3 Data Layer 보안 그룹 수정

**Inbound Rules 추가:**

| Type | Protocol | Port Range | Source | Description |
|------|----------|------------|--------|-------------|
| Custom TCP | TCP | 9100 | Monitoring Layer SG | Node Exporter |
| Custom TCP | TCP | 9187 | Monitoring Layer SG | Postgres Exporter |
| Custom TCP | TCP | 9121 | Monitoring Layer SG | Redis Exporter |
| Custom TCP | TCP | 9114 | Monitoring Layer SG | OpenSearch Exporter |

### 2.4 보안 그룹 설정 주의사항

#### ⚠️ CIDR vs Security Group 참조 선택

AWS 보안 그룹 규칙에서 Source를 지정할 때 두 가지 방식이 있습니다:

**방법 1: Private IP (CIDR 형식) 사용 (권장)**
```
소스 유형: 사용자 지정
소스: <MONITORING_PRIVATE_IP>/32
예: 10.0.3.50/32
```

**방법 2: Security Group ID 참조**
```
소스 유형: 사용자 지정
소스: sg-xxxxxxxxx (Monitoring Layer의 Security Group ID)
```

#### ⚠️ 규칙 충돌 해결

**오류 메시지:**
```
기존 IPv4 CIDR 규칙에 참조된 그룹 ID를 지정할 수 없습니다.
```

**원인:**
- 동일한 포트에 대해 CIDR 블록 규칙이 이미 존재하는 상태에서 Security Group ID 규칙을 추가하려고 할 때 발생

**해결 방법:**
1. **기존 규칙 확인**: 해당 포트(예: 9100)의 기존 규칙 확인
2. **기존 CIDR 규칙 삭제**: `0.0.0.0/0` 또는 다른 CIDR 블록으로 된 규칙 제거
3. **새 규칙 추가**: Private IP/32 형식 또는 Security Group ID로 새 규칙 추가

**예시:**
```bash
# 삭제할 규칙: Port 9100, Source: 0.0.0.0/0
# 추가할 규칙: Port 9100, Source: 10.0.3.50/32
```

---

## 3. Monitoring Layer 배포

### 3.1 서버 초기 설정

```bash
# Monitoring Layer 서버에 SSH 접속
ssh -i ~/.ssh/your-key.pem ubuntu@${MONITORING_PUBLIC_IP}

# 시스템 업데이트
sudo apt-get update
sudo apt-get upgrade -y

# Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 설치 확인
docker --version
docker-compose --version

# 로그아웃 후 재접속 (docker 그룹 적용)
exit
ssh -i ~/.ssh/your-key.pem ubuntu@${MONITORING_PUBLIC_IP}
```

### 3.2 배포 파일 업로드

**로컬 머신에서 실행:**

```bash
# 프로젝트 루트 디렉토리에서 실행
cd /path/to/Backend

# deploy/monitoring 디렉토리 전체를 서버로 복사
scp -i ~/.ssh/your-key.pem -r deploy/monitoring ubuntu@${MONITORING_PUBLIC_IP}:~/monitoring-deploy

# 업로드 확인
ssh -i ~/.ssh/your-key.pem ubuntu@${MONITORING_PUBLIC_IP} "ls -la ~/monitoring-deploy"
```

### 3.3 환경 변수 설정

**Monitoring Layer 서버에서 실행:**

```bash
cd ~/monitoring-deploy

# .env 파일 생성
cp .env.example .env

# 환경 변수 편집
nano .env
```

**.env 파일 내용:**

```bash
# Grafana 관리자 비밀번호 (강력한 비밀번호 설정)
GRAFANA_ADMIN_PASSWORD=your_strong_password_here

# Monitoring Layer IP (현재 서버의 Private IP)
MONITORING_IP=<MONITORING_PRIVATE_IP>

# App Layer Private IP
APP_PRIVATE_IP=<APP_PRIVATE_IP>

# Data Layer Private IP
DATA_PRIVATE_IP=<DATA_PRIVATE_IP>

# Slack Webhook URL (선택 사항, 나중에 설정 가능)
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**저장 및 종료**: `Ctrl+O` → `Enter` → `Ctrl+X`

### 3.4 Prometheus 설정 업데이트

환경 변수 치환 (IP 주소를 실제 값으로 변경):

```bash
cd ~/monitoring-deploy

# prometheus.yml에서 환경 변수를 실제 IP로 치환
sed -i "s/\${APP_PRIVATE_IP}/$APP_PRIVATE_IP/g" prometheus.yml
sed -i "s/\${DATA_PRIVATE_IP}/$DATA_PRIVATE_IP/g" prometheus.yml

# 확인
cat prometheus.yml | grep -E "APP_PRIVATE_IP|DATA_PRIVATE_IP"
# 위 명령 실행 시 IP 주소가 치환되어 표시되어야 함
```

### 3.5 Promtail 설정 업데이트

**주의**: Promtail은 Docker socket을 통해 로그를 수집하므로, 현재 설정은 로컬 Docker 컨테이너 로그 수집용입니다. App/Data Layer의 로그를 수집하려면 각 서버에서 Promtail을 실행하거나 Docker 로그 드라이버를 사용해야 합니다.

**현재 구성에서는 Promtail을 일단 비활성화하고 나중에 설정:**

```bash
# docker-compose.yml 편집
nano docker-compose.yml
```

**promtail-app, promtail-data 서비스 주석 처리:**

```yaml
  # Promtail은 나중에 설정 (App/Data Layer에서 직접 실행 필요)
  # promtail-app:
  #   ...

  # promtail-data:
  #   ...
```

### 3.6 서비스 시작

```bash
cd ~/monitoring-deploy

# 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# Ctrl+C로 로그 보기 중지

# 컨테이너 상태 확인
docker-compose ps

# 모든 컨테이너가 Up 상태여야 함
```

### 3.7 헬스 체크

```bash
# Prometheus
curl http://localhost:9090/-/healthy
# 출력: Prometheus is Healthy.

# Grafana
curl http://localhost:3000/api/health
# 출력: {"database":"ok",...}

# Loki
curl http://localhost:3100/ready
# 출력: ready

# Tempo
curl http://localhost:3200/ready
# 출력: ready

# Alertmanager
curl http://localhost:9093/-/healthy
# 출력: OK
```

---

## 4. App Layer 수정

### 4.1 App Layer에서 모니터링 서비스 제거

**App Layer 서버에 SSH 접속:**

```bash
ssh -i ~/.ssh/your-key.pem ubuntu@${APP_PUBLIC_IP}
```

**기존 Prometheus/Grafana 중지 및 제거:**

```bash
cd ~/techeer-deploy/deploy/app

# 기존 서비스 중지
docker-compose down

# prometheus.yml 백업 (필요 시)
cp prometheus.yml prometheus.yml.backup

# grafana_data, prometheus_data 백업 (필요 시)
# sudo cp -r grafana_data grafana_data.backup
# sudo cp -r prometheus_data prometheus_data.backup
```

**docker-compose.yml 업데이트:**

```bash
# 로컬에서 수정한 파일을 서버로 업로드
# 로컬 머신에서 실행:
scp -i ~/.ssh/your-key.pem deploy/app/docker-compose.yml ubuntu@${APP_PUBLIC_IP}:~/techeer-deploy/deploy/app/
```

**또는 서버에서 직접 수정:**

```bash
nano docker-compose.yml
```

**prometheus, grafana 서비스 제거 (이미 수정된 파일을 업로드했다면 건너뛰기)**

```yaml
  # Prometheus, Grafana는 Monitoring Layer로 이전됨
  # Node Exporter와 cAdvisor는 메트릭 제공을 위해 유지

  node-exporter:
    # ... (기존 설정 유지, 포트만 9100으로 변경)
    ports:
      - "9100:9100"  # 외부 노출
```

**서비스 재시작:**

```bash
docker-compose up -d

# 컨테이너 확인
docker-compose ps

# prometheus, grafana가 목록에 없고
# node-exporter, cadvisor가 실행 중이어야 함
```

### 4.2 메트릭 수집 확인

**Monitoring Layer 서버에서 확인:**

```bash
# App Layer Node Exporter 접근 테스트
curl http://${APP_PRIVATE_IP}:9100/metrics | head -20

# App Layer cAdvisor 접근 테스트
curl http://${APP_PRIVATE_IP}:8081/metrics | head -20

# Django 메트릭 접근 테스트
curl http://${APP_PRIVATE_IP}:8000/internal/metrics | head -20
```

---

## 5. 검증 및 테스트

### 5.1 Prometheus 타겟 확인

**웹 브라우저에서 접속:**

```
URL: http://${MONITORING_PUBLIC_IP}:9090
```

1. **Status → Targets** 메뉴 클릭
2. 모든 타겟이 **UP** 상태인지 확인:
   - prometheus (자체)
   - node-exporter-monitoring
   - django-app
   - node-exporter-app
   - cadvisor-app
   - node-exporter-data
   - postgres-exporter
   - redis-exporter
   - opensearch-exporter

**트러블슈팅:**
- **DOWN 상태**: 보안 그룹 설정 확인, Private IP 확인
- **UNKNOWN 상태**: Prometheus 재시작 필요

### 5.2 Grafana 접속 및 Datasource 확인

**웹 브라우저에서 접속:**

```
URL: http://${MONITORING_PUBLIC_IP}:3000
Username: admin
Password: <GRAFANA_ADMIN_PASSWORD> (.env에 설정한 비밀번호)
```

**Datasource 확인:**

1. **Configuration (설정 아이콘) → Data sources**
2. Prometheus, Loki, Tempo가 자동으로 추가되어 있는지 확인
3. 각 Datasource 클릭 → **Test** 버튼 클릭 → "Data source is working" 확인

### 5.3 Portainer 접속

**웹 브라우저에서 접속:**

```
URL: http://${MONITORING_PUBLIC_IP}:9000
```

1. **첫 접속 시 관리자 계정 생성**
   - Username: admin
   - Password: (12자 이상 강력한 비밀번호)

2. **"Get Started"** 클릭

3. **"local"** 환경 선택

4. **Containers** 메뉴에서 모든 컨테이너 확인

### 5.4 메트릭 쿼리 테스트

**Prometheus에서 쿼리 테스트:**

```
URL: http://${MONITORING_PUBLIC_IP}:9090/graph
```

**테스트 쿼리:**

```promql
# 1. CPU 사용률
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 2. 메모리 사용률
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100

# 3. Django HTTP 요청 수
rate(django_http_requests_total_by_view_transport_method_total[5m])
```

---

## 6. Grafana 대시보드 구성

### 6.1 기본 대시보드 Import

**Grafana → Dashboards → Import**

추천 대시보드:

1. **Node Exporter Full**
   - Dashboard ID: `1860`
   - Datasource: Prometheus 선택
   - Import

2. **cAdvisor**
   - Dashboard ID: `14282`
   - Datasource: Prometheus 선택
   - Import

3. **PostgreSQL Database**
   - Dashboard ID: `9628`
   - Datasource: Prometheus 선택
   - Import

4. **Redis Dashboard**
   - Dashboard ID: `11835`
   - Datasource: Prometheus 선택
   - Import

### 6.2 커스텀 대시보드 생성

**Application Metrics 대시보드:**

1. **Dashboards → New Dashboard → Add visualization**

2. **Panel 추가 예시:**

   **Panel 1: HTTP Request Rate**
   ```promql
   rate(django_http_requests_total_by_view_transport_method_total[5m])
   ```

   **Panel 2: HTTP Response Time (P95)**
   ```promql
   histogram_quantile(0.95, rate(django_http_request_duration_seconds_bucket[5m]))
   ```

   **Panel 3: Error Rate (5xx)**
   ```promql
   rate(django_http_responses_total_by_status_total{status=~"5.."}[5m])
   ```

3. **Save Dashboard** 클릭

---

## 7. 트러블슈팅

### 7.0 보안 그룹 설정 오류

#### 오류: "기존 IPv4 CIDR 규칙에 참조된 그룹 ID를 지정할 수 없습니다"

**원인:**
- 동일한 포트에 대해 CIDR 블록 규칙과 Security Group ID 규칙을 동시에 가질 수 없음

**해결:**
```bash
# 1. AWS Console에서 기존 규칙 확인
# EC2 → Security Groups → 해당 SG 선택 → Inbound rules

# 2. 해당 포트의 기존 CIDR 규칙 삭제 (예: 0.0.0.0/0)

# 3. 새 규칙 추가 (두 가지 방법 중 선택)

# 방법 A: Private IP CIDR 형식 (권장)
# 소스: <MONITORING_PRIVATE_IP>/32
# 예: 10.0.3.50/32

# 방법 B: Security Group 참조
# 소스: sg-xxxxxxxxx (Monitoring Layer SG ID)
```

### 7.1 Prometheus 타겟이 DOWN 상태

**원인:**
- 보안 그룹 설정 누락
- Private IP 주소 오류
- 타겟 서비스 미실행

**해결:**
```bash
# 1. 보안 그룹 확인 (AWS Console)
# 2. Private IP 확인
ssh -i ~/.ssh/your-key.pem ubuntu@${APP_PUBLIC_IP} "hostname -I | awk '{print \$1}'"

# 3. 타겟 서비스 확인
ssh -i ~/.ssh/your-key.pem ubuntu@${APP_PUBLIC_IP} "docker ps | grep node-exporter"

# 4. 메트릭 엔드포인트 직접 접근 테스트
curl http://${APP_PRIVATE_IP}:9100/metrics
```

### 7.2 Grafana Datasource 연결 실패

**원인:**
- Prometheus/Loki/Tempo 서비스 미실행
- Docker 네트워크 문제

**해결:**
```bash
# Monitoring Layer 서버에서 확인
docker-compose ps

# 서비스 재시작
docker-compose restart prometheus loki tempo

# 네트워크 확인
docker network ls
docker network inspect monitoring_monitoring
```

### 7.3 Loki 로그가 수집되지 않음

**원인:**
- Promtail 설정 오류
- Docker socket 권한 문제

**해결:**
```bash
# Promtail 로그 확인
docker logs promtail-app
docker logs promtail-data

# Docker socket 권한 확인
ls -la /var/run/docker.sock

# Promtail 재시작
docker-compose restart promtail-app promtail-data
```

### 7.4 Portainer 접속 불가

**원인:**
- 보안 그룹 포트 9000 미허용
- Portainer 컨테이너 미실행

**해결:**
```bash
# Portainer 상태 확인
docker ps | grep portainer

# Portainer 로그 확인
docker logs portainer

# Portainer 재시작
docker-compose restart portainer
```

### 7.5 메모리 부족 에러

**원인:**
- t3.small(2GB RAM)에서 모든 서비스 실행 시 메모리 부족

**해결:**
```bash
# 메모리 사용량 확인
free -h

# Docker 컨테이너 메모리 확인
docker stats --no-stream

# Tempo 메모리 제한 확인
docker inspect tempo | grep -A 10 Memory

# 필요 시 Tempo 메모리 제한 조정
# docker-compose.yml에서 이미 768MB로 제한되어 있음
```

---

## 8. 다음 단계

### 8.1 Alertmanager Slack 연동

```bash
# Monitoring Layer 서버
cd ~/monitoring-deploy

# Slack Incoming Webhook 생성
# https://api.slack.com/messaging/webhooks

# .env 파일 업데이트
nano .env
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# alertmanager.yml 주석 해제
nano alertmanager.yml
# slack_configs 섹션 주석 해제

# Alertmanager 재시작
docker-compose restart alertmanager
```

### 8.2 Promtail 원격 로그 수집 설정

**App/Data Layer에 Promtail 설치:**

```bash
# App Layer 서버에서 실행
docker run -d \
  --name promtail \
  --restart always \
  -v /var/lib/docker/containers:/var/lib/docker/containers:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/promtail-config.yml:/etc/promtail/promtail-config.yml \
  grafana/promtail:2.9.0 \
  -config.file=/etc/promtail/promtail-config.yml
```

### 8.3 OpenTelemetry 트레이싱 구현

**Django 애플리케이션에 OpenTelemetry SDK 추가**

```bash
# requirements.txt
opentelemetry-api
opentelemetry-sdk
opentelemetry-instrumentation-django
opentelemetry-instrumentation-psycopg2
opentelemetry-instrumentation-redis
opentelemetry-exporter-otlp
```

**config/settings.py:**
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Tracer 설정
trace.set_tracer_provider(TracerProvider())
otlp_exporter = OTLPSpanExporter(
    endpoint="http://${MONITORING_PRIVATE_IP}:4317",
    insecure=True
)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)

# Django 자동 계측
from opentelemetry.instrumentation.django import DjangoInstrumentor
DjangoInstrumentor().instrument()
```

---

## 9. 체크리스트

배포 완료 전 다음 항목을 모두 확인하세요:

### 인프라
- [ ] Monitoring Layer EC2 인스턴스 생성 완료
- [ ] 보안 그룹 설정 완료 (Monitoring, App, Data)
- [ ] Private IP 주소 확인 및 기록

### Monitoring Layer
- [ ] Docker 및 Docker Compose 설치
- [ ] 배포 파일 업로드 완료
- [ ] 환경 변수 (.env) 설정 완료
- [ ] prometheus.yml IP 주소 치환 완료
- [ ] 모든 컨테이너 Up 상태 확인
- [ ] 헬스 체크 통과 (Prometheus, Grafana, Loki, Tempo, Alertmanager)

### App Layer
- [ ] Prometheus/Grafana 서비스 제거
- [ ] Node Exporter/cAdvisor 포트 외부 노출 (9100, 8081)
- [ ] 서비스 재시작 완료

### Prometheus
- [ ] 모든 타겟 UP 상태 확인
- [ ] 메트릭 쿼리 테스트 성공

### Grafana
- [ ] 로그인 성공
- [ ] Datasource 연결 확인 (Prometheus, Loki, Tempo)
- [ ] 기본 대시보드 Import 완료

### Portainer
- [ ] 접속 성공
- [ ] 관리자 계정 생성 완료
- [ ] 컨테이너 목록 확인

---

## 10. 유지보수

### 정기 점검 (주 1회)

```bash
# 1. 디스크 사용량 확인
df -h

# 2. 메모리 사용량 확인
free -h

# 3. Prometheus 데이터 크기 확인
du -sh ~/monitoring-deploy/prometheus_data

# 4. Loki 데이터 크기 확인
du -sh ~/monitoring-deploy/loki_data

# 5. 오래된 데이터 정리 (자동 실행되지만 확인)
docker-compose logs loki | grep compactor
```

### 백업 (월 1회)

```bash
# Grafana 데이터베이스 백업 (방법 1: 전체 DB)
docker cp grafana:/var/lib/grafana/grafana.db ~/grafana-db-backup-$(date +%Y%m%d).db

# Grafana 대시보드 백업 (방법 2: API 사용)
# 먼저 Grafana에서 API 키 생성 필요 (Configuration → API Keys)
# 대시보드 목록 조회
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:3000/api/search?type=dash-db

# 특정 대시보드 export (UID 필요)
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:3000/api/dashboards/uid/DASHBOARD_UID > \
  ~/grafana-dashboard-DASHBOARD_UID-$(date +%Y%m%d).json

# Prometheus 알림 규칙 백업
cp ~/monitoring-deploy/prometheus-alerts.yml ~/prometheus-alerts-backup-$(date +%Y%m%d).yml
```

---

## 11. 문의 및 지원

문제 발생 시:
1. 로그 확인: `docker-compose logs <service-name>`
2. 컨테이너 상태 확인: `docker-compose ps`
3. 보안 그룹 재확인
4. GitHub Issue 등록

---

**배포 완료를 축하합니다! 🎉**
