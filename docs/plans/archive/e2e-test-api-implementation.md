# E2E 테스트 API 구현 계획

## 개요

Gemini 토큰 사용을 최소화하면서 실제 연결과 데이터 정합성, 신뢰성을 검증하는 End-to-End 테스트 API를 구현합니다.

## 목표

- **인프라 검증**: DB, Redis, RabbitMQ, OpenSearch 연결 상태 확인
- **외부 API 검증**: DART API, Gemini API 연결 확인
- **데이터 정합성 검증**: 실제 데이터의 무결성 및 일관성 확인
- **보고서 처리 파이프라인 검증**: Gemini를 사용한 전체 파이프라인 테스트
- **비용 최적화**: Gemini 토큰 사용 최소화 (~650 tokens, $0.00011)

## 구현 계획

### Phase 1: 인프라 검증 (예상 시간: ~6초)

**목적**: 모든 인프라 서비스의 연결 상태 확인

**검증 항목**:
1. **PostgreSQL (TimescaleDB)**
   - 연결 가능 여부
   - 간단한 쿼리 실행 (`SELECT 1`)
   - 응답 시간 측정

2. **Redis**
   - 연결 가능 여부
   - PING 명령 실행
   - 간단한 SET/GET 테스트

3. **RabbitMQ**
   - 연결 가능 여부
   - 큐 생성 및 삭제 테스트
   - 메시지 publish/consume 테스트

4. **OpenSearch**
   - 연결 가능 여부
   - 클러스터 상태 조회
   - 간단한 검색 쿼리 실행

**구현 파일**: `companies/tests/e2e/test_phase1_infrastructure.py`

**Gemini 토큰 사용**: 0

---

### Phase 2: 외부 API 검증 (예상 시간: ~5초)

**목적**: 외부 API 연결 및 인증 확인

**검증 항목**:
1. **DART API**
   - API 키 유효성 확인
   - 간단한 기업 정보 조회 (예: 삼성전자)
   - 응답 형식 검증

2. **Gemini API**
   - API 키 유효성 확인
   - 최소 토큰 테스트 (입력: "Hi", 예상 응답: 5 tokens)
   - 응답 시간 측정

**구현 파일**: `companies/tests/e2e/test_phase2_external_api.py`

**Gemini 토큰 사용**: ~5 tokens (minimal health check)

---

### Phase 3: 데이터 정합성 검증 (예상 시간: ~6초)

**목적**: 실제 데이터의 무결성 및 일관성 확인

**검증 항목**:
1. **Company 데이터**
   - 최소 1개 이상의 기업 존재
   - 필수 필드 검증 (stock_code, corp_code, company_name)
   - corp_code와 stock_code 유효성 확인

2. **FinancialStatement 데이터**
   - 2024년 이하 데이터만 존재 (2025-2026 제외)
   - 재무 지표 값 범위 검증
   - 기업과의 관계 검증

3. **Report 데이터**
   - 보고서 제출일 형식 검증
   - 기업과의 관계 검증
   - rcept_no 중복 확인

4. **Price 데이터**
   - 최신 주가 데이터 존재 확인
   - 가격 값 유효성 검증 (> 0)
   - 시계열 데이터 정렬 확인

**구현 파일**: `companies/tests/e2e/test_phase3_data_integrity.py`

**Gemini 토큰 사용**: 0

---

### Phase 4: 보고서 처리 파이프라인 검증 (예상 시간: ~16초)

**목적**: Gemini를 사용한 전체 보고서 처리 파이프라인 검증

**검증 항목**:
1. **테스트 보고서 선택**
   - DB에서 가장 짧은 보고서 선택 (<500자)
   - 또는 더미 보고서 생성 (최소 내용)

2. **보고서 처리 파이프라인 실행**
   - `extract_report_info_task` Celery 작업 트리거
   - 파이프라인 단계별 검증:
     - 보고서 내용 추출
     - 정보 정제
     - Gemini API 호출 (정보 추출)
     - 임베딩 생성
     - OpenSearch 저장

3. **결과 검증**
   - ProcessedReport 생성 확인
   - 추출된 정보 필드 검증
   - OpenSearch 인덱싱 확인

**구현 파일**: `companies/tests/e2e/test_phase4_report_pipeline.py`

**Gemini 토큰 사용**: ~650 tokens (입력 ~500 + 출력 ~150)

**예상 비용**: $0.00011 (Gemini Flash 기준)

---

## API 엔드포인트 설계

**URL**: `POST /api/companies/test/e2e/`

**요청 파라미터**:
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
      }
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
        "extract": {"status": "ok"},
        "refine": {"status": "ok"},
        "gemini_extract": {"status": "ok", "tokens": 650},
        "embedding": {"status": "ok"},
        "opensearch": {"status": "ok"}
      }
    }
  }
}
```

**오류 응답**:
```json
{
  "status": "error",
  "phase": "phase2_external_api",
  "check": "dart_api",
  "error": "Connection timeout",
  "details": "Failed to connect to DART API after 3 retries"
}
```

---

## 파일 구조

```
companies/
├── tests/
│   ├── e2e/
│   │   ├── __init__.py
│   │   ├── test_phase1_infrastructure.py
│   │   ├── test_phase2_external_api.py
│   │   ├── test_phase3_data_integrity.py
│   │   └── test_phase4_report_pipeline.py
│   └── services/
│       ├── __init__.py
│       └── e2e_runner.py              # 통합 실행 로직
├── views.py                            # API 엔드포인트 추가
└── urls.py                             # URL 라우팅 추가
```

---

## 구현 단계

### Step 1: E2E Runner 서비스 구현
- 파일: `companies/tests/services/e2e_runner.py`
- 각 Phase별 테스트 실행 로직
- 결과 취합 및 응답 생성

### Step 2: Phase 1 테스트 구현
- 파일: `companies/tests/e2e/test_phase1_infrastructure.py`
- PostgreSQL, Redis, RabbitMQ, OpenSearch 연결 테스트

### Step 3: Phase 2 테스트 구현
- 파일: `companies/tests/e2e/test_phase2_external_api.py`
- DART API, Gemini API 연결 테스트

### Step 4: Phase 3 테스트 구현
- 파일: `companies/tests/e2e/test_phase3_data_integrity.py`
- 데이터 정합성 검증 로직

### Step 5: Phase 4 테스트 구현
- 파일: `companies/tests/e2e/test_phase4_report_pipeline.py`
- 보고서 처리 파이프라인 전체 검증

### Step 6: API 엔드포인트 추가
- 파일: `companies/views.py`
- E2E 테스트 API 뷰 함수 구현

### Step 7: URL 라우팅 추가
- 파일: `companies/urls.py`
- `/api/companies/test/e2e/` 경로 추가

---

## Gemini 토큰 최적화 전략

1. **Phase 2 최소 테스트**: "Hi" 입력으로 5 토큰만 사용하여 API 연결 확인
2. **Phase 4 단일 보고서**: 가장 짧은 보고서 1개만 처리
3. **조건부 실행**: `skip_gemini=true` 옵션으로 Phase 2, 4 스킵 가능
4. **Phase 선택**: 필요한 Phase만 선택 실행하여 비용 절감

**총 Gemini 토큰 사용량**: ~655 tokens
**예상 비용**: $0.00011 (Gemini Flash 1.5 기준)

---

## 성공 기준

- [ ] 모든 인프라 서비스 연결 성공
- [ ] DART API 정상 응답
- [ ] Gemini API 정상 응답 (최소 토큰)
- [ ] 2025-2026 재무제표 데이터 없음
- [ ] 보고서 처리 파이프라인 완료
- [ ] OpenSearch 인덱싱 성공
- [ ] Gemini 토큰 사용량 700 이하
- [ ] 전체 실행 시간 40초 이하

---

## 주의사항

1. **Gemini API 호출 최소화**: Phase 2에서 "Hi" 테스트, Phase 4에서 최단 보고서 1개만
2. **타임아웃 설정**: 각 Phase별 적절한 타임아웃 설정 (총 40초 이내)
3. **오류 처리**: 각 단계별 상세한 오류 메시지 반환
4. **트랜잭션 롤백**: 테스트용 데이터는 자동 롤백하여 DB 오염 방지
5. **관리자 전용**: 이 API는 관리자 권한 필요 (`@permission_classes([IsAdminUser])`)
