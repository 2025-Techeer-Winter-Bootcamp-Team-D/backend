# 모니터링 시스템 사용 가이드

이 문서는 프로젝트에서 사용하는 모니터링 도구들의 사용법을 설명합니다.

## 목차

1. [모니터링 아키텍처 개요](#1-모니터링-아키텍처-개요)
2. [접속 정보](#2-접속-정보)
3. [Grafana - 대시보드](#3-grafana---대시보드)
4. [Prometheus - 메트릭 조회](#4-prometheus---메트릭-조회)
5. [Loki - 로그 조회](#5-loki---로그-조회)
6. [Alertmanager - 알림 관리](#6-alertmanager---알림-관리)
7. [Portainer - Docker 관리](#7-portainer---docker-관리)
8. [Celery Flower - 작업 큐 모니터링](#8-celery-flower---작업-큐-모니터링)
9. [문제 해결](#9-문제-해결)

---

## 1. 모니터링 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                      Monitoring Layer                            │
│  ┌───────────┐  ┌───────────┐  ┌────────┐  ┌─────────────────┐  │
│  │ Prometheus│  │  Grafana  │  │  Loki  │  │  Alertmanager   │  │
│  │  :9090    │  │  :3000    │  │ :3100  │  │     :9093       │  │
│  └─────┬─────┘  └─────┬─────┘  └────┬───┘  └────────┬────────┘  │
│        │              │             │               │            │
│        └──────────────┴─────────────┴───────────────┘            │
│                              │                                   │
│  ┌─────────────┐    ┌───────┴───────┐    ┌─────────────┐        │
│  │ Promtail   │    │  Portainer    │    │Node Exporter│        │
│  │  (App)     │    │    :9000      │    │   :9100     │        │
│  └─────────────┘    └───────────────┘    └─────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        App Layer                                 │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ Django │ │ Celery │ │ Flower │ │ cAdvisor │ │Node Exporter│  │
│  │ :8000  │ │ Worker │ │ :5555  │ │  :8081   │ │   :9100     │  │
│  └────────┘ └────────┘ └────────┘ └──────────┘ └─────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Data Layer                                │
│  ┌────────────┐ ┌───────┐ ┌────────────┐ ┌─────────────┐        │
│  │ TimescaleDB│ │ Redis │ │ OpenSearch │ │Node Exporter│        │
│  │   :5432    │ │ :6379 │ │   :9200    │ │   :9100     │        │
│  └────────────┘ └───────┘ └────────────┘ └─────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### 수집되는 메트릭

| Exporter | 수집 대상 | 주요 메트릭 |
|----------|----------|-------------|
| Node Exporter | 서버 (CPU, 메모리, 디스크) | `node_cpu_seconds_total`, `node_memory_*` |
| cAdvisor | Docker 컨테이너 | `container_cpu_usage_seconds_total`, `container_memory_usage_bytes` |
| Django Prometheus | Django 애플리케이션 | `django_http_requests_total`, `django_db_query_duration_seconds` |
| Redis Exporter | Redis | `redis_connected_clients`, `redis_memory_used_bytes` |
| PostgreSQL Exporter | PostgreSQL/TimescaleDB | `pg_stat_activity_count`, `pg_database_size_bytes` |
| OpenSearch Exporter | OpenSearch | `opensearch_cluster_health_status` |

---

## 2. 접속 정보

### 외부 접속 (Nginx 리버스 프록시 경유)

| 서비스 | URL | 비고 |
|--------|-----|------|
| Grafana | `http://quasa.info/grafana/` | 대시보드 |
| Prometheus | `http://quasa.info/prometheus/` | 메트릭 조회 |
| Alertmanager | `http://quasa.info/alertmanager/` | 알림 관리 |
| Portainer | `http://quasa.info/portainer/` | Docker 관리 |
| Celery Flower | `http://quasa.info/celery-flower/` | Celery 모니터링 |
| RabbitMQ | `http://quasa.info/rabbitmq/` | 메시지 큐 관리 |

### 직접 접속 (내부 네트워크)

| 서비스 | 포트 | 서버 |
|--------|------|------|
| Grafana | 3000 | Monitoring |
| Prometheus | 9090 | Monitoring |
| Loki | 3100 | Monitoring |
| Alertmanager | 9093 | Monitoring |
| Portainer | 9000 | Monitoring |
| Node Exporter | 9100 | All Layers |
| cAdvisor | 8081 | App |
| Flower | 5555 | App |

---

## 3. Grafana - 대시보드

### 3.1. 접속 및 로그인

1. `http://quasa.info/grafana/` 접속
2. 기본 계정: `admin` / `<GRAFANA_ADMIN_PASSWORD>`

### 3.2. 제공되는 대시보드

| 대시보드 | 설명 | 주요 지표 |
|----------|------|----------|
| **Django Prometheus** | Django 애플리케이션 모니터링 | 요청 수, 응답 시간, 에러율 |
| **Docker System** | Docker 컨테이너 모니터링 | 컨테이너 CPU/메모리, 네트워크 I/O |
| **Node Exporter** | 서버 리소스 모니터링 | CPU, 메모리, 디스크, 네트워크 |
| **PostgreSQL** | 데이터베이스 모니터링 | 연결 수, 쿼리 성능, 테이블 크기 |
| **Redis** | Redis 캐시 모니터링 | 메모리, 연결 수, 명령어 통계 |

### 3.3. 대시보드 사용법

#### 시간 범위 조정
- 우측 상단의 시간 선택기 클릭
- 프리셋 선택 (Last 15 minutes, Last 1 hour 등)
- 또는 Custom range로 직접 지정

#### 변수 필터링
- 대시보드 상단의 드롭다운 메뉴 사용
- `server`: 특정 서버 선택
- `container`: 특정 컨테이너 선택
- `interval`: 데이터 집계 간격

#### 패널 확대
- 패널 제목 클릭 → **View** 선택
- 또는 패널에서 `v` 키 누르기

#### 데이터 탐색
- 패널 제목 클릭 → **Explore** 선택
- 쿼리 수정하여 상세 분석 가능

### 3.4. 알림 설정

1. 대시보드에서 알림을 설정할 패널 선택
2. **Edit** → **Alert** 탭
3. 조건 설정 (예: CPU > 80%)
4. 알림 채널 선택 (Slack, Email 등)
5. **Save**

---

## 4. Prometheus - 메트릭 조회

### 4.1. 접속

`http://quasa.info/prometheus/` 접속

### 4.2. PromQL 기본 쿼리

#### 즉시 벡터 (현재 값)
```promql
# 모든 타겟의 상태
up

# Django 요청 수
django_http_requests_total

# 특정 레이블 필터링
node_cpu_seconds_total{mode="idle"}
```

#### 범위 벡터 (시간 범위)
```promql
# 최근 5분간의 데이터
node_cpu_seconds_total[5m]

# 최근 1시간간의 요청 수
django_http_requests_total[1h]
```

#### 집계 함수
```promql
# CPU 사용률 (%)
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 메모리 사용률 (%)
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# 초당 요청 수 (RPS)
rate(django_http_requests_total[5m])

# 컨테이너별 메모리 사용량
container_memory_usage_bytes{name!=""}
```

### 4.3. 자주 사용하는 쿼리

#### 서버 리소스
```promql
# CPU 사용률 (레이어별)
100 - (avg by(layer) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 메모리 사용량 (GB)
node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes

# 디스크 사용률
(1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100
```

#### Django 애플리케이션
```promql
# HTTP 요청 수 (상태 코드별)
sum by(status) (rate(django_http_requests_total[5m]))

# 평균 응답 시간
rate(django_http_request_duration_seconds_sum[5m]) / rate(django_http_request_duration_seconds_count[5m])

# 에러율 (5xx)
sum(rate(django_http_requests_total{status=~"5.."}[5m])) / sum(rate(django_http_requests_total[5m])) * 100
```

#### Docker 컨테이너
```promql
# 컨테이너 CPU 사용률
rate(container_cpu_usage_seconds_total{name!=""}[5m]) * 100

# 컨테이너 메모리 사용량 (MB)
container_memory_usage_bytes{name!=""} / 1024 / 1024

# 컨테이너 네트워크 수신 (bytes/sec)
rate(container_network_receive_bytes_total{name!=""}[5m])
```

### 4.4. 타겟 상태 확인

1. **Status** → **Targets** 메뉴
2. 각 타겟의 상태 확인 (UP/DOWN)
3. 마지막 스크래핑 시간 및 에러 확인

---

## 5. Loki - 로그 조회

### 5.1. Grafana Explore에서 조회

1. Grafana 좌측 메뉴 → **Explore** (나침반 아이콘)
2. 상단 데이터소스에서 **Loki** 선택

### 5.2. LogQL 기본 쿼리

#### 로그 스트림 선택
```logql
# Django 컨테이너 로그
{container_name="django"}

# 특정 레이어의 모든 로그
{layer="app"}

# 여러 조건 조합
{container_name="django", layer="app"}
```

#### 로그 필터링
```logql
# 에러 로그만
{container_name="django"} |= "ERROR"

# 특정 문자열 제외
{container_name="django"} != "health"

# 정규식 필터
{container_name="django"} |~ "status=[45][0-9]{2}"
```

#### 로그 파싱
```logql
# JSON 로그 파싱
{container_name="django"} | json

# 특정 필드 추출
{container_name="django"} | json | level="error"

# 로그 라인 포맷팅
{container_name="django"} | json | line_format "{{.timestamp}} [{{.level}}] {{.message}}"
```

### 5.3. 자주 사용하는 쿼리

```logql
# Django 에러 로그
{container_name="django"} |= "ERROR" | json

# Celery 작업 실패 로그
{container_name="celery-worker"} |= "Task" |= "raised"

# 느린 쿼리 로그 (1초 이상)
{container_name="django"} |= "duration" | json | duration > 1s

# 특정 시간대 로그
{container_name="django"} |= "ERROR" | json | __timestamp__ >= "2024-01-01T00:00:00Z"
```

### 5.4. 로그 집계

```logql
# 시간당 에러 로그 수
count_over_time({container_name="django"} |= "ERROR"[1h])

# 컨테이너별 로그 수
sum by(container_name) (count_over_time({layer="app"}[5m]))
```

---

## 6. Alertmanager - 알림 관리

### 6.1. 접속

`http://quasa.info/alertmanager/` 접속

### 6.2. 주요 기능

#### Alerts 탭
- 현재 활성화된 알림 목록
- 알림 상태: `firing` (발생 중), `resolved` (해결됨)

#### Silences 탭
- 알림 일시 중지 관리
- 유지보수 시 알림 비활성화에 사용

### 6.3. 알림 일시 중지 (Silence)

1. **Silences** 탭 → **New Silence**
2. **Matchers** 설정:
   - `alertname = HighCPUUsage` (특정 알림)
   - `instance = 172.31.36.109:9100` (특정 인스턴스)
3. **Duration** 설정 (예: 2h)
4. **Comment** 입력 (예: "서버 유지보수 중")
5. **Create**

### 6.4. 설정된 알림 규칙

| 알림 이름 | 조건 | 심각도 |
|----------|------|--------|
| HighCPUUsage | CPU > 80% (5분) | warning |
| HighMemoryUsage | Memory > 85% | warning |
| DiskSpaceLow | Disk > 80% | warning |
| ServiceDown | Target down (1분) | critical |
| HighErrorRate | 5xx > 5% | critical |

---

## 7. Portainer - Docker 관리

### 7.1. 접속

`http://quasa.info/portainer/` 접속

### 7.2. 주요 기능

#### Containers
- 실행 중인 컨테이너 목록
- 시작/중지/재시작/삭제
- 로그 조회
- 컨테이너 내부 쉘 접속

#### Images
- Docker 이미지 관리
- 미사용 이미지 삭제

#### Networks
- Docker 네트워크 관리
- 네트워크 연결 상태 확인

#### Volumes
- Docker 볼륨 관리
- 볼륨 크기 및 사용 현황

### 7.3. 자주 사용하는 작업

#### 컨테이너 로그 확인
1. **Containers** → 컨테이너 선택
2. **Logs** 클릭
3. 실시간 로그 스트리밍 또는 과거 로그 조회

#### 컨테이너 재시작
1. **Containers** → 컨테이너 체크박스 선택
2. 상단 **Restart** 클릭

#### 컨테이너 쉘 접속
1. **Containers** → 컨테이너 선택
2. **Console** 클릭
3. `/bin/sh` 또는 `/bin/bash` 선택
4. **Connect**

#### 리소스 사용량 확인
1. **Containers** → 컨테이너 선택
2. **Stats** 클릭
3. CPU, 메모리, 네트워크 I/O 실시간 확인

---

## 8. Celery Flower - 작업 큐 모니터링

### 8.1. 접속

`http://quasa.info/celery-flower/` 접속

### 8.2. 대시보드 탭

#### Dashboard
- 전체 작업 통계
- 활성 워커 수
- 처리된 작업 수

#### Workers
- 워커 목록 및 상태
- 워커별 처리량
- 워커 풀 정보

#### Tasks
- 작업 목록 (성공/실패/대기)
- 작업 상세 정보
- 작업 실행 시간

#### Broker
- RabbitMQ 큐 상태
- 대기 중인 메시지 수

### 8.3. 작업 모니터링

#### 실패한 작업 확인
1. **Tasks** 탭
2. **State** 필터에서 `FAILURE` 선택
3. 작업 클릭하여 에러 상세 확인

#### 작업 재시도
1. 실패한 작업 선택
2. **Retry** 버튼 클릭

#### 워커 상태 확인
1. **Workers** 탭
2. 각 워커의 `Status` 확인 (Online/Offline)
3. `Active Tasks`로 현재 처리 중인 작업 확인

### 8.4. 주요 메트릭

| 메트릭 | 설명 | 정상 범위 |
|--------|------|----------|
| Active Tasks | 현재 실행 중인 작업 | 워커 수 이하 |
| Processed | 처리 완료된 작업 수 | 증가 추세 |
| Failed | 실패한 작업 수 | 최소화 |
| Pending | 대기 중인 작업 | 급증 시 주의 |

---

## 9. 문제 해결

### 9.1. Grafana 대시보드 데이터 없음

```bash
# 1. Prometheus 연결 확인
docker exec grafana wget -qO- "http://prometheus:9090/prometheus/api/v1/query?query=up"

# 2. 데이터소스 설정 확인
docker exec grafana cat /etc/grafana/provisioning/datasources/datasources.yml

# 3. Grafana 재시작
docker restart grafana
```

### 9.2. Prometheus 타겟 DOWN

```bash
# 1. 타겟 서비스 상태 확인
curl http://<TARGET_IP>:<PORT>/metrics

# 2. 네트워크 연결 확인
docker exec prometheus wget -qO- http://<TARGET_IP>:<PORT>/metrics

# 3. 방화벽 확인 (EC2 Security Group)
```

### 9.3. 로그가 Loki에 수집되지 않음

```bash
# 1. Promtail 상태 확인
docker logs promtail-app --tail 50

# 2. Loki 연결 확인
docker exec promtail-app wget -qO- http://loki:3100/ready

# 3. Docker 소켓 권한 확인
ls -la /var/run/docker.sock
```

### 9.4. 알림이 오지 않음

```bash
# 1. Alertmanager 상태 확인
curl http://localhost:9093/-/healthy

# 2. 알림 규칙 확인
curl http://localhost:9090/prometheus/api/v1/rules

# 3. Silence 상태 확인 (알림 비활성화 여부)
# Alertmanager UI → Silences 탭
```

### 9.5. 컨테이너 접속 불가 (Portainer)

```bash
# 1. Docker 소켓 마운트 확인
docker inspect portainer | grep -A5 "Mounts"

# 2. Portainer 재시작
docker restart portainer

# 3. Docker 데몬 상태 확인
sudo systemctl status docker
```

---

## 10. 모니터링 체크리스트

### 일일 점검 항목

- [ ] 모든 타겟 UP 상태 확인 (Prometheus Targets)
- [ ] 활성 알림 확인 (Alertmanager)
- [ ] 디스크 사용량 확인 (80% 미만)
- [ ] 실패한 Celery 작업 확인 (Flower)

### 주간 점검 항목

- [ ] 로그 용량 및 보존 기간 확인
- [ ] 미사용 Docker 이미지 정리
- [ ] 대시보드 쿼리 성능 확인
- [ ] 알림 규칙 적절성 검토

### 장애 대응 순서

1. **Grafana**에서 이상 징후 확인
2. **Prometheus**에서 상세 메트릭 분석
3. **Loki**에서 관련 로그 조회
4. **Portainer**에서 컨테이너 상태 확인 및 조치
5. 필요시 **Alertmanager**에서 Silence 설정
