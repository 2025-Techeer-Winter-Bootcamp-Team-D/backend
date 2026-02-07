# 기술 스택

## Backend Framework

| 기술 | 버전 | 설명 |
|------|------|------|
| **Django** | 6.0 | Python 기반 웹 프레임워크. MTV 패턴, ORM, 관리자 패널 제공 |
| **Django REST Framework** | - | Django용 REST API 구축 라이브러리. 직렬화, 인증, 뷰셋 제공 |
| **Django Channels** | - | Django에서 WebSocket, 비동기 처리를 지원하는 확장 |
| **drf-spectacular** | - | OpenAPI 3.0 스키마 자동 생성. Swagger UI 문서화 |

## Database

| 기술 | 버전 | 설명 |
|------|------|------|
| **TimescaleDB** | PostgreSQL 16 기반 | 시계열 데이터에 최적화된 PostgreSQL 확장. Hypertable, Continuous Aggregate 지원 |
| **Redis** | 7 | 인메모리 키-값 저장소. 캐시, 세션, Pub/Sub 메시징에 사용 |
| **OpenSearch** | - | Elasticsearch 포크. 전문 검색, 벡터 검색(HNSW), 로그 분석 지원 |

## Message Queue & Task

| 기술 | 버전 | 설명 |
|------|------|------|
| **RabbitMQ** | 3.13 | AMQP 기반 메시지 브로커. Celery 작업 큐의 브로커로 사용 |
| **Celery** | 5.4+ | Python 분산 작업 큐. 비동기 태스크, 스케줄링(Beat) 지원 |
| **Flower** | - | Celery 모니터링 웹 대시보드. 실시간 작업 상태 확인 |

## Monitoring

| 기술 | 설명 |
|------|------|
| **Prometheus** | 메트릭 수집 및 시계열 DB. Pull 방식으로 타겟에서 메트릭 수집 |
| **Grafana** | 메트릭 시각화 대시보드. Prometheus, TimescaleDB 등 다양한 데이터소스 지원 |
| **Node Exporter** | 서버 하드웨어/OS 메트릭(CPU, 메모리, 디스크) 수집기 |
| **cAdvisor** | Docker 컨테이너 리소스 사용량 모니터링 |

## External API

| API | 용도 |
|-----|------|
| **KIS WebSocket API** | 한국투자증권 실시간 주가 체결 데이터 수신 |
| **DART OpenAPI** | 금융감독원 전자공시시스템. 기업 정보, 재무제표, 공시 보고서 |
| **Naver News API** | 네이버 뉴스 검색 |
| **Gemini API** | Google AI. 텍스트 정제/요약, 벡터 임베딩 생성 |

## Infrastructure

| 기술 | 설명 |
|------|------|
| **Docker** | 컨테이너 기반 애플리케이션 패키징 및 배포 |
| **Docker Compose** | 멀티 컨테이너 애플리케이션 정의 및 실행 |
| **Nginx** | 리버스 프록시, SSL 종료, 정적 파일 서빙 |
| **Let's Encrypt** | 무료 SSL/TLS 인증서 발급 (Certbot) |

## Development Tools

| 도구 | 설명 |
|------|------|
| **Ruff** | Python 린터 & 포매터. 빠른 속도, Flake8/Black 대체 |
| **Git** | 버전 관리 시스템 |
| **GitHub Actions** | CI/CD 파이프라인 자동화 |
