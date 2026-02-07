# 산업 전망 분석 기능 구현 계획

## 개요

OpenSearch에 저장된 특정 산업 관련 뉴스와 해당 산업 소속 기업들의 보고서를 분석하여 퀀트 투자자가 산업 트렌드를 파악할 수 있는 전망을 제공하는 기능입니다.

**분석 결과:**
- **낙관 시나리오 (Optimistic)**: 3줄 이내 분석 + 핵심 요인
- **중립 시나리오 (Neutral)**: 3줄 이내 분석 + 핵심 요인
- **비관 시나리오 (Pessimistic)**: 3줄 이내 분석 + 핵심 요인

**핵심 기술:**
- Django 6.0 + DRF
- OpenSearch (뉴스/보고서 검색)
- Gemini API (전망 분석 LLM)
- Redis (캐싱)
- KSIC 코드 기반 산업 분류

## 기업 전망 분석과의 차이점

| 항목 | 기업 전망 분석 | 산업 전망 분석 |
|------|--------------|--------------|
| **분석 대상** | 특정 기업 | 특정 산업 |
| **데이터 소스** | 기업 뉴스 + 공시 보고서 | 산업 뉴스 + 산업 내 기업들 보고서 + 산업 통계 |
| **응답 구조** | 단일 분석 + upside_potential + signal | 낙관/중립/비관 시나리오별 분석 |
| **분석 단위** | 개별 종목 | 업종 전체 |
| **활용 목적** | 종목 선정 | 업종 트렌드 파악 |

## 비용 예측

### Gemini 2.0 Flash 단가

- 입력: $0.10 / 1M tokens
- 출력: $0.40 / 1M tokens

### 분석 1건당 예상 비용

| 단계 | 입력 토큰 | 출력 토큰 | 예상 비용 |
|------|----------|----------|----------|
| 산업 뉴스 + 기업 보고서 + 통계 | ~3,000 | - | ~$0.0003 |
| LLM 시나리오 분석 응답 | - | ~400 | ~$0.00016 |
| **합계** | - | - | **~$0.00046** |

### 규모별 예상 비용

| 규모 | 요청 수 | 예상 비용 |
|------|---------|----------|
| 일 50회 | 1,500/월 | ~$0.69/월 |
| 일 500회 | 15,000/월 | ~$6.9/월 |
| 일 5,000회 | 150,000/월 | ~$69/월 |

> **참고**: Redis 캐싱(TTL 1시간)으로 동일 산업 반복 요청 시 LLM 호출 없이 응답하여 비용 절감 가능

## 아키텍처

```
[클라이언트] → GET /api/industries/{industry_id}/outlook/
                     ↓
              [Django API]
                     ↓
              [Redis 캐시 확인]
                     ↓ (캐시 미스)
         ┌───────────┴───────────┐
         ↓                       ↓
   [OpenSearch]            [PostgreSQL]
   - 산업 뉴스 검색          - 산업 기업 목록
   - 기업 보고서 검색        - 산업 통계
         └───────────┬───────────┘
                     ↓
              [Gemini LLM]
         (낙관/중립/비관 시나리오 분석)
                     ↓
              [Redis 캐시 저장]
                     ↓
              [JSON 응답]
```

**데이터 흐름:**
1. API 요청 수신 (industry_id)
2. Redis 캐시 확인 (TTL: 1시간)
3. 캐시 미스 시 다음 데이터 수집:
   - 산업명 키워드로 뉴스 검색 (OpenSearch)
   - 해당 산업 소속 기업 목록 조회 (PostgreSQL)
   - 기업들의 공시 보고서 검색 (OpenSearch/DB)
   - 산업 통계 계산 (기업 수, 평균/총 시가총액)
4. Gemini LLM으로 시나리오별 전망 분석 생성
5. 결과 캐싱 및 응답 반환

## API 설계

### 엔드포인트

```
GET /api/industries/{industry_id}/outlook/
```

### 요청 파라미터

| 파라미터 | 타입 | 기본값 | 최대값 | 설명 |
|---------|------|-------|-------|------|
| `days_back` | int | 30 | 90 | 뉴스/보고서 검색 기간 (일) |
| `max_news` | int | 20 | 50 | 최대 뉴스 수 |
| `max_reports` | int | 10 | 20 | 최대 보고서 수 (산업 내 주요 기업 기준) |
| `top_companies` | int | 10 | 20 | 보고서 수집 대상 상위 기업 수 (시가총액 기준) |

### 응답 형식

```json
{
  "status": 200,
  "message": "산업 전망 분석 성공",
  "data": {
    "industry_id": 1,
    "industry_name": "반도체",
    "ksic_code": "264",
    "analyzed_at": "2026-01-18T10:30:00+09:00",
    "scenarios": {
      "optimistic": {
        "analysis": "AI 반도체 수요 급증과 정부의 반도체 지원 정책 강화로 업황 개선이 기대됩니다. 주요 기업들의 HBM 생산 확대와 첨단 공정 투자 확대가 긍정적입니다. 글로벌 반도체 슈퍼 사이클 진입 가능성이 높아지고 있습니다.",
        "key_factors": [
          "AI 반도체 수요 급증",
          "정부 지원 정책 강화",
          "HBM 생산 확대"
        ]
      },
      "neutral": {
        "analysis": "반도체 업황은 회복세를 보이고 있으나 중국 시장 불확실성이 존재합니다. 메모리 반도체 가격은 안정화되었으나 재고 조정이 필요합니다. 시스템 반도체 부문은 투자 확대 중이나 성과는 중장기적으로 나타날 전망입니다.",
        "key_factors": [
          "중국 시장 불확실성",
          "메모리 가격 안정화",
          "시스템 반도체 투자 확대"
        ]
      },
      "pessimistic": {
        "analysis": "글로벌 경기 둔화로 반도체 수요 감소 우려가 있습니다. 미중 무역 갈등 심화로 공급망 리스크가 증가하고 있습니다. 과잉 투자로 인한 공급 과잉과 가격 하락 압력이 존재합니다.",
        "key_factors": [
          "글로벌 경기 둔화",
          "미중 무역 갈등",
          "공급 과잉 우려"
        ]
      }
    },
    "industry_statistics": {
      "company_count": 45,
      "total_market_cap": 450000000000000,
      "avg_market_cap": 10000000000000,
      "top_companies": [
        {
          "stock_code": "005930",
          "company_name": "삼성전자",
          "market_amount": 400000000000000
        }
      ]
    },
    "data_sources": {
      "news_count": 25,
      "report_count": 12,
      "company_count": 10
    }
  }
}
```

### 에러 응답

| 상태 코드 | 상황 | 응답 예시 |
|----------|-----|----------|
| 404 | 산업 없음 | `{"status": 404, "error": "Industry not found"}` |
| 429 | LLM 쿼터 초과 | `{"status": 429, "error": "API 요청 한도 초과", "retry_after": 3600}` |
| 503 | LLM 서비스 장애 | `{"status": 503, "error": "분석 서비스 일시 불가"}` |

## 구현 상세

### 디렉토리 구조

```
industries/
├── services/
│   └── outlook.py              # 산업 전망 분석 서비스 (신규)
├── views.py                    # API 뷰 (수정)
└── urls.py                     # URL 패턴 (수정)
```

### 서비스 클래스 주요 메서드

**industries/services/outlook.py (신규)**

```python
class IndustryOutlookService:
    """산업 전망 분석 서비스"""

    def analyze_outlook(self, industry: Industry, ...) -> dict:
        """산업 전망 분석 수행"""
        # 1. 캐시 확인
        # 2. 데이터 검색 (뉴스 + 보고서 + 통계)
        # 3. LLM 시나리오 분석 생성
        # 4. 결과 구성 및 캐싱
        # 5. 응답 반환

    def _search_industry_data(self, industry: Industry, ...) -> dict:
        """산업 관련 데이터 검색"""
        # 1. 산업명 키워드로 뉴스 검색
        # 2. 해당 산업 소속 기업 목록 조회
        # 3. 상위 기업들의 보고서 검색
        # 4. 산업 통계 계산

    def _calculate_industry_statistics(self, companies: QuerySet) -> dict:
        """산업 통계 계산"""
        # 기업 수, 총/평균 시가총액, 상위 기업 목록

    def _generate_scenario_analysis(self, industry: Industry, search_data: dict) -> dict:
        """LLM 시나리오별 분석 생성"""
        # Gemini API 호출로 낙관/중립/비관 시나리오 분석
```

### 프롬프트 설계

```python
prompt = f"""당신은 퀀트 투자 산업 분석 전문가입니다.
아래 정보를 바탕으로 {industry.name} 산업의 전망을 낙관/중립/비관 시나리오로 분석하세요.

## 산업 정보
- 산업명: {industry.name}
- KSIC 코드: {industry.induty_code}
- 소속 기업 수: {statistics['company_count']}개
- 총 시가총액: {statistics['total_market_cap']}원

## 최근 뉴스 ({len(news_list)}건)
{news_summaries}

## 주요 기업 공시 보고서 ({len(reports_list)}건)
{report_summaries}

## 분석 요청
위 정보를 종합하여 다음 JSON 형식으로 응답하세요:

{{
  "optimistic": {{
    "analysis": "낙관 시나리오 3줄 이내 분석",
    "key_factors": ["긍정 요인1", "긍정 요인2", "긍정 요인3"]
  }},
  "neutral": {{
    "analysis": "중립 시나리오 3줄 이내 분석",
    "key_factors": ["중립 요인1", "중립 요인2", "중립 요인3"]
  }},
  "pessimistic": {{
    "analysis": "비관 시나리오 3줄 이내 분석",
    "key_factors": ["부정 요인1", "부정 요인2", "부정 요인3"]
  }}
}}

## 시나리오 정의
- **낙관 시나리오**: 긍정적 뉴스, 실적 개선, 정책 지원, 기술 혁신 등 최선의 경우
- **중립 시나리오**: 현재 추세 유지, 불확실성 존재, 관망 필요
- **비관 시나리오**: 부정적 뉴스, 실적 악화, 규제 강화, 구조적 리스크 등 최악의 경우

## 주의사항
- 각 시나리오의 analysis는 반드시 3줄 이내로 작성하세요
- key_factors는 각 시나리오당 2-5개로 구성하세요
- JSON 형식 외 다른 텍스트를 포함하지 마세요
- 추측이 아닌 제공된 데이터에 기반하여 분석하세요
"""
```

## 구현 순서

1. [x] `docs/plans/industry-outlook-analysis.md` 작성
2. [ ] `industries/services/outlook.py` 생성
3. [ ] `industries/views.py`에 `get_industry_outlook` 뷰 추가
4. [ ] `industries/urls.py`에 URL 패턴 추가
5. [ ] API 테스트 (Swagger UI)
6. [ ] 캐싱 동작 확인

## 테스트 방법

### 1. 개발 서버 실행

```bash
python manage.py runserver
```

### 2. API 호출

```bash
# 기본 요청
curl http://localhost:8000/api/industries/1/outlook/

# 파라미터 지정
curl "http://localhost:8000/api/industries/1/outlook/?days_back=60&max_news=30&top_companies=15"
```

### 3. Swagger UI

```
http://localhost:8000/swagger/
```

Industry 태그에서 `/api/industries/{industry_id}/outlook/` 확인

## 데이터 소스 상세

### 1. 즉시 활용 가능 (Phase 1)

#### 산업 관련 뉴스
- **소스**: OpenSearch (news 인덱스)
- **검색 방법**: 산업명 키워드 검색
- **데이터**: 뉴스 제목, 본문 요약, 발행일

#### 산업 소속 기업 공시 보고서
- **소스**: OpenSearch (reports 인덱스) + PostgreSQL (Report 모델)
- **검색 방법**:
  1. 산업 소속 기업 목록 조회 (시가총액 상위 N개)
  2. 각 기업의 최근 보고서 검색
- **데이터**: 보고서명, 요약, 제출일

#### 산업 통계
- **소스**: PostgreSQL (Company 모델)
- **계산 항목**:
  - 소속 기업 수
  - 총 시가총액 (산업 전체)
  - 평균 시가총액
  - 상위 기업 목록 (시가총액 기준)

### 2. 향후 확장 가능 (Phase 2)

#### 한국은행 경제통계
- 산업별 생산지수
- 산업별 매출액 지수
- 고용 통계

#### 금융감독원 OpenDART
- 업종별 재무제표 집계
- 업종별 재무비율 평균

#### 정책/규제 뉴스 필터링
- 정부 정책 발표
- 법안 통과
- 규제 변화

## 최적화 전략

### 1. 캐싱 (Redis)

- 캐시 키: `industry_outlook:{industry_id}:v1`
- TTL: 1시간 (기본)
- 예상 캐시 히트율: 60-70%

### 2. 토큰 절약

- 뉴스: 제목 + 요약 (본문 X)
- 보고서: 보고서명 + 요약 (전체 본문 X)
- 최대 입력: ~3,000 토큰
- 최대 출력: ~400 토큰

### 3. 응답 시간

| 단계 | 예상 시간 |
|-----|----------|
| 캐시 히트 | ~10ms |
| 캐시 미스 (전체) | ~4초 |
| - PostgreSQL 조회 | ~100ms |
| - OpenSearch 검색 | ~700ms |
| - LLM 호출 | ~3,000ms |
| - 기타 처리 | ~200ms |

### 4. 데이터 필터링

- 뉴스: 최신순 정렬, 중복 제거
- 보고서: 시가총액 상위 기업 우선, 최신 보고서만
- 통계: 삭제되지 않은 기업만 집계

## 주의사항

1. **Industry 모델 필수**: industry_id로 산업 조회 가능해야 함
2. **Company.industry 관계**: 기업-산업 매핑이 되어 있어야 함
3. **KSIC 코드**: induty_code 필드에 KSIC 코드 저장 필요
4. **OpenSearch 데이터**: 뉴스와 보고서가 인덱싱되어 있어야 함
5. **GEMINI_API_KEY**: `.env` 파일에 API 키 필수
6. **Redis 설정**: 캐싱을 위해 Redis 연결 필요

## 향후 개선 가능 사항

1. **시계열 트렌드 분석**: TimescaleDB 활용하여 산업 지표 추이 시각화
2. **산업 간 비교**: 여러 산업 동시 분석 및 상관관계 분석
3. **실시간 업데이트**: 주요 뉴스/공시 발생 시 캐시 무효화 및 재분석
4. **외부 데이터 연동**: 한국은행, 금융감독원 API 연동
5. **분석 히스토리**: 분석 결과 DB 저장 및 추이 조회
6. **알림 기능**: 특정 산업 전망 변화 시 사용자 알림

## 기업 전망 분석 코드 재사용

아래 모듈을 재사용합니다:
- `news.services.opensearch.OpenSearchService` (뉴스 검색)
- `companies.services.report_opensearch.ReportOpenSearchService` (보고서 검색)
- `news.services.embedding.EmbeddingService` (벡터 임베딩)

차이점:
- 기업 전망: 단일 기업 → 산업 전망: 산업 내 다수 기업
- 기업 전망: 단일 분석 → 산업 전망: 3개 시나리오
- 기업 전망: buy/sell 신호 → 산업 전망: 시나리오별 핵심 요인
