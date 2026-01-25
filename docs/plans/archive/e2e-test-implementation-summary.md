# E2E 테스트 API 구현 완료 보고서

## 개요

End-to-End 테스트 API를 성공적으로 구현했습니다. 이 API는 전체 시스템의 인프라, 외부 API 연결, 데이터 정합성, 보고서 처리 파이프라인을 검증합니다.

## 구현 내용

### 1. 파일 구조

```
companies/
├── tests/
│   ├── __init__.py
│   ├── e2e/
│   │   ├── __init__.py
│   │   ├── test_phase1_infrastructure.py    # Phase 1: 인프라 검증
│   │   ├── test_phase2_external_api.py      # Phase 2: 외부 API 검증
│   │   ├── test_phase3_data_integrity.py    # Phase 3: 데이터 정합성 검증
│   │   └── test_phase4_report_pipeline.py   # Phase 4: 보고서 처리 파이프라인 검증
│   └── services/
│       ├── __init__.py
│       └── e2e_runner.py                     # E2E Runner 서비스
├── views.py                                  # API 엔드포인트 추가
└── urls.py                                   # URL 라우팅 추가

test_e2e.sh                                   # 테스트 실행 스크립트
```

### 2. Phase별 구현 내용

#### Phase 1: 인프라 검증 (~6초)
- **PostgreSQL (TimescaleDB)**: 연결 확인, 간단한 쿼리 실행, TimescaleDB 확장 확인
- **Redis**: PING 명령, SET/GET 테스트
- **RabbitMQ**: 연결 확인, 큐 생성/삭제, 메시지 publish/consume 테스트
- **OpenSearch**: 클러스터 상태 조회, 간단한 검색 쿼리

**Gemini 토큰 사용**: 0

#### Phase 2: 외부 API 검증 (~5초)
- **DART API**: API 키 유효성 확인, 기업 정보 조회 (삼성전자)
- **Gemini API**: 최소 토큰 테스트 (입력: "Hi", 출력: ~5 tokens)

**Gemini 토큰 사용**: ~5 tokens

#### Phase 3: 데이터 정합성 검증 (~6초)
- **Company 데이터**: 필수 필드 검증, corp_code/stock_code 유효성 확인
- **FinancialStatement 데이터**: 2025-2026 데이터 제외 확인, 재무 지표 범위 검증
- **Report 데이터**: 제출일 형식 검증, rcept_no 중복 확인
- **Price 데이터**: 가격 유효성 검증, 시계열 데이터 정렬 확인

**Gemini 토큰 사용**: 0

#### Phase 4: 보고서 처리 파이프라인 검증 (~16초)
- **보고서 선택**: 가장 짧은 보고서 선택 (<500자)
- **파이프라인 실행**:
  1. 보고서 내용 추출
  2. 정보 정제
  3. Gemini API 호출 (정보 추출)
  4. 임베딩 생성
  5. OpenSearch 저장
- **결과 검증**: ProcessedReport 생성 확인, 필드 검증

**Gemini 토큰 사용**: ~650 tokens (입력 ~500 + 출력 ~150)

**예상 비용**: $0.00011 (Gemini Flash 1.5 기준)

### 3. API 엔드포인트

**URL**: `POST /api/companies/test/e2e/`

**권한**: 관리자 전용 (`IsAdminUser`)

**요청 형식**:
```json
{
  "phases": [1, 2, 3, 4],  // 실행할 Phase 선택 (optional, default: all)
  "skip_gemini": false      // Gemini 사용 스킵 여부 (optional)
}
```

**응답 형식**:
```json
{
  "status": "success",
  "total_duration": 33.5,
  "gemini_tokens_used": 655,
  "estimated_cost": 0.00011,
  "phases": {
    "phase1_infrastructure": {
      "status": "success",
      "duration": 6.2,
      "checks": {
        "postgresql": {"status": "ok", "duration": 0.15},
        "redis": {"status": "ok", "duration": 0.05},
        "rabbitmq": {"status": "ok", "duration": 1.2},
        "opensearch": {"status": "ok", "duration": 0.8}
      }
    },
    "phase2_external_api": {
      "status": "success",
      "duration": 5.1,
      "checks": {
        "dart_api": {"status": "ok", "duration": 2.3},
        "gemini_api": {"status": "ok", "duration": 2.8, "tokens": 5}
      },
      "tokens_used": 5
    },
    "phase3_data_integrity": {
      "status": "success",
      "duration": 6.0,
      "checks": {
        "company_data": {"status": "ok", "count": 150},
        "financial_data": {"status": "ok", "latest_year": 2024},
        "report_data": {"status": "ok", "count": 1234},
        "price_data": {"status": "ok", "latest_date": "2026-01-23"}
      }
    },
    "phase4_report_pipeline": {
      "status": "success",
      "duration": 16.2,
      "report_id": "20240101000123",
      "checks": {
        "report_selection": {"status": "ok"},
        "pipeline": {
          "status": "ok",
          "checks": {
            "task_execution": {"status": "ok"},
            "processing_status": {"status": "ok"},
            "extracted_info": {"status": "ok"},
            "embedding": {"status": "ok"},
            "opensearch": {"status": "ok"}
          }
        }
      },
      "tokens_used": 650
    }
  }
}
```

## 사용 방법

### 1. 테스트 스크립트 사용

```bash
# 관리자 토큰 발급 (Django Admin 또는 JWT 토큰)
# 예: python manage.py createsuperuser

# 테스트 실행
./test_e2e.sh <ADMIN_TOKEN>

# 옵션 선택:
# 1. 전체 Phase 실행 (Gemini 사용) - ~33초, ~655 tokens, ~$0.00011
# 2. 전체 Phase 실행 (Gemini 스킵) - ~17초, 0 tokens, $0
# 3. Phase 1, 2, 3만 실행 (Gemini 최소 사용) - ~17초, ~5 tokens, ~$0.00001
# 4. Phase 1만 실행 (인프라 검증) - ~6초, 0 tokens, $0
```

### 2. cURL 직접 사용

```bash
# 전체 Phase 실행 (Gemini 사용)
curl -X POST "http://localhost:8000/api/companies/test/e2e/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -d '{"phases": [1, 2, 3, 4], "skip_gemini": false}'

# 전체 Phase 실행 (Gemini 스킵)
curl -X POST "http://localhost:8000/api/companies/test/e2e/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -d '{"phases": [1, 2, 3, 4], "skip_gemini": true}'

# Phase 1만 실행 (인프라 검증)
curl -X POST "http://localhost:8000/api/companies/test/e2e/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -d '{"phases": [1], "skip_gemini": true}'
```

### 3. Swagger UI 사용

1. 브라우저에서 `http://localhost:8000/api/schema/swagger-ui/` 접속
2. `Admin` 태그의 `E2E 테스트 실행 (관리자용)` 엔드포인트 찾기
3. `Authorize` 버튼 클릭하여 관리자 토큰 입력
4. 요청 파라미터 입력 후 `Execute` 클릭

## Gemini 토큰 최적화

### 기본 실행 (전체 Phase)
- **토큰 사용량**: ~655 tokens
- **예상 비용**: $0.00011 (Gemini Flash 1.5 기준)
- **실행 시간**: ~33초

### Gemini 스킵 모드
- **토큰 사용량**: 0 tokens
- **예상 비용**: $0
- **실행 시간**: ~17초
- **스킵되는 Phase**: Phase 2의 Gemini API 테스트, Phase 4 전체

### Phase 선택 실행
- **Phase 1만**: 0 tokens, $0, ~6초
- **Phase 1, 2, 3**: ~5 tokens, ~$0.00001, ~17초
- **Phase 1, 3**: 0 tokens, $0, ~12초

## 성공 기준

- [x] 모든 인프라 서비스 연결 성공
- [x] DART API 정상 응답
- [x] Gemini API 정상 응답 (최소 토큰)
- [x] 2025-2026 재무제표 데이터 없음
- [x] 보고서 처리 파이프라인 완료
- [x] OpenSearch 인덱싱 성공
- [x] Gemini 토큰 사용량 700 이하
- [x] 전체 실행 시간 40초 이하

## 주의사항

1. **Gemini API 호출 최소화**: Phase 2에서 "Hi" 테스트, Phase 4에서 최단 보고서 1개만
2. **타임아웃 설정**: 각 Phase별 적절한 타임아웃 설정 (Phase 4: 60초)
3. **관리자 전용**: 이 API는 관리자 권한 필요 (`@permission_classes([IsAdminUser])`)
4. **트랜잭션 롤백**: Phase 4는 실제 데이터를 생성하므로 주의
5. **Celery Worker**: Phase 4는 Celery Worker가 실행 중이어야 함

## 문제 해결

### Phase 1 실패 시
- PostgreSQL, Redis, RabbitMQ, OpenSearch 서비스 상태 확인
- Docker Compose: `docker-compose up db redis rabbitmq opensearch`

### Phase 2 실패 시
- DART_API_KEY, GEMINI_API_KEY 환경 변수 확인
- `.env` 파일에 API 키 설정 확인

### Phase 3 실패 시
- 데이터베이스 마이그레이션 실행: `python manage.py migrate`
- 기업 데이터 동기화: `POST /api/companies/sync/top/` (limit: 100)

### Phase 4 실패 시
- Celery Worker 실행 확인: `celery -A config worker -l info`
- RabbitMQ 상태 확인
- 보고서 데이터 존재 확인

## 다음 단계

1. **CI/CD 통합**: GitHub Actions에서 자동 실행
2. **모니터링**: Phase별 실행 시간 및 성공률 추적
3. **알림**: 실패 시 Slack 알림
4. **주기적 실행**: 매일 새벽 자동 실행하여 시스템 상태 확인
5. **상세 로그**: 각 Phase별 상세 로그 저장

## 구현 날짜

2026-01-23

## 구현자

Claude Code (Anthropic)

## 관련 문서

- [E2E 테스트 API 구현 계획](./e2e-test-api-implementation.md)
- [Django REST Framework 문서](https://www.django-rest-framework.org/)
- [Celery 문서](https://docs.celeryproject.org/)
- [Gemini API 문서](https://ai.google.dev/docs)
