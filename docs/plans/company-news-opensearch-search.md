# 기업 뉴스 OpenSearch 검색 기반 매핑 전환

## 개요

기존 기업 뉴스 동기화 방식을 **크롤링 기반**에서 **OpenSearch 검색 기반**으로 전환하여 중복 기능을 제거하고 비용을 절감합니다.

## 배경 및 문제점

### 현재 구조

```
[기업 뉴스 동기화 - crawl_company_news_task]
회사명 → Naver API 검색 → Jina Reader 본문 추출 → Gemini 정제 → Gemini 요약 → Gemini 메타데이터 → DB 저장

[대량 뉴스 수집 파이프라인 - scheduled_crawl_news]
키워드 → Naver API → Jina Reader → Gemini 정제 → Gemini 요약 → Gemini 임베딩 → PostgreSQL + OpenSearch 저장
```

### 문제점

1. **기능 중복**: 두 파이프라인이 거의 동일한 처리를 수행
2. **불필요한 API 비용**: 기업 뉴스 동기화마다 Gemini API 호출 (정제, 요약, 메타데이터 추출)
3. **처리 시간**: 기사당 수 초의 처리 시간 소요
4. **데이터 불일치**: 동일한 뉴스가 다른 경로로 저장될 가능성

## 제안하는 구조

```
[기업 뉴스 매핑 - 신규]
회사명 → OpenSearch 텍스트/벡터 검색 → news_id 획득 → PostgreSQL에서 News 조회 → CompanyNews 매핑
```

### 장점

| 항목 | 기존 | 신규 |
|------|------|------|
| Gemini API 호출 | 기사당 3-4회 | 0회 (또는 임베딩 1회) |
| 처리 시간 | 기사당 수 초 | 검색 쿼리 수십 ms |
| 데이터 품질 | 새로 처리 | 이미 검증된 데이터 |
| 중복 가능성 | 있음 | 없음 (동일 데이터 소스) |

## 구현 방안

### 1. OpenSearch 검색 메서드 추가

`news/services/opensearch.py`에 텍스트 기반 검색 메서드 추가:

```python
def search_news_by_keyword(
    self,
    keyword: str,
    size: int = 20,
    published_after: datetime = None,
    search_fields: list = None,
) -> list:
    """
    키워드 기반 뉴스 검색 (텍스트 매칭)

    Args:
        keyword: 검색 키워드 (예: "삼성전자")
        size: 반환할 결과 개수
        published_after: 이 날짜 이후의 뉴스만 검색
        search_fields: 검색할 필드 목록 (기본: ["title", "content"])

    Returns:
        list: 검색 결과 (news_id, title, score, published_at)
    """
```

#### 검색 전략 옵션

**A. 텍스트 매칭 (단순)**
```json
{
  "query": {
    "multi_match": {
      "query": "삼성전자",
      "fields": ["title^2", "content"],
      "type": "best_fields"
    }
  }
}
```

**B. 하이브리드 검색 (정확도 향상)**
```json
{
  "query": {
    "bool": {
      "should": [
        { "multi_match": { "query": "삼성전자", "fields": ["title^2", "content"] } },
        { "knn": { "content_vector": { "vector": [임베딩], "k": 20 } } }
      ]
    }
  }
}
```

**권장**: 초기에는 **A. 텍스트 매칭**으로 시작하고, 정확도가 부족하면 B로 확장

### 2. 기업 뉴스 매핑 서비스

`news/services/company_news_mapper.py` (신규):

```python
class CompanyNewsMapperService:
    """OpenSearch 검색 결과를 CompanyNews에 매핑하는 서비스"""

    def __init__(self):
        self.opensearch = OpenSearchService()

    def map_news_to_company(
        self,
        company: Company,
        max_news: int = 20,
        days_back: int = 30,
    ) -> tuple[int, int]:
        """
        회사에 관련된 뉴스를 검색하여 CompanyNews에 매핑

        Args:
            company: Company 모델 인스턴스
            max_news: 최대 매핑할 뉴스 수
            days_back: 검색할 기간 (일)

        Returns:
            tuple: (새로 매핑된 수, 이미 매핑된 수)
        """
        # 1. OpenSearch에서 회사명으로 검색
        results = self.opensearch.search_news_by_keyword(
            keyword=company.name,
            size=max_news,
            published_after=datetime.now() - timedelta(days=days_back),
        )

        # 2. PostgreSQL에서 News 조회 및 CompanyNews 생성
        news_ids = [r['news_id'] for r in results]
        existing_news = News.objects.filter(news_id__in=news_ids, is_deleted=False)

        created_count = 0
        existing_count = 0

        for news in existing_news:
            obj, created = CompanyNews.objects.get_or_create(
                company=company,
                news=news,
            )
            if created:
                created_count += 1
            else:
                existing_count += 1

        return created_count, existing_count
```

### 3. Celery Task 수정

`news/tasks/company_news.py` 수정:

```python
# Fallback 임계값: 검색 결과가 이 값 미만이면 기존 크롤링 사용
MIN_SEARCH_RESULTS = 3


@shared_task(bind=True)
def sync_company_news_task(self, stock_code: str, max_news: int = 20):
    """
    기업 뉴스 동기화 (OpenSearch 검색 기반 + Fallback)

    1. OpenSearch에서 회사명으로 뉴스 검색
    2. 검색 결과가 3개 미만이면 기존 크롤링 방식으로 fallback
    3. 3개 이상이면 검색 결과를 CompanyNews에 매핑
    """
    company = Company.objects.get(stock_code=stock_code)
    mapper = CompanyNewsMapperService()

    # 1단계: OpenSearch 검색 시도
    search_results = mapper.search_company_news(
        company=company,
        max_news=max_news,
    )

    # 2단계: 결과가 3개 미만이면 기존 크롤링으로 fallback
    if len(search_results) < MIN_SEARCH_RESULTS:
        logger.info(
            f"OpenSearch 검색 결과 부족 ({len(search_results)}개), "
            f"기존 크롤링으로 fallback: {company.name}"
        )
        # 기존 크롤링 태스크 호출
        return crawl_company_news_task(stock_code, max_news)

    # 3단계: 검색 결과를 CompanyNews에 매핑
    created, existing = mapper.map_news_to_company(
        company=company,
        search_results=search_results,
    )

    return {
        "company": company.name,
        "method": "opensearch",
        "search_count": len(search_results),
        "created": created,
        "existing": existing,
    }
```

### 4. API 엔드포인트 수정

`companies/views.py`의 `sync_news` 액션 수정:

- 기존: `crawl_company_news_task` 호출
- 변경: `sync_company_news_task` 호출

응답 형식은 동일하게 유지하여 API 호환성 보장

## 검색 정확도 개선 방안

### 회사명 변형 처리

```python
def get_search_keywords(company: Company) -> list[str]:
    """회사명의 검색 키워드 변형 생성"""
    keywords = [company.name]

    # 접미사 제거 버전
    for suffix in ['주식회사', '(주)', '㈜', ' Inc.', ' Corp.']:
        if company.name.endswith(suffix):
            keywords.append(company.name.replace(suffix, '').strip())

    # 영문명이 있으면 추가
    if company.english_name:
        keywords.append(company.english_name)

    return keywords
```

### 최소 관련성 점수 설정

검색 결과 중 관련성이 낮은 뉴스 필터링:

```python
MIN_RELEVANCE_SCORE = 5.0  # OpenSearch BM25 점수 기준

results = [r for r in results if r['score'] >= MIN_RELEVANCE_SCORE]
```

## 마이그레이션 계획

### Phase 1: 신규 기능 구현
1. `search_news_by_keyword` 메서드 추가
2. `CompanyNewsMapperService` 구현
3. `sync_company_news_task` 구현

### Phase 2: 테스트 및 검증
1. 몇 개 기업으로 검색 정확도 테스트
2. 기존 방식과 결과 비교
3. 최소 관련성 점수 튜닝

### Phase 3: 전환
1. API에서 새 태스크(`sync_company_news_task`) 사용
2. 기존 `crawl_company_news_task`는 fallback 전용으로 내부 호출만 허용
3. 모니터링 및 피드백 (fallback 발생률 추적)

### Phase 4: 정리
1. 기존 크롤링 로직은 fallback용으로 유지 (제거하지 않음)
2. 문서 업데이트
3. fallback 발생 빈도 모니터링 → 대량 수집 키워드 확장 검토

## 고려사항

### Fallback 전략

OpenSearch 검색 결과가 **3개 미만**이면 기존 크롤링 방식으로 자동 전환:

```
검색 결과 >= 3개  →  OpenSearch 매핑 (빠름, 비용 없음)
검색 결과 < 3개   →  기존 크롤링 (Gemini API 사용)
```

**Fallback이 발생하는 경우:**
- 신규 상장 기업 (뉴스 데이터 부족)
- 소규모 기업 (언론 노출 적음)
- 대량 수집 파이프라인 키워드 범위 밖의 기업

### 임계값 설정 근거

- `MIN_SEARCH_RESULTS = 3`: 최소한의 의미 있는 뉴스 목록을 보장
- 너무 낮으면 (1-2개) 사용자 경험 저하
- 너무 높으면 (5개 이상) 불필요한 fallback 증가
- 운영 중 모니터링 후 조정 가능

## 파일 변경 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `news/services/opensearch.py` | 수정 | `search_news_by_keyword` 메서드 추가 |
| `news/services/company_news_mapper.py` | 신규 | 매핑 서비스 |
| `news/tasks/company_news.py` | 수정 | `sync_company_news_task` 추가 |
| `companies/views.py` | 수정 | sync_news에서 새 태스크 호출 |

## 결론

이 전환을 통해:
- **Gemini API 비용 절감**: 기업 뉴스 동기화 시 API 호출 제거
- **응답 시간 개선**: 크롤링/처리 대기 없이 즉시 결과 반환
- **코드 단순화**: 중복 파이프라인 제거
- **데이터 일관성**: 단일 데이터 소스 사용
