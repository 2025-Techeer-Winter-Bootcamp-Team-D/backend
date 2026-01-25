# 모니터링 아키텍처 비교 분석

## 📋 문서 정보
- **작성일**: 2026-01-23
- **목적**: 모니터링 전용 인스턴스 도입 검토

---

## 1. 현재 상황

### 인스턴스 구성
| Layer | 인스턴스 타입 | vCPU | RAM | 용도 |
|-------|--------------|------|-----|------|
| App Layer | t3.small | 2 | 2GB | Django, Celery, Nginx, KIS, Persistence Worker |
| Data Layer | t3.small | 2 | 2GB | PostgreSQL, Redis, OpenSearch, RabbitMQ |

### 문제점
- ⚠️ **t3.small 스펙이 부족**: 모니터링 스택 추가 시 2GB RAM으로 부족
- ⚠️ **리소스 경합**: 애플리케이션과 모니터링이 같은 리소스 사용
- ⚠️ **SPOF (Single Point of Failure)**: App 서버 다운 시 모니터링도 중단

---

## 2. 아키텍처 옵션 비교

### Option A: 기존 서버 업그레이드 (2-Tier)

```
┌─────────────────────────────────┐
│       App Layer (t3.medium)     │
│  - Django, Celery, Nginx        │
│  - 모니터링 스택 전체             │
│  - Prometheus, Grafana          │
│  - Loki, Tempo, Alertmanager    │
│  - Portainer                    │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│       Data Layer (t3.small)     │
│  - PostgreSQL, Redis            │
│  - OpenSearch, RabbitMQ         │
│  - Exporters                    │
└─────────────────────────────────┘
```

**비용:**
- App Layer: t3.small → **t3.medium** ($16.79 → $33.58)
- Data Layer: t3.small ($16.79)
- **총 월 비용: $50.37**

**장점:**
- ✅ 관리할 서버 수가 적음 (2개)
- ✅ 네트워크 홉이 적음

**단점:**
- ❌ App 서버 다운 시 모니터링도 중단 (SPOF)
- ❌ 애플리케이션과 모니터링이 리소스 경합
- ❌ App 서버에 부하가 집중됨
- ❌ 확장성 제한적

---

### Option B: 모니터링 전용 인스턴스 (3-Tier) ⭐ 권장

```
┌─────────────────────────────────┐
│       App Layer (t3.small)      │
│  - Django, Celery, Nginx        │
│  - KIS Publisher                │
│  - Persistence Worker           │
│  - Subscribe Handler            │
│  - Flower                       │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│       Data Layer (t3.small)     │
│  - PostgreSQL, Redis            │
│  - OpenSearch, RabbitMQ         │
│  - Node Exporter (Data)         │
│  - Postgres/Redis Exporter      │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│   Monitoring Layer (t3.small)   │
│  - Prometheus                   │
│  - Grafana                      │
│  - Loki + Promtail              │
│  - Tempo                        │
│  - Alertmanager                 │
│  - Portainer                    │
│  - Node Exporter (Monitoring)   │
└─────────────────────────────────┘
```

**비용:**
- App Layer: t3.small ($16.79)
- Data Layer: t3.small ($16.79)
- Monitoring Layer: **t3.small ($16.79)** ⭐ 신규
- **총 월 비용: $50.37**

**장점:**
- ✅ **비용 동일**: Option A와 같은 비용 ($50.37/월)
- ✅ **리소스 격리**: 모니터링이 애플리케이션에 영향 주지 않음
- ✅ **고가용성**: App 다운되어도 모니터링 시스템은 정상 작동
- ✅ **독립적 확장**: 각 Layer를 필요에 따라 개별 스케일링
- ✅ **안정성**: 모니터링 시스템이 안정적으로 메트릭 수집 가능
- ✅ **디버깅 용이**: App 장애 시에도 모니터링 데이터 조회 가능

**단점:**
- ⚠️ 관리할 서버 수 증가 (3개)
- ⚠️ 네트워크 설정 복잡도 증가 (보안 그룹 등)

---

## 3. 리소스 사용량 예측

### Option A: t3.medium App Layer

| 컴포넌트 | CPU | Memory |
|---------|-----|--------|
| Django + Gunicorn | 0.5 | 512MB |
| Celery Worker | 0.3 | 256MB |
| Celery Beat | 0.1 | 128MB |
| Subscribe Handler | 0.2 | 256MB |
| KIS Publisher | 0.3 | 256MB |
| Persistence Worker | 0.2 | 256MB |
| Nginx | 0.1 | 64MB |
| Flower | 0.1 | 128MB |
| **앱 총계** | **1.8** | **1856MB** |
| Prometheus | 0.3 | 512MB |
| Grafana | 0.2 | 256MB |
| Loki | 0.5 | 512MB |
| Promtail | 0.1 | 128MB |
| Tempo | 0.5 | 1024MB |
| Alertmanager | 0.2 | 256MB |
| Portainer | 0.1 | 256MB |
| **모니터링 총계** | **1.9** | **2944MB** |
| **전체 총계** | **3.7** | **4800MB** |

**결론**: t3.medium (2 vCPU, 4GB RAM)으로는 **부족** ❌
→ **t3.large (2 vCPU, 8GB RAM) 필요** → 비용 $67.16/월

---

### Option B: 3-Tier 분산

#### App Layer (t3.small)
| 컴포넌트 | CPU | Memory |
|---------|-----|--------|
| Django + Gunicorn | 0.5 | 512MB |
| Celery Worker | 0.3 | 256MB |
| Celery Beat | 0.1 | 128MB |
| Subscribe Handler | 0.2 | 256MB |
| KIS Publisher | 0.3 | 256MB |
| Persistence Worker | 0.2 | 256MB |
| Nginx | 0.1 | 64MB |
| Flower | 0.1 | 128MB |
| Node Exporter | 0.1 | 64MB |
| cAdvisor | 0.1 | 128MB |
| **총계** | **2.0** | **2048MB** |

**여유 공간**: 0 vCPU, 0MB RAM (딱 맞음) ✅

#### Data Layer (t3.small)
| 컴포넌트 | CPU | Memory |
|---------|-----|--------|
| PostgreSQL | 0.5 | 512MB |
| Redis | 0.2 | 256MB |
| OpenSearch | 0.5 | 512MB |
| RabbitMQ | 0.2 | 256MB |
| Node Exporter | 0.1 | 64MB |
| Postgres Exporter | 0.1 | 64MB |
| Redis Exporter | 0.1 | 64MB |
| OpenSearch Exporter | 0.1 | 64MB |
| **총계** | **1.8** | **1792MB** |

**여유 공간**: 0.2 vCPU, 256MB RAM ✅

#### Monitoring Layer (t3.small)
| 컴포넌트 | CPU | Memory |
|---------|-----|--------|
| Prometheus | 0.3 | 512MB |
| Grafana | 0.2 | 256MB |
| Loki | 0.5 | 512MB |
| Promtail | 0.1 | 128MB |
| Tempo | 0.5 | 1024MB |
| Alertmanager | 0.2 | 256MB |
| Portainer | 0.1 | 256MB |
| Node Exporter | 0.1 | 64MB |
| **총계** | **2.0** | **3008MB** |

**문제**: 메모리 1GB 초과 ⚠️

**해결책**: Tempo 메모리 제한 조정
```yaml
# Tempo 메모리 제한
environment:
  - "TEMPO_QUERY_MAX_CONCURRENT=2"
  - "TEMPO_STORAGE_TRACE_BACKEND=local"
resources:
  limits:
    memory: 768MB  # 1024MB → 768MB
```

**조정 후 총계**: 2.0 vCPU, **2752MB** RAM ✅

---

## 4. 네트워크 구성

### 보안 그룹 설정

#### App Layer Security Group
**Inbound:**
- 80/443 (HTTP/HTTPS) ← 0.0.0.0/0 (Public)
- 22 (SSH) ← My IP (관리용)

**Outbound:**
- All traffic → Data Layer (Private IP)
- All traffic → Monitoring Layer (Private IP)
- All traffic → 0.0.0.0/0 (외부 API 호출용)

#### Data Layer Security Group
**Inbound:**
- 5432 (PostgreSQL) ← App Layer SG
- 6379 (Redis) ← App Layer SG
- 9200/9600 (OpenSearch) ← App Layer SG
- 5672/15672 (RabbitMQ) ← App Layer SG
- 9100 (Node Exporter) ← Monitoring Layer SG
- 9187 (Postgres Exporter) ← Monitoring Layer SG
- 9121 (Redis Exporter) ← Monitoring Layer SG
- 9114 (OpenSearch Exporter) ← Monitoring Layer SG
- 22 (SSH) ← My IP (관리용)

**Outbound:**
- All traffic → 0.0.0.0/0

#### Monitoring Layer Security Group
**Inbound:**
- 9090 (Prometheus) ← My IP (관리용)
- 3000 (Grafana) ← My IP (관리용)
- 9000/9443 (Portainer) ← My IP (관리용)
- 22 (SSH) ← My IP (관리용)

**Outbound:**
- All traffic → App Layer (메트릭 수집)
- All traffic → Data Layer (메트릭 수집)
- All traffic → 0.0.0.0/0 (Slack webhook 등)

### Prometheus 설정 (Monitoring Layer)

```yaml
# prometheus.yml
scrape_configs:
  # Self monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # App Layer
  - job_name: 'django-app'
    metrics_path: /internal/metrics
    static_configs:
      - targets: ['<APP_PRIVATE_IP>:8000']

  - job_name: 'node-exporter-app'
    static_configs:
      - targets: ['<APP_PRIVATE_IP>:9100']

  - job_name: 'cadvisor-app'
    static_configs:
      - targets: ['<APP_PRIVATE_IP>:8081']

  # Data Layer
  - job_name: 'node-exporter-data'
    static_configs:
      - targets: ['<DATA_PRIVATE_IP>:9100']

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['<DATA_PRIVATE_IP>:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['<DATA_PRIVATE_IP>:9121']

  - job_name: 'opensearch-exporter'
    static_configs:
      - targets: ['<DATA_PRIVATE_IP>:9114']

  # Monitoring Layer
  - job_name: 'node-exporter-monitoring'
    static_configs:
      - targets: ['localhost:9100']
```

---

## 5. 배포 전략

### 1단계: Monitoring Layer 인스턴스 생성 (1일)

```bash
# AWS EC2 생성
# - AMI: Ubuntu 22.04 LTS
# - Instance Type: t3.small
# - VPC: 기존 VPC (App, Data와 동일)
# - Subnet: Private Subnet (권장)
# - Security Group: 위 설정 참조
# - Storage: 30GB gp3

# Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo usermod -aG docker ubuntu

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2단계: 배포 디렉토리 구조 생성 (10분)

```bash
mkdir -p ~/monitoring-deploy/{prometheus,grafana,loki,tempo,alertmanager}
cd ~/monitoring-deploy
```

### 3단계: docker-compose.yml 작성 (30분)

```yaml
# ~/monitoring-deploy/docker-compose.yml
services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus-alerts.yml:/etc/prometheus/alerts.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'
      - '--storage.tsdb.retention.size=10GB'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
    ports:
      - "9090:9090"
    networks:
      - monitoring
    restart: always

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
      - GF_SERVER_ROOT_URL=http://<MONITORING_IP>:3000
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
    ports:
      - "3000:3000"
    networks:
      - monitoring
    restart: always

  loki:
    image: grafana/loki:2.9.0
    container_name: loki
    volumes:
      - ./loki-config.yml:/etc/loki/loki-config.yml
      - loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yml
    ports:
      - "3100:3100"
    networks:
      - monitoring
    restart: always

  promtail-app:
    image: grafana/promtail:2.9.0
    container_name: promtail-app
    volumes:
      - ./promtail-app-config.yml:/etc/promtail/promtail-config.yml
    command: -config.file=/etc/promtail/promtail-config.yml
    networks:
      - monitoring
    restart: always

  promtail-data:
    image: grafana/promtail:2.9.0
    container_name: promtail-data
    volumes:
      - ./promtail-data-config.yml:/etc/promtail/promtail-config.yml
    command: -config.file=/etc/promtail/promtail-config.yml
    networks:
      - monitoring
    restart: always

  tempo:
    image: grafana/tempo:latest
    container_name: tempo
    volumes:
      - ./tempo-config.yml:/etc/tempo.yml
      - tempo_data:/tmp/tempo
    command: -config.file=/etc/tempo.yml
    ports:
      - "3200:3200"
      - "4317:4317"
      - "4318:4318"
    networks:
      - monitoring
    deploy:
      resources:
        limits:
          memory: 768M
    restart: always

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    ports:
      - "9093:9093"
    networks:
      - monitoring
    restart: always

  portainer:
    image: portainer/portainer-ce:latest
    container_name: portainer
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - portainer_data:/data
    ports:
      - "9000:9000"
      - "9443:9443"
    networks:
      - monitoring
    restart: always

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.rootfs=/rootfs'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    ports:
      - "9100:9100"
    networks:
      - monitoring
    restart: always

volumes:
  prometheus_data:
  grafana_data:
  loki_data:
  tempo_data:
  alertmanager_data:
  portainer_data:

networks:
  monitoring:
    driver: bridge
```

### 4단계: 설정 파일 작성 (1시간)

- `prometheus.yml` (위 네트워크 구성 참조)
- `loki-config.yml`
- `tempo-config.yml`
- `alertmanager.yml`
- `promtail-app-config.yml` (App Layer 로그 수집용)
- `promtail-data-config.yml` (Data Layer 로그 수집용)

### 5단계: App/Data Layer 수정 (30분)

```bash
# App Layer: Prometheus/Grafana/cAdvisor 제거
# → Monitoring Layer로 이전

# App Layer에서 제거할 서비스:
# - prometheus
# - grafana
# - (node-exporter, cadvisor는 유지 - 메트릭 제공용)

# Data Layer: 변경 없음
# - Exporter들은 그대로 유지
```

### 6단계: 배포 및 검증 (1시간)

```bash
# Monitoring Layer 시작
cd ~/monitoring-deploy
docker compose up -d

# 헬스 체크
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3000/api/health  # Grafana
curl http://localhost:3100/ready       # Loki
curl http://localhost:3200/ready       # Tempo

# Grafana 접속 및 Datasource 추가
# - Prometheus: http://prometheus:9090
# - Loki: http://loki:3100
# - Tempo: http://tempo:3200
```

---

## 6. 마이그레이션 체크리스트

### 사전 준비
- [ ] Monitoring Layer EC2 인스턴스 생성
- [ ] 보안 그룹 설정
- [ ] Private IP 확인 및 기록
- [ ] Docker/Docker Compose 설치

### Monitoring Layer 구축
- [ ] 배포 디렉토리 생성
- [ ] docker-compose.yml 작성
- [ ] 설정 파일 작성 (prometheus.yml, loki-config.yml 등)
- [ ] 환경 변수 설정 (.env)
- [ ] 서비스 시작 및 헬스 체크

### App Layer 수정
- [ ] Prometheus/Grafana 서비스 제거
- [ ] Node Exporter/cAdvisor 유지 확인
- [ ] docker-compose.yml 업데이트
- [ ] 재배포

### 검증
- [ ] Prometheus에서 모든 타겟 수집 확인 (App, Data, Monitoring)
- [ ] Grafana 대시보드 정상 작동 확인
- [ ] Loki 로그 수집 확인 (App, Data)
- [ ] Alertmanager 알림 테스트
- [ ] Portainer 접속 확인

### 문서화
- [ ] Private IP 기록
- [ ] 접속 정보 기록 (Grafana, Portainer 계정)
- [ ] 보안 그룹 설정 문서화
- [ ] 운영 가이드 작성

---

## 7. 비용 최종 비교

| 옵션 | 구성 | 월 비용 |
|-----|------|--------|
| **현재** | App (t3.small) + Data (t3.small) | **$33.58** |
| **Option A** | App (t3.medium) + Data (t3.small) | **$50.37** |
| **Option A 실제** | App (t3.large) + Data (t3.small) | **$67.16** ❌ |
| **Option B** ⭐ | App (t3.small) + Data (t3.small) + Monitoring (t3.small) | **$50.37** ✅ |

**결론**: Option B가 Option A 실제 비용보다 **$16.79/월 저렴** ($200/년 절감)

---

## 8. 권장 사항

### ✅ Option B (3-Tier) 선택 이유

1. **비용 효율성**: Option A 실제 필요 스펙 대비 25% 저렴
2. **고가용성**: App 장애 시에도 모니터링 시스템 정상 작동
3. **리소스 격리**: 모니터링이 애플리케이션 성능에 영향 없음
4. **확장성**: 각 Layer 독립적 스케일링 가능
5. **운영 안정성**: 장애 상황에서도 메트릭/로그 수집 가능

### 다음 단계

1. **즉시 진행 (오늘)**: Monitoring Layer EC2 생성 및 기본 설정
2. **1주일 내**: Prometheus + Grafana 이전
3. **2주일 내**: Loki + Promtail 구축
4. **3주일 내**: Tempo + Alertmanager 추가
5. **4주일 내**: 전체 통합 및 최적화

---

## 9. 문서 이력

| 버전 | 날짜 | 작성자 | 변경 내용 |
|-----|------|--------|----------|
| 1.0 | 2026-01-23 | Claude | 최초 작성 |
