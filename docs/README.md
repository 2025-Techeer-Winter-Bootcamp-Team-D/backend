# 문서 디렉토리

프로젝트 문서 모음입니다.

## 디렉토리 구조

```text
docs/
├── README.md                           # 이 파일
│
├── # 핵심 문서
├── PRD.md                              # 제품 요구사항 문서
├── SYSTEM_ARCHITECTURE.md              # 시스템 아키텍처
├── TECH_STACK.md                       # 기술 스택 상세
├── API-REFERENCE.md                    # API 레퍼런스
│
├── # 아키텍처 문서
├── ARCHITECTURE-EVOLUTION.md           # 아키텍처 진화 과정
├── DATA-PROCESSING-ARCHITECTURE.md     # 데이터 처리 아키텍처
├── STOCK-TICK-PIPELINE.md              # 주가 데이터 파이프라인
├── RABBITMQ-STREAMING.md               # RabbitMQ 스트리밍 구조
│
├── # API 문서
├── REALTIME-STOCK-WEBSOCKET-API.md     # 실시간 주가 WebSocket API
│
├── # 배포 및 운영
├── DEPLOYMENT.md                       # 배포 가이드
├── MONITORING-DEPLOYMENT-GUIDE.md      # 모니터링 배포 가이드
│
├── # 성능 분석
├── LOAD_TEST_ANALYSIS.md               # 부하 테스트 분석 보고서
├── TECHNICAL-HIGHLIGHTS.md             # 기술적 하이라이트
│
├── # 데모 시나리오
├── QUASA-DEMO-SCENARIO.md              # 데모 시나리오
├── QUASA-USER-SCENARIO.md              # 사용자 시나리오
│
├── guides/                             # 개발 가이드
│   ├── DJANGO-APP-TUTORIAL.md          # Django 앱 생성 튜토리얼
│   ├── CELERY-TASK-PIPELINE.md         # Celery Canvas 워크플로우
│   ├── DEBUGGING-CELERY.md             # Celery 디버깅 가이드
│   ├── OPENSEARCH-SERVICE.md           # OpenSearch 서비스 가이드
│   ├── MONITORING_QUICKSTART.md        # 모니터링 퀵스타트
│   ├── MONITORING-GUIDE.md             # 모니터링 상세 가이드
│   ├── HTTPS-DOMAIN-SETUP.md           # HTTPS/도메인 설정 가이드
│   ├── DATA_RETENTION_STRATEGY.md      # TimescaleDB 데이터 보관 전략
│   ├── FINANCIAL_DATA_MAPPING.md       # 재무 데이터 매핑 가이드
│   └── INDUSTRY-MAPPING-ANALYSIS.md    # 기업-산업 매핑 분석
│
└── plans/                              # 구현 계획 문서
    ├── REFACTORING-PLAN.md             # 리팩토링 계획
    ├── RABBITMQ_LOAD_TEST.md           # RabbitMQ 부하 테스트 계획
    ├── CICD-OPTIMIZATION-ANALYSIS.md   # CI/CD 최적화 분석
    ├── USER-COMPANY-VISIT-HISTORY.md   # 기업 방문 기록 기능
    ├── report-processing-enhancement.md # 보고서 처리 강화 (보류)
    └── archive/                        # 완료된 계획서 보관
```

## 문서 설명

### 핵심 문서

| 문서 | 설명 |
|------|------|
| [PRD.md](./PRD.md) | 제품 요구사항 정의서 (Product Requirements Document) |
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | 시스템 아키텍처 및 3-Tier 배포 구조 |
| [TECH_STACK.md](./TECH_STACK.md) | 기술 스택 상세 설명 |
| [API-REFERENCE.md](./API-REFERENCE.md) | API 엔드포인트, Management Commands, Celery Tasks 레퍼런스 |

### 아키텍처 문서

| 문서 | 설명 |
|------|------|
| [ARCHITECTURE-EVOLUTION.md](./ARCHITECTURE-EVOLUTION.md) | Redis Pub/Sub → RabbitMQ 진화 과정 |
| [DATA-PROCESSING-ARCHITECTURE.md](./DATA-PROCESSING-ARCHITECTURE.md) | 뉴스/보고서 AI 분석 파이프라인 |
| [STOCK-TICK-PIPELINE.md](./STOCK-TICK-PIPELINE.md) | 주가 데이터 실시간 저장 파이프라인 (Publisher Confirm, 수동 ACK/NACK) |
| [RABBITMQ-STREAMING.md](./RABBITMQ-STREAMING.md) | RabbitMQ 메시지 스트리밍 구조 |

### API 문서

| 문서 | 설명 |
|------|------|
| [REALTIME-STOCK-WEBSOCKET-API.md](./REALTIME-STOCK-WEBSOCKET-API.md) | 실시간 주가 WebSocket 연결 및 사용법 |
| [API-REFERENCE.md](./API-REFERENCE.md) | REST API 엔드포인트 전체 목록 |

### 배포 및 운영

| 문서 | 설명 |
|------|------|
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Docker Compose 배포 가이드 |
| [MONITORING-DEPLOYMENT-GUIDE.md](./MONITORING-DEPLOYMENT-GUIDE.md) | Prometheus/Grafana/Loki 모니터링 배포 |

### 성능 분석

| 문서 | 설명 |
|------|------|
| [LOAD_TEST_ANALYSIS.md](./LOAD_TEST_ANALYSIS.md) | RabbitMQ 부하 테스트 분석 (10,000/초 달성 가이드 포함) |
| [TECHNICAL-HIGHLIGHTS.md](./TECHNICAL-HIGHLIGHTS.md) | 프로젝트 기술적 하이라이트 |

### 데모 시나리오

| 문서 | 설명 |
|------|------|
| [QUASA-DEMO-SCENARIO.md](./QUASA-DEMO-SCENARIO.md) | 시연용 데모 시나리오 |
| [QUASA-USER-SCENARIO.md](./QUASA-USER-SCENARIO.md) | 사용자 관점 시나리오 |

### 개발 가이드 (`guides/`)

| 문서 | 설명 |
|------|------|
| [DJANGO-APP-TUTORIAL.md](./guides/DJANGO-APP-TUTORIAL.md) | Django 앱 생성 및 REST API 구현 단계별 가이드 |
| [CELERY-TASK-PIPELINE.md](./guides/CELERY-TASK-PIPELINE.md) | Celery Canvas를 활용한 분산 태스크 설계 |
| [DEBUGGING-CELERY.md](./guides/DEBUGGING-CELERY.md) | Celery Worker, Beat, Flower 디버깅 방법 |
| [OPENSEARCH-SERVICE.md](./guides/OPENSEARCH-SERVICE.md) | OpenSearch 벡터 검색 서비스 사용법 |
| [MONITORING_QUICKSTART.md](./guides/MONITORING_QUICKSTART.md) | Prometheus + Grafana 모니터링 빠른 시작 |
| [MONITORING-GUIDE.md](./guides/MONITORING-GUIDE.md) | 모니터링 상세 설정 가이드 |
| [HTTPS-DOMAIN-SETUP.md](./guides/HTTPS-DOMAIN-SETUP.md) | Let's Encrypt SSL 인증서 및 도메인 설정 |
| [DATA_RETENTION_STRATEGY.md](./guides/DATA_RETENTION_STRATEGY.md) | TimescaleDB 시계열 데이터 보관 정책 |
| [FINANCIAL_DATA_MAPPING.md](./guides/FINANCIAL_DATA_MAPPING.md) | DART/KIS API 재무 데이터 매핑 방법 |
| [INDUSTRY-MAPPING-ANALYSIS.md](./guides/INDUSTRY-MAPPING-ANALYSIS.md) | 기업-산업 업종코드 매핑 구조 분석 |

### 계획 문서 (`plans/`)

진행 중인 구현 계획만 포함합니다. 완료된 계획은 `plans/archive/`에 보관됩니다.

| 문서 | 상태 | 설명 |
|------|------|------|
| [REFACTORING-PLAN.md](./plans/REFACTORING-PLAN.md) | 진행 중 | 코드 리팩토링 계획 |
| [RABBITMQ_LOAD_TEST.md](./plans/RABBITMQ_LOAD_TEST.md) | 완료 | RabbitMQ 부하 테스트 시나리오 |
| [CICD-OPTIMIZATION-ANALYSIS.md](./plans/CICD-OPTIMIZATION-ANALYSIS.md) | 완료 | CI/CD 파이프라인 최적화 분석 |
| [USER-COMPANY-VISIT-HISTORY.md](./plans/USER-COMPANY-VISIT-HISTORY.md) | 완료 | 기업 방문 기록 기능 |
| [report-processing-enhancement.md](./plans/report-processing-enhancement.md) | 보류 | 보고서 처리 강화 계획 |

## 문서 작성 규칙

1. **언어**: 한국어 (기술 용어는 영어 병기 가능)
2. **파일명**: 대문자, 하이픈 사용 (예: `API-REFERENCE.md`)
3. **위치**:
   - 핵심 문서 → `docs/` 루트
   - 개발 가이드 → `docs/guides/`
   - 구현 계획 → `docs/plans/`
   - 완료된 계획 → `docs/plans/archive/`
