# 기업 전망 분석 기능 구현 계획

## 개요

OpenSearch에 저장된 특정 기업의 뉴스와 보고서를 분석하여 퀀트 투자자가 의사결정을 할 수 있는 전망을 제공하는 기능입니다.

**분석 결과:**
- **분석 내용**: 3줄 이내 문장 (투자 전망 요약)
- **상승 여력**: `high` 또는 `low`
- **투자 신호**: `buy` 또는 `sell`

**핵심 기술:**
- Django 6.0 + DRF
- OpenSearch (뉴스/보고서 벡터 검색)
- Gemini API (전망 분석 LLM)
- Redis (캐싱)

## 비용 예측

### Gemini 2.5 Flash Lite 단가

- 입력: $0.10 / 1M tokens
- 출력: $0.40 / 1M tokens

### 분석 1건당 예상 비용

| 단계 | 입력 토큰 | 출력 토큰 | 예상 비용 |
|------|----------|----------|----------|
| 뉴스 + 보고서 컨텍스트 | ~2,000 | - | ~$0.0002 |
| LLM 분석 응답 | - | ~200 | ~$0.00008 |
| **합계** | - | - | **~$0.00028** |

### 규모별 예상 비용

| 규모 | 요청 수 | 예상 비용 |
|------|---------|----------|
| 일 100회 | 3,000/월 | ~$0.84/월 |
| 일 1,000회 | 30,000/월 | ~$8.4/월 |
| 일 10,000회 | 300,000/월 | ~$84/월 |

> **참고**: Redis 캐싱(TTL 1시간)으로 동일 종목 반복 요청 시 LLM 호출 없이 응답하여 비용 80% 이상 절감 가능

## 아키텍처

```
[클라이언트] → GET /api/companies/{stock_code}/outlook/
                     ↓
              [Django API]
                     ↓
              [Redis 캐시 확인]
                     ↓ (캐시 미스)
              ┌──────┴──────┐
              ↓             ↓
       [OpenSearch]    [OpenSearch]
       (뉴스 검색)     (보고서 검색)
       (키워드 기반)   (벡터 유사도)
              └──────┬──────┘
                     ↓
              [Gemini LLM]
              (전망 분석)
                     ↓
              [Redis 캐시 저장]
                     ↓
              [JSON 응답]
```

**데이터 흐름:**
1. API 요청 수신 (stock_code)
2. Redis 캐시 확인 (TTL: 1시간)
3. 캐시 미스 시 OpenSearch에서 데이터 검색
   - 뉴스: 기업명 키워드 검색 (`search_news_by_keyword`)
   - 보고서: 벡터 유사도 검색 (`search_similar_reports`)
4. Gemini LLM으로 전망 분석 생성
5. 결과 캐싱 및 응답 반환

## API 설계

### 엔드포인트

```
GET /api/companies/{stock_code}/outlook/
```

### 요청 파라미터

| 파라미터 | 타입 | 기본값 | 최대값 | 설명 |
|---------|------|-------|-------|------|
| `days_back` | int | 30 | 90 | 뉴스/보고서 검색 기간 (일) |
| `max_news` | int | 10 | 20 | 최대 뉴스 수 |
| `max_reports` | int | 5 | 10 | 최대 보고서 수 |

### 응답 형식

```json
{
  "status": 200,
  "message": "기업 전망 분석 성공",
  "data": {
    "stock_code": "005930",
    "company_name": "삼성전자",
    "analyzed_at": "2026-01-18T10:30:00+09:00",
    "analysis": "삼성전자는 반도체 수요 회복으로 실적 개선이 기대됩니다. AI 반도체 시장 진출 확대와 HBM 생산 증가가 긍정적 요인입니다. 다만 중국 시장 불확실성은 리스크 요인으로 남아있습니다.",
    "upside_potential": "high",
    "signal": "buy",
    "data_sources": {
      "news_count": 10,
      "report_count": 3
    }
  }
}
```

### 에러 응답

| 상태 코드 | 상황 | 응답 예시 |
|----------|-----|----------|
| 404 | 기업 없음 | `{"status": 404, "error": "Company not found"}` |
| 429 | LLM 쿼터 초과 | `{"status": 429, "error": "API 요청 한도 초과", "retry_after": 3600}` |
| 503 | LLM 서비스 장애 | `{"status": 503, "error": "분석 서비스 일시 불가"}` |

## 구현 상세

### 서비스 클래스

**companies/services/outlook.py (신규)**

```python
"""
기업 전망 분석 서비스

OpenSearch에서 뉴스와 보고서를 검색하고,
Gemini LLM을 통해 투자 전망을 분석합니다.
"""

from django.conf import settings
from django.core.cache import cache
from google import genai
from datetime import datetime, timedelta
import json
import logging

from companies.models import Company
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.opensearch import OpenSearchService
from news.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class CompanyOutlookService:
    """기업 전망 분석 서비스"""

    # 캐시 TTL (초)
    DEFAULT_CACHE_TTL = 3600  # 1시간

    # LLM 모델
    MODEL_NAME = "gemini-2.5-flash-lite"

    def __init__(self):
        self.news_opensearch = OpenSearchService()
        self.report_opensearch = ReportOpenSearchService()
        self.embedding_service = EmbeddingService()

        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        self.gemini_client = genai.Client(api_key=api_key)

    def analyze_outlook(
        self,
        company: Company,
        days_back: int = 30,
        max_news: int = 10,
        max_reports: int = 5,
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ) -> dict:
        """
        기업 전망 분석 수행

        Args:
            company: 분석할 기업 객체
            days_back: 검색 기간 (일)
            max_news: 최대 뉴스 수
            max_reports: 최대 보고서 수
            cache_ttl: 캐시 유효 기간 (초)

        Returns:
            분석 결과 딕셔너리
        """
        # 1. 캐시 확인
        cache_key = f"outlook:{company.stock_code}:v1"
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.debug(f"캐시 히트: {cache_key}")
            return cached_result

        # 2. 데이터 검색
        search_data = self._search_company_data(
            company, days_back, max_news, max_reports
        )

        # 3. LLM 분석
        analysis_result = self._generate_analysis(company, search_data)

        # 4. 결과 구성
        result = {
            "stock_code": company.stock_code,
            "company_name": company.company_name,
            "analyzed_at": datetime.now().isoformat(),
            "analysis": analysis_result.get("analysis", ""),
            "upside_potential": analysis_result.get("upside_potential", "low"),
            "signal": analysis_result.get("signal", "sell"),
            "data_sources": {
                "news_count": len(search_data.get("news", [])),
                "report_count": len(search_data.get("reports", [])),
            },
        }

        # 5. 캐시 저장
        cache.set(cache_key, result, timeout=cache_ttl)

        return result

    def _search_company_data(
        self,
        company: Company,
        days_back: int,
        max_news: int,
        max_reports: int,
    ) -> dict:
        """뉴스와 보고서 검색"""
        # 뉴스 검색 (키워드 기반)
        published_after = datetime.now() - timedelta(days=days_back)
        news_results = self.news_opensearch.search_news_by_keyword(
            keyword=company.company_name,
            size=max_news,
            published_after=published_after,
        )

        # 보고서 검색 (벡터 유사도)
        query_text = f"{company.company_name} 실적 전망"
        query_vector = self.embedding_service.create_embedding(query_text)

        report_results = []
        if query_vector:
            report_results = self.report_opensearch.search_similar_reports(
                query_vector=query_vector,
                size=max_reports,
                company_stock_code=company.stock_code,
            )

        return {
            "news": news_results or [],
            "reports": report_results or [],
        }

    def _generate_analysis(
        self,
        company: Company,
        search_data: dict,
    ) -> dict:
        """LLM 분석 생성"""
        news_data = search_data.get("news", [])
        report_data = search_data.get("reports", [])

        # 뉴스 제목 리스트 구성
        news_summaries = "\n".join([
            f"- [{n.get('published_at', 'N/A')[:10]}] {n.get('title', '')}"
            for n in news_data[:10]
        ]) or "최근 뉴스 없음"

        # 보고서 요약 구성
        report_summaries = "\n".join([
            f"- [{r.get('submitted_at', 'N/A')[:10]}] {r.get('report_name', '')}: {r.get('summary', '')[:100]}"
            for r in report_data[:5]
        ]) or "최근 보고서 없음"

        # 프롬프트 구성
        prompt = self._build_prompt(
            company=company,
            news_summaries=news_summaries,
            report_summaries=report_summaries,
            news_count=len(news_data),
            report_count=len(report_data),
        )

        # LLM 호출
        try:
            response = self.gemini_client.models.generate_content(
                model=self.MODEL_NAME,
                contents=prompt,
            )
            text = response.text.strip()

            # JSON 파싱
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                result = json.loads(text[start:end])
                return self._validate_result(result)

        except Exception as e:
            logger.error(f"LLM 분석 실패: {company.stock_code} - {e}")

        # 기본 응답
        return {
            "analysis": "분석 데이터가 부족하여 정확한 전망을 제공하기 어렵습니다.",
            "upside_potential": "low",
            "signal": "sell",
        }

    def _build_prompt(
        self,
        company: Company,
        news_summaries: str,
        report_summaries: str,
        news_count: int,
        report_count: int,
    ) -> str:
        """분석 프롬프트 구성"""
        market_amount_str = f"{company.market_amount:,}" if company.market_amount else "N/A"

        return f"""당신은 퀀트 투자 분석 전문가입니다. 아래 정보를 바탕으로 투자 전망을 분석하세요.

## 기업 정보
- 기업명: {company.company_name}
- 종목코드: {company.stock_code}
- 시가총액: {market_amount_str}원

## 최근 뉴스 ({news_count}건)
{news_summaries}

## 최근 공시 보고서 ({report_count}건)
{report_summaries}

## 분석 요청
위 정보를 종합하여 다음 형식의 JSON으로 응답하세요:

{{
    "analysis": "3줄 이내의 투자 전망 분석 (구체적인 근거 포함)",
    "upside_potential": "high" 또는 "low",
    "signal": "buy" 또는 "sell"
}}

## 분석 기준
- upside_potential "high": 긍정적 뉴스/실적 개선/성장 동력 존재
- upside_potential "low": 부정적 뉴스/실적 악화/리스크 요인 존재
- signal "buy": 상승 여력 높고 진입 시점 적절
- signal "sell": 하락 리스크 높거나 차익 실현 권장

## 주의사항
- 추측이 아닌 제공된 데이터에 기반하여 분석하세요
- analysis는 한국어로 작성하고, 3줄 이내로 간결하게 작성하세요
- JSON 형식 외 다른 텍스트를 포함하지 마세요
"""

    def _validate_result(self, result: dict) -> dict:
        """결과 검증 및 정규화"""
        validated = {}

        # analysis 검증
        analysis = result.get("analysis", "")
        if isinstance(analysis, str) and len(analysis) > 0:
            validated["analysis"] = analysis[:500]  # 최대 500자
        else:
            validated["analysis"] = "분석 결과를 생성할 수 없습니다."

        # upside_potential 검증
        upside = str(result.get("upside_potential", "")).lower()
        validated["upside_potential"] = "high" if upside == "high" else "low"

        # signal 검증
        signal = str(result.get("signal", "")).lower()
        validated["signal"] = "buy" if signal == "buy" else "sell"

        return validated
```

### API 뷰

**companies/views.py에 추가:**

```python
@extend_schema(
    summary="기업 전망 분석",
    description="""
    특정 기업의 뉴스와 보고서를 분석하여 투자 전망을 제공합니다.

    **분석 결과:**
    - analysis: 3줄 이내 투자 전망 분석
    - upside_potential: 상승 여력 (high/low)
    - signal: 투자 신호 (buy/sell)

    **캐싱:** 동일 종목 요청 시 1시간 동안 캐시된 결과 반환
    """,
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="종목코드 (예: 005930)",
        ),
        OpenApiParameter(
            name="days_back",
            type=int,
            location=OpenApiParameter.QUERY,
            description="검색 기간 (일, 기본값: 30)",
            required=False,
        ),
        OpenApiParameter(
            name="max_news",
            type=int,
            location=OpenApiParameter.QUERY,
            description="최대 뉴스 수 (기본값: 10, 최대: 20)",
            required=False,
        ),
        OpenApiParameter(
            name="max_reports",
            type=int,
            location=OpenApiParameter.QUERY,
            description="최대 보고서 수 (기본값: 5, 최대: 10)",
            required=False,
        ),
    ],
    responses={
        200: OpenApiResponse(description="분석 성공"),
        404: OpenApiResponse(description="기업을 찾을 수 없음"),
        503: OpenApiResponse(description="분석 서비스 일시 불가"),
    },
    tags=["Company"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_company_outlook(request, stock_code):
    """기업 전망 분석 API"""
    from companies.services.outlook import CompanyOutlookService

    # 기업 조회
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)
    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # 파라미터 파싱
    try:
        days_back = min(int(request.query_params.get("days_back", 30)), 90)
        max_news = min(int(request.query_params.get("max_news", 10)), 20)
        max_reports = min(int(request.query_params.get("max_reports", 5)), 10)
    except (ValueError, TypeError):
        return Response(
            {"status": 400, "error": "파라미터는 정수여야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 분석 수행
    try:
        service = CompanyOutlookService()
        result = service.analyze_outlook(
            company=company,
            days_back=days_back,
            max_news=max_news,
            max_reports=max_reports,
        )

        return Response(
            {
                "status": 200,
                "message": "기업 전망 분석 성공",
                "data": result,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception(f"기업 전망 분석 오류: {stock_code}")
        return Response(
            {
                "status": 503,
                "error": "분석 서비스를 일시적으로 사용할 수 없습니다",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
```

### URL 패턴

**companies/urls.py에 추가:**

```python
from .views import (
    # ... 기존 imports ...
    get_company_outlook,
)

urlpatterns = [
    # ... 기존 URL 패턴들 ...

    # 기업 전망 분석
    path("<str:stock_code>/outlook/", get_company_outlook, name="company_outlook"),
]
```

## 파일 구조

```
companies/
├── services/
│   ├── outlook.py              # 전망 분석 서비스 (신규)
│   ├── report_opensearch.py    # 기존 보고서 OpenSearch 서비스
│   └── ...
├── views.py                    # API 뷰 (수정)
└── urls.py                     # URL 패턴 (수정)
```

## 구현 순서

1. [ ] `companies/services/outlook.py` 생성
2. [ ] `companies/views.py`에 `get_company_outlook` 뷰 추가
3. [ ] `companies/urls.py`에 URL 패턴 추가
4. [ ] API 테스트 (Swagger UI)
5. [ ] 캐싱 동작 확인

## 테스트 방법

### 1. 개발 서버 실행

```bash
python manage.py runserver
```

### 2. API 호출

```bash
# 기본 요청
curl http://localhost:8000/api/companies/005930/outlook/

# 파라미터 지정
curl "http://localhost:8000/api/companies/005930/outlook/?days_back=60&max_news=15"
```

### 3. Swagger UI

```
http://localhost:8000/swagger/
```

Companies 태그에서 `/api/companies/{stock_code}/outlook/` 확인

## LLM 선택 근거

### Gemini 2.5 Flash Lite

| 항목 | Gemini Flash Lite | OpenAI GPT-4 Turbo | Claude 3 Haiku |
|-----|------------------|-------------------|----------------|
| 입력 비용 | $0.10/1M | $10/1M | $0.25/1M |
| 출력 비용 | $0.40/1M | $30/1M | $1.25/1M |
| 속도 | 빠름 | 보통 | 빠름 |
| 한국어 | 우수 | 우수 | 우수 |

**선택 이유:**
1. 기존 프로젝트에서 이미 사용 중 (일관성)
2. 가장 저렴한 비용
3. 빠른 응답 속도
4. 한국어 분석에 충분한 성능

## 최적화 전략

### 1. 캐싱 (Redis)

- 캐시 키: `outlook:{stock_code}:v1`
- TTL: 1시간 (기본)
- 예상 캐시 히트율: 70-80%

### 2. 토큰 절약

- 뉴스: 제목만 사용 (본문 X)
- 보고서: 요약만 사용 (본문 X)
- 최대 입력: ~2,000 토큰

### 3. 응답 시간

| 단계 | 예상 시간 |
|-----|----------|
| 캐시 히트 | ~10ms |
| 캐시 미스 (전체) | ~3초 |
| - OpenSearch 검색 | ~500ms |
| - LLM 호출 | ~2,000ms |
| - 기타 처리 | ~500ms |

## 주의사항

1. **OpenSearch 데이터 필요**: 뉴스와 보고서가 OpenSearch에 인덱싱되어 있어야 함
2. **GEMINI_API_KEY 설정**: `.env` 파일에 API 키 필수
3. **Redis 설정**: 캐싱을 위해 Redis 연결 필요
4. **Rate Limiting**: Gemini API 요청 제한 고려 (분당 15회 무료 티어)
5. **데이터 부족 시**: 기본 응답 반환 (분석 불가 메시지)

## 향후 개선 가능 사항

1. **신뢰도 점수 추가**: 분석 근거 데이터 양에 따른 신뢰도 표시
2. **비동기 처리 옵션**: 대량 분석 요청 시 Celery 태스크 활용
3. **분석 히스토리**: 분석 결과 DB 저장 및 추이 조회
4. **실시간 갱신**: 주요 공시 발생 시 캐시 무효화
