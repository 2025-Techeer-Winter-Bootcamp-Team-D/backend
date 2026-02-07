# 배포 계획: 2-Tier EC2 아키텍처 (Project Tailored)

## 1. 개요 및 목표
현재 프로젝트(**Techeer Winter Backend**)의 구체적인 서비스(TimscaleDB, Redis, OpenSearch, Django Channels, Celery 등)를 기반으로 **CI/CD 친화적인 2-Tier 아키텍처**를 구성합니다.

- **핵심 철학**:
    1.  **계층 분리**: `Data Layer`(상태 저장)와 `App Layer`(빈번한 배포)의 물리적/논리적 분리.
    2.  **설정 독립성**: 각 계층은 **독립적인 `.env`** 파일을 가집니다.
    3.  **프로덕션 최적화**: Mock Server 제외, 실제 KIS 연동 준비, Nginx 도입.

## 2. 디렉토리 구조

프로젝트 루트에 `deploy` 폴더를 생성하고, 계층별 구성을 명확히 합니다.

```text

project_root/
├── deploy/
│   ├── app/                      # [EC2 A: App Layer]
│   │   ├── .env                  # 앱 노드 환경변수 (DB 접속 정보, Secret Key 등)
│   │   ├── docker-compose.yml    # App, Celery, Workers, Nginx, Monitoring
│   │   └── nginx/                # Nginx 설정
│   │       ├── Dockerfile
│   │       └── conf.d/
│   │           └── default.conf
│   │
│   ├── data/                     # [EC2 B: Data Layer]
│   │   ├── .env                  # 데이터 노드 환경변수 (DB/Redis/OpenSearch 암호 등)
│   │   └── docker-compose.yml    # DB, Redis, OpenSearch, Exporters
│   │
│   └── env/                      # 환경 변수 템플릿
│       ├── .env.app.example      # 앱용 템플릿
│       └── .env.data.example     # 데이터용 템플릿
│
├── ...
```

## 3. 계층별 서비스 및 설정 상세

### 3.1. 데이터 계층 (Data Layer) - EC2 Instance B
*안정적인 인프라스트럭처. CI/CD 배포 대상에서 제외(수동/별도 관리).*

*   **포트 개방 (Inbound)**: App Instance의 Private IP에 대해서만 허용.
  *   `5432` (Postgres), `6379` (Redis), `9200` (OpenSearch), `9100` (Node Exp), `9187` (Pg Exp), `9121` (Redis Exp).
*   **환경 변수 (`deploy/data/.env`)**:
  *   `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
  *   `OPENSEARCH_INITIAL_ADMIN_PASSWORD`
  *   `TZ=Asia/Seoul`
*   **docker-compose.yml 구성**:
  *   `db`: `timescale/timescaledb:latest-pg16`
  *   `redis`: `redis:7-alpine`
  *   `opensearch`: `opensearchproject/opensearch` (단일 노드 모드)
  *   `postgres-exporter`, `redis-exporter`, `node-exporter`

### 3.2. 앱 계층 (App Layer) - EC2 Instance A
*비즈니스 로직. CI/CD 파이프라인의 주요 배포 대상.*

*   **포트 개방 (Inbound)**: `80`, `443` (Public), `22` (Management).
*   **환경 변수 (`deploy/app/.env`)**:
    *   **접속 정보**: `DB_HOST`, `REDIS_HOST`, `OPENSEARCH_HOST` (Data Layer의 Private IP로 설정).
    *   **앱 설정**: `DJANGO_SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`.
    *   **KIS 설정**: `KIS_APPKEY`, `KIS_APPSECRET`, `KIS_USE_TEST_MODE=false` (프로덕션 모드).
*   **docker-compose.yml 구성**:
    *   **Gateway**: `nginx` (80->443 SSL, Static Files, Gunicorn/Daphne Proxy).
    *   **Backend**: `app` (Django). CI/CD에서는 `image: my-repo/backend:tag` 사용.
    *   **Async**: `tick-broadcaster` (Daphne/Websockets).
    *   **Workers Data**: `celery-worker`, `celery-beat`, `flower`.
    *   **Stream Workers**: `kis-publisher` (Real Mode), `tick-writer`.
    *   **Monitoring**: `prometheus` (Data Node의 Exporter까지 수집), `grafana`, `node-exporter`, `cadvisor`.

## 4. 단계별 구현 액션 플랜

### 1단계: Data Layer 구성 (`deploy/data/`)
1.  **`docker-compose.yml`**: 기존 파일에서 `db`, `redis`, `opensearch`, `*-exporter` 추출.
    *   볼륨 경로는 호스트 폴더 바인딩(`- ./data/postgres:/var/lib/postgresql/data`) 권장.
2.  **`.env`**: DB 및 인프라 구동에 필요한 최소 로컬 변수 정의.

### 2단계: App Layer 구성 (`deploy/app/`)
1.  **`docker-compose.yml`**: `app`, `celery*`, `workers`, `monitoring` 서비스 정의.
    *   `environment` 섹션 수정: `db:5432` 대신 `${DB_HOST}:5432` 형태로 변경하여 외부 주입 가능하게 함.
    *   `kis-mock-server` **제거**.
    *   `kis-publisher`가 `kis-mock-server` 대신 실제 KIS 또는 테스트 서버를 바라보도록 환경변수 조정.
2.  **`nginx/`**:
    *   `nginx.conf`: `/api/`는 `app:8000`, `/ws/`는 `tick-broadcaster` 등 적절한 라우팅 설정.

### 3단계: CI/CD 연동 준비
*   `deploy/app/docker-compose.yml`에서 이미지를 `local build`와 `registry image` 중 선택 가능하도록 주석 가이드 추가.

## 5. 승인 요청
현재 프로젝트의 모든 서비스 컴포넌트를 빠짐없이 포함하되, 프로덕션 환경에 맞게 재배치했습니다.
이 상세 계획대로 구현을 진행하시겠습니까?
