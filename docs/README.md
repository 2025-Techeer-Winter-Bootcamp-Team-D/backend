# 문서 디렉토리

프로젝트 문서 모음입니다.

## 디렉토리 구조

```
docs/
├── README.md                       # 이 파일
├── PRD.md                          # 제품 요구사항 문서
├── SYSTEM_ARCHITECTURE.md          # 시스템 아키텍처
├── API-REFERENCE.md                # API 레퍼런스
├── REALTIME-STOCK-WEBSOCKET-API.md # 실시간 주가 WebSocket API
├── MONITORING-DEPLOYMENT-GUIDE.md  # 모니터링 배포 가이드
│
├── guides/                         # 개발 가이드
│   ├── DJANGO-APP-TUTORIAL.md      # Django 앱 생성 튜토리얼
│   ├── CELERY-TASK-PIPELINE.md     # Celery Canvas 워크플로우
│   ├── DEBUGGING-CELERY.md         # Celery 디버깅 가이드
│   ├── OPENSEARCH-SERVICE.md       # OpenSearch 서비스 가이드
│   ├── MONITORING_QUICKSTART.md    # 모니터링 퀵스타트
│   ├── DATA_RETENTION_STRATEGY.md  # TimescaleDB 데이터 보관 전략
│   ├── FINANCIAL_DATA_MAPPING.md   # 재무 데이터 매핑 가이드
│   └── INDUSTRY-MAPPING-ANALYSIS.md# 기업-산업 매핑 분석
│
└── plans/                          # 구현 계획 문서
    ├── REFACTORING_PLAN.md         # 리팩토링 계획 (진행 중)
    ├── report-processing-enhancement.md # 보고서 처리 강화 (보류)
    └── archive/                    # 완료된 계획서 보관
```

## 문서 설명

### 핵심 문서

| 문서 | 설명 |
|------|------|
| [PRD.md](./PRD.md) | 제품 요구사항 정의서 (Product Requirements Document) |
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | 시스템 아키텍처 및 기술 스택 상세 |
| [API-REFERENCE.md](./API-REFERENCE.md) | API 엔드포인트, Management Commands, Celery Tasks 레퍼런스 |

### API 문서

| 문서 | 설명 |
|------|------|
| [REALTIME-STOCK-WEBSOCKET-API.md](./REALTIME-STOCK-WEBSOCKET-API.md) | 실시간 주가 WebSocket 연결 및 사용법 |
| [API-REFERENCE.md](./API-REFERENCE.md) | REST API 엔드포인트 전체 목록 |

### 배포 및 운영

| 문서 | 설명 |
|------|------|
| [MONITORING-DEPLOYMENT-GUIDE.md](./MONITORING-DEPLOYMENT-GUIDE.md) | 3-Tier 모니터링 레이어 배포 가이드 |

### 개발 가이드 (`guides/`)

| 문서 | 설명 |
|------|------|
| [DJANGO-APP-TUTORIAL.md](./guides/DJANGO-APP-TUTORIAL.md) | Django 앱 생성 및 REST API 구현 단계별 가이드 |
| [CELERY-TASK-PIPELINE.md](./guides/CELERY-TASK-PIPELINE.md) | Celery Canvas를 활용한 분산 태스크 설계 |
| [DEBUGGING-CELERY.md](./guides/DEBUGGING-CELERY.md) | Celery Worker, Beat, Flower 디버깅 방법 |
| [OPENSEARCH-SERVICE.md](./guides/OPENSEARCH-SERVICE.md) | OpenSearch 벡터 검색 서비스 사용법 |
| [MONITORING_QUICKSTART.md](./guides/MONITORING_QUICKSTART.md) | Prometheus + Grafana 모니터링 빠른 시작 |
| [DATA_RETENTION_STRATEGY.md](./guides/DATA_RETENTION_STRATEGY.md) | TimescaleDB 시계열 데이터 보관 정책 |
| [FINANCIAL_DATA_MAPPING.md](./guides/FINANCIAL_DATA_MAPPING.md) | DART/KIS API 재무 데이터 매핑 방법 |
| [INDUSTRY-MAPPING-ANALYSIS.md](./guides/INDUSTRY-MAPPING-ANALYSIS.md) | 기업-산업 업종코드 매핑 구조 분석 |

### 계획 문서 (`plans/`)

진행 중인 구현 계획만 포함합니다. 완료된 계획은 `plans/archive/`에 보관됩니다.

## 문서 작성 규칙

1. **언어**: 한국어 (기술 용어는 영어 병기 가능)
2. **파일명**: 대문자, 하이픈 사용 (예: `API-REFERENCE.md`)
3. **위치**:
   - 핵심 문서 → `docs/` 루트
   - 개발 가이드 → `docs/guides/`
   - 구현 계획 → `docs/plans/`
   - 완료된 계획 → `docs/plans/archive/`
