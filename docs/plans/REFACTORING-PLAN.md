# 코드베이스 리팩토링 계획서

**작성일**: 2025-01-25
**대상**: Django 6.0 백엔드 프로젝트
**상태**: 계획 단계

---

## 목차

1. [개요](#1-개요)
2. [즉시 조치 필요 (Critical)](#2-즉시-조치-필요-critical)
3. [단기 개선 (High Priority)](#3-단기-개선-high-priority)
4. [중기 리팩토링 (Medium Priority)](#4-중기-리팩토링-medium-priority)
5. [장기 구조 개선 (Low Priority)](#5-장기-구조-개선-low-priority)
6. [제거 대상 코드](#6-제거-대상-코드)
7. [구현 로드맵](#7-구현-로드맵)

---

## 1. 개요

### 1.1 분석 범위

- **앱**: companies, news, core, users, industries, indices, comparisons
- **분석 관점**: 중복 코드, 미사용 코드, Celery 태스크, 모델/Serializer 구조

### 1.2 주요 발견사항 요약

| 카테고리 | 발견 건수 | 심각도 |
|---------|----------|--------|
| 중복 코드 패턴 | 9건 | 중간 |
| 미사용 코드 | 7건 | 낮음 |
| Celery 태스크 문제 | 5건 | 높음 |
| 모델/Serializer 문제 | 8건 | 중간 |

---

## 2. 즉시 조치 필요 (Critical)

### 2.1 중복 CORS 미들웨어 제거

**파일**: `config/settings.py`

```python
# 현재 (Line 83, 86에서 중복)
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Line 83
    # ... 다른 미들웨어
    "corsheaders.middleware.CorsMiddleware",  # Line 86 (중복)
]
```

**조치**: Line 86의 중복 미들웨어 제거

---

### 2.2 industries 태스크 `__init__.py` 수정

**파일**: `industries/tasks/__init__.py`

```python
# 현재: 빈 파일
# 문제: autodiscover_tasks()가 태스크를 인식하지 못함
```

**조치**:
```python
# industries/tasks/__init__.py
from . import index_sync  # noqa: F401
```

---

### 2.3 중복 Celery autodiscover 제거

**파일**: `config/celery.py`

```python
# 현재 (Line 8-9)
app.autodiscover_tasks()
app.autodiscover_tasks(['industries'])  # 불필요한 중복
```

**조치**: Line 9 제거 (industries __init__.py 수정 후)

---

### 2.4 레거시 뉴스 크롤링 태스크 제거

**파일**: `news/tasks.py`

```python
# 전체 파일이 deprecated
@shared_task
def crawl_news_task(...):
    raise NotImplementedError(...)
```

**조치**:
- `news/tasks.py` 파일 제거
- 모든 참조를 `news.tasks.workflows.scheduled_crawl_news`로 변경

---

## 3. 단기 개선 (High Priority)

### 3.1 API 응답 표준화

**문제**: 응답 포맷이 앱마다 다름

| 위치 | 현재 패턴 |
|------|----------|
| news/views.py | `{"total_count": ..., "results": [...]}` |
| industries/views.py | `{"status": 200, "message": ..., "data": ...}` |
| core/views.py | `{"status": "accepted", "message": ...}` |

**조치**: 공통 응답 헬퍼 생성

```python
# utils/responses.py (신규)
from rest_framework.response import Response

def success_response(data, message="성공", status_code=200):
    return Response({
        "status": status_code,
        "message": message,
        "data": data,
    }, status=status_code)

def paginated_response(queryset, serializer_class, request, message="조회 성공"):
    # 페이지네이션 로직 통합
    ...

def error_response(message, status_code=400, errors=None):
    return Response({
        "status": status_code,
        "error": message,
        "details": errors,
    }, status=status_code)
```

---

### 3.2 페이지네이션 로직 통합

**문제**: 3개 이상의 views.py에서 동일한 페이지네이션 코드 반복

**조치**: 공통 유틸리티 생성

```python
# utils/pagination.py (신규)
from django.core.paginator import Paginator
from rest_framework.response import Response

def paginate_queryset(request, queryset, serializer_class, default_page_size=20):
    """공통 페이지네이션 처리"""
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", default_page_size))
    except (ValueError, TypeError):
        return None, {"error": "page와 page_size는 정수여야 합니다."}

    if page < 1:
        return None, {"error": "page는 1 이상이어야 합니다."}

    page_size = max(1, min(page_size, 100))
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)

    return {
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page,
        "page_size": page_size,
        "results": serializer_class(page_obj, many=True).data,
    }, None
```

---

### 3.3 News Serializer 중복 제거

**파일**: `news/serializers.py`

**현재**: 5개의 유사한 Serializer 존재

**조치**: BaseNewsSerializer 도입

```python
# news/serializers.py 리팩토링
class BaseNewsSerializer(serializers.ModelSerializer):
    """뉴스 기본 직렬화"""
    class Meta:
        model = News
        fields = ['news_id', 'title', 'url', 'summary', 'author',
                  'press', 'keywords', 'sentiment', 'published_at']

class NewsDetailSerializer(BaseNewsSerializer):
    """뉴스 상세 직렬화"""
    class Meta(BaseNewsSerializer.Meta):
        fields = BaseNewsSerializer.Meta.fields + ['content', 'updated_at']

class CompanyNewsSerializer(serializers.ModelSerializer):
    """기업-뉴스 관계 직렬화"""
    news = BaseNewsSerializer(read_only=True)

    class Meta:
        model = CompanyNews
        fields = ['company_id', 'created_at', 'news']
```

---

### 3.4 미등록 Celery Beat 스케줄 정리

**문제**: 정의되었지만 스케줄에 등록되지 않은 태스크들

| 태스크 | 파일 | 조치 |
|--------|------|------|
| `sync_all_reports` | companies/tasks/dart_sync.py | 스케줄 추가 |
| `sync_all_market_amount_async` | companies/tasks/kis_market_amount.py | 제거 또는 대체 |
| `calculate_all_companies_metrics` | companies/tasks/financial_metrics.py | 제거 |
| `update_all_rankings_task` | companies/tasks/rankings.py | 스케줄 추가 또는 제거 |

---

## 4. 중기 리팩토링 (Medium Priority)

### 4.1 Gemini 클라이언트 통합

**문제**: 4개 서비스에서 동일한 초기화 코드 반복

**파일들**:
- `news/services/embedding.py`
- `news/services/summarizer.py`
- `news/services/refiner.py`
- `companies/services/report_info_extractor.py`

**조치**: 베이스 클래스 생성

```python
# services/base/gemini_client.py (신규)
import logging
from django.conf import settings
from google import genai

logger = logging.getLogger(__name__)

class GeminiClientMixin:
    """Gemini API 클라이언트 공통 기능"""

    model_name: str = "gemini-2.5-flash-lite"

    def __init__(self):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.client = genai.Client(api_key=api_key)
        logger.info(f"Gemini 클라이언트 초기화: {self.model_name}")

    def truncate_text(self, text: str, max_length: int = 10000) -> str:
        """텍스트 길이 제한"""
        if len(text) > max_length:
            logger.warning(f"텍스트가 {max_length}자를 초과하여 잘림")
            return text[:max_length]
        return text

    @property
    def safety_settings(self):
        """공통 안전 설정"""
        return [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
```

---

### 4.2 보고서 처리 서비스 구조화

**문제**: 4개 파일의 책임 경계가 불명확

**현재 구조**:
```text
companies/services/
├── report_extractor.py
├── report_info_extractor.py
├── report_section_extractor.py
└── report_classifier.py
```

**조치**: 디렉토리 구조화

```text
companies/services/report_processing/
├── __init__.py           # 통합 인터페이스
├── content_extractor.py  # 본문 추출
├── info_extractor.py     # 정보 추출 (Gemini)
├── classifier.py         # 분류
└── pipeline.py           # 파이프라인 오케스트레이터
```

---

### 4.3 Industry 모델 정규화

**문제**: `induty_code`와 `kis_code` 동시 존재

**파일**: `industries/models.py`, `companies/models.py`

**조치**:
1. `Industry.induty_code` 필드 완전 제거 (DEPRECATED 상태)
2. `Company.original_ksic_code` 필드 제거
3. `Industry.kis_code`를 primary 매핑 키로 통일

```python
# 마이그레이션 계획
# 1. 데이터 검증: 모든 Company가 Industry FK 사용 확인
# 2. induty_code 필드 제거 마이그레이션
# 3. original_ksic_code 필드 제거 마이그레이션
```

---

### 4.4 DB 인덱스 최적화

**누락된 인덱스**:

```python
# companies/models.py
class Company(models.Model):
    # 추가 필요
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['market', '-created_at']),
            models.Index(fields=['is_deleted', '-updated_at']),
        ]

# news/models.py
class News(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['-published_at']),  # 단일 인덱스로 변경
            models.Index(fields=['is_deleted', '-created_at']),
        ]
```

---

### 4.5 시가총액 동기화 태스크 통합

**문제**: 동기/비동기 2가지 방식 존재

**현재**:
- `sync_all_market_amount()` - 동기, 스케줄됨
- `sync_all_market_amount_async()` - 비동기, 미사용

**조치**: 비동기 방식으로 통합

```python
# companies/tasks/kis_market_amount.py
@shared_task
def sync_all_market_amount():
    """전체 기업 시가총액 갱신 (비동기)"""
    companies = Company.objects.filter(is_deleted=False)

    for idx, company in enumerate(companies):
        countdown = idx * REQUEST_DELAY  # Rate limit 준수
        sync_market_amount.apply_async(
            args=[company.stock_code],
            countdown=countdown
        )
```

---

## 5. 장기 구조 개선 (Low Priority)

### 5.1 외부 API 클라이언트 베이스 클래스

**문제**: DART API, Naver API 등에서 비슷한 요청 처리 로직 반복

**조치**:

```python
# services/base/api_client.py (신규)
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ExternalAPIClient:
    """외부 API 클라이언트 베이스"""

    base_url: str
    timeout: int = 30

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API 요청 실패: {url} - {e}")
            raise
```

---

### 5.2 산업 매핑 서비스 통합

**현재**:
- `companies/services/industry_mapper.py`
- `companies/services/industry_mapping_rules.py`

**조치**: 단일 서비스로 병합

```python
# companies/services/industry_mapping.py
class IndustryMappingService:
    """산업 코드 매핑 통합 서비스"""

    # industry_mapping_rules.py 내용 포함
    MAPPING_RULES = {...}

    def map_ksic_to_kis(self, ksic_code: str) -> Optional[str]:
        ...

    def get_industry_for_company(self, company: Company) -> Optional[Industry]:
        ...
```

---

### 5.3 SankeyData 모델 정규화

**문제**: JSON 필드에 중복 데이터 저장

**조치**:

```python
# companies/models.py
class SankeyData(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    fiscal_year = models.IntegerField()

    # 원본 데이터만 저장
    revenue_data = models.JSONField()  # 매출 구성
    cost_data = models.JSONField()     # 비용 구조

    class Meta:
        unique_together = ('company', 'fiscal_year')

    # 시각화 데이터는 @property로 계산
    @property
    def nodes(self) -> list:
        return SankeyDataService.generate_nodes(self)

    @property
    def links(self) -> list:
        return SankeyDataService.generate_links(self)
```

---

## 6. 제거 대상 코드

### 6.1 파일 제거

| 파일 | 이유 | 조치 |
|------|------|------|
| `news/tasks.py` | Deprecated (Canvas로 대체됨) | 삭제 |
| `users/forms.py` | 빈 파일 | 삭제 |

### 6.2 필드 제거

| 모델 | 필드 | 이유 |
|------|------|------|
| `Industry` | `induty_code` | DEPRECATED 마크됨 |
| `Company` | `original_ksic_code` | 마이그레이션 검증용 (더 이상 불필요) |
| `Favorite` | `is_deleted` | 하드 삭제로 충분 |

### 6.3 중복 설정 제거

| 파일 | 위치 | 내용 |
|------|------|------|
| `config/settings.py` | Line 33 | `NAVER_CLIENT_ID` 첫 번째 정의 (Line 374에서 재정의됨) |
| `config/settings.py` | Line 86 | 중복 CORS 미들웨어 |
| `config/celery.py` | Line 9 | 중복 autodiscover_tasks |

### 6.4 미사용 태스크 제거

| 태스크 | 파일 | 이유 |
|--------|------|------|
| `crawl_news_task` | news/tasks.py | NotImplementedError 발생 |
| `sync_all_market_amount_async` | companies/tasks/kis_market_amount.py | 미사용 |
| `calculate_all_companies_metrics` | companies/tasks/financial_metrics.py | 호출되지 않음 |

---

## 7. 구현 로드맵

### Phase 1: 즉시 조치 (1-2일) ✅ 완료

- [x] CORS 미들웨어 중복 제거 (2025-01-25)
- [x] industries/tasks/__init__.py 수정 (2025-01-25)
- [x] celery.py 중복 autodiscover 제거 (2025-01-25)
- [x] news/tasks.py 레거시 파일 제거 (2025-01-25)
- [x] users/forms.py 빈 파일 제거 (2025-01-25)

### Phase 2: 단기 개선 (1주) ✅ 완료

- [x] `utils/responses.py` 생성 및 views 적용 (2025-01-25)
- [x] `utils/pagination.py` 생성 및 views 적용 (2025-01-25)
- [x] News Serializer 통합 (2025-01-25)
- [x] 미등록 Celery 스케줄 정리 - 이미 정리됨 확인 (2025-01-25)
- [x] 중복 설정값 제거 (NAVER_CLIENT_ID) (2025-01-25)

### Phase 3: 중기 리팩토링 (2-3주) ✅ 완료

- [x] GeminiClientMixin 생성 및 적용 (2025-01-25)
  - `services/base/gemini_client.py` 생성
  - `news/services/embedding.py`, `summarizer.py`, `refiner.py` 리팩토링
  - `companies/services/report_info_extractor.py` 리팩토링
  - `companies/services/report_classifier.py` 리팩토링 (추가)
- [x] 미사용 Celery 태스크 제거 (2025-01-25)
  - `sync_all_market_amount_async` 제거
  - `calculate_all_companies_metrics` 제거
- [x] DB 인덱스 최적화 마이그레이션 (2025-01-25)
  - Company 모델에 복합 인덱스 2개 추가
  - `0004_add_company_indexes.py` 마이그레이션 생성
- [~] 보고서 처리 서비스 구조화 → Phase 5로 이동 (import 경로 변경 위험)
- [~] Industry 필드 정규화 마이그레이션 → Phase 5로 이동 (데이터 마이그레이션 필요)

### Phase 4: 장기 개선 (1개월+) ✅ 완료

- [x] ExternalAPIClient 베이스 클래스 (2025-01-25)
  - `services/base/api_client.py` 생성
- [x] 산업 매핑 서비스 검토 (2025-01-25)
  - 별도 목적으로 유지 결정 (매퍼 vs 규칙)
- [~] SankeyData 모델 정규화 → Phase 5로 이동
- [~] 마이그레이션 스쿼시 → Phase 5로 이동

### Phase 5: 고위험 변경 (추후 별도 진행)

> 아래 작업들은 import 경로 변경, 데이터 마이그레이션 등 위험도가 높아 별도 검토 후 진행

- [ ] 보고서 처리 서비스 디렉토리 구조화
  - `companies/services/report_processing/` 디렉토리 생성
  - 기존 6개 파일 이동 및 import 경로 수정
- [ ] Industry 필드 정규화 마이그레이션
  - `induty_code`, `original_ksic_code` 필드 제거
  - 데이터 검증 및 마이그레이션 스크립트 필요
- [ ] SankeyData 모델 정규화
  - nodes/links 필드를 computed property로 변경
- [ ] 마이그레이션 스쿼시
  - 안정화 후 마이그레이션 파일 정리

---

## 부록: 영향받는 파일 목록

### 수정 필요

```text
config/settings.py
config/celery.py
industries/tasks/__init__.py
news/serializers.py
companies/services/*.py
news/services/*.py
*/views.py (응답 표준화)
```

### 신규 생성

```text
utils/responses.py
utils/pagination.py
services/base/gemini_client.py
services/base/api_client.py
companies/services/report_processing/__init__.py
```

### 삭제 대상

```text
news/tasks.py
users/forms.py
```

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2025-01-25 | 1.0 | 초안 작성 |
| 2025-01-25 | 1.1 | Phase 1, Phase 2 완료 |
| 2025-01-25 | 1.2 | Phase 3, Phase 4 부분 완료 (Gemini 클라이언트, API 클라이언트 베이스) |
| 2025-01-25 | 1.3 | Phase 3, Phase 4 완료, Phase 5 생성 (고위험 변경 분리) |
| 2025-01-25 | 1.4 | Docker 테스트 완료, drf-spectacular 호환성 수정 (news/serializers.py) |
