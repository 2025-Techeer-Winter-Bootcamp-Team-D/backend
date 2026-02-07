# Celery Canvas 워크플로우 가이드

**작성일**: 2026-01-13
**버전**: 1.0.0

## 목차

1. [개요](#개요)
2. [현재 구조의 문제점](#현재-구조의-문제점)
3. [Celery Canvas란?](#celery-canvas란)
4. [개선된 아키텍처](#개선된-아키텍처)
5. [태스크 분리 설계](#태스크-분리-설계)
6. [구현 가이드](#구현-가이드)
7. [Flower 모니터링](#flower-모니터링)
8. [마이그레이션 가이드](#마이그레이션-가이드)
9. [트러블슈팅](#트러블슈팅)

---

## 개요

뉴스 크롤링 파이프라인을 **Celery Canvas**를 활용하여 **단일 Monolithic Task**에서 **분산된 Microservice Task**로 개선하는 가이드입니다.

### 개선 목표

- ✅ **Flower에서 각 단계별 진행 상황 확인**
- ✅ **실패한 단계만 선택적으로 재시도**
- ✅ **병렬 처리로 성능 향상**
- ✅ **디버깅 및 모니터링 개선**

---

## 현재 구조의 문제점

### 현재 구현 (Monolithic Task)

```python
@shared_task
def crawl_news_task(job_id, keywords, max_articles_per_keyword):
    # 1. Naver API 검색
    # 2. Jina.ai 본문 추출
    # 3. 본문 정제
    # 4. Gemini 요약 생성
    # 5. 벡터 임베딩
    # 6. PostgreSQL 저장
    # 7. 클러스터링
    # 8. OpenSearch 저장
    pass
```

### Flower에서 보이는 모습

```
✅ Active Tasks
   └─ news.tasks.crawl_news_task (1개)
      상태: RUNNING
```

**문제:**
- 현재 어느 단계(검색/추출/임베딩 등)인지 알 수 없음
- 전체 태스크가 실패하면 처음부터 다시 실행
- 부분적인 병렬 처리 불가능
- 디버깅 시 어느 단계에서 실패했는지 파악 어려움

---

## Celery Canvas란?

Celery Canvas는 **여러 태스크를 조합하여 복잡한 워크플로우를 구성**하는 기능입니다.

### Canvas의 주요 구성 요소

#### 1. **Signature (서명)**

태스크를 실행하지 않고 나중에 호출할 수 있도록 래핑합니다.

```python
# 방법 1: .s()
task1.s(arg1, arg2)

# 방법 2: .signature()
task1.signature((arg1, arg2), kwargs={'key': 'value'})
```

#### 2. **Chain (순차 실행)**

태스크를 순서대로 실행하며, 이전 태스크의 결과를 다음 태스크의 입력으로 전달합니다.

```python
from celery import chain

workflow = chain(
    task1.s(arg1),      # 결과: result1
    task2.s(),          # 입력: result1
    task3.s(),          # 입력: task2의 결과
)
workflow.apply_async()
```

**예시:**
```python
# 검색 → 추출 → 요약
chain(
    search_news_task.s(keywords),
    extract_content_task.s(),
    summarize_task.s(),
).apply_async()
```

#### 3. **Group (병렬 실행)**

여러 태스크를 동시에 실행합니다.

```python
from celery import group

parallel_tasks = group(
    task1.s(arg1),
    task2.s(arg2),
    task3.s(arg3),
)
parallel_tasks.apply_async()
```

**예시:**
```python
# 여러 기사의 본문을 동시에 추출
group(
    extract_content_task.s(url1),
    extract_content_task.s(url2),
    extract_content_task.s(url3),
).apply_async()
```

#### 4. **Chord (병렬 실행 + 결과 집계)**

여러 태스크를 병렬 실행한 후, 모든 결과를 하나의 콜백 태스크로 전달합니다.

```python
from celery import chord

workflow = chord(
    group(task1.s(), task2.s(), task3.s())  # 병렬 실행
)(callback_task.s())  # 모든 결과를 받아서 처리
```

**예시:**
```python
# 여러 기사 처리 → 결과 집계
chord(
    group(process_article.s(url) for url in urls)
)(aggregate_results.s())
```

#### 5. **Chunks (배치 처리)**

큰 작업을 여러 개의 작은 배치로 나눕니다.

```python
from celery import chunks

# 1000개 URL을 100개씩 10개 배치로 나눔
workflow = chunks(process_url.s(), urls, 100)
workflow.apply_async()
```

---

## 개선된 아키텍처

### Before: Monolithic Task

```
┌──────────────────────────────────────────┐
│     crawl_news_task (1개 태스크)          │
├──────────────────────────────────────────┤
│ 1. Naver API 검색                        │
│ 2. Jina.ai 본문 추출                     │
│ 3. 본문 정제                             │
│ 4. Gemini 요약 생성                      │
│ 5. 벡터 임베딩                           │
│ 6. PostgreSQL 저장                       │
│ 7. 클러스터링                            │
│ 8. OpenSearch 저장                       │
└──────────────────────────────────────────┘
```

**Flower에서 보임:** 1개 태스크만 표시

---

### After: Microservice Tasks (Canvas)

```
┌─────────────────────┐
│ search_news_task    │  ← 1단계: Naver API 검색
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ extract_content_    │  ← 2단계: Jina.ai 본문 추출 (병렬)
│ batch_task          │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ refine_and_         │  ← 3단계: 본문 정제 + 요약
│ summarize_task      │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ create_embeddings_  │  ← 4단계: 벡터 임베딩 생성
│ task                │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ save_to_db_task     │  ← 5단계: PostgreSQL 저장
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ cluster_and_save_   │  ← 6단계: 클러스터링 + OpenSearch
│ opensearch_task     │
└─────────────────────┘
```

**Flower에서 보임:** 6개 태스크 각각 표시 + 진행 상황 명확

---

## 태스크 분리 설계

### 1단계: Naver API 검색

**태스크:** `search_news_task`

**입력:**
- `keywords`: List[str] - 검색 키워드 리스트
- `max_articles_per_keyword`: int - 키워드당 최대 기사 수

**출력:**
- `List[Dict]` - 검색 결과 리스트

**구조:**
```python
{
    "title": "기사 제목",
    "link": "https://...",
    "description": "기사 설명",
    "published_at": "2026-01-13T10:00:00"
}
```

**주요 작업:**
- NaverSearchService로 키워드별 검색
- 병렬 검색 (ThreadPoolExecutor)
- 중복 URL 제거

---

### 2단계: 본문 추출

**태스크:** `extract_content_batch_task`

**입력:**
- 1단계의 출력 (검색 결과 리스트)

**출력:**
- `List[Dict]` - 본문이 추가된 검색 결과

**구조:**
```python
{
    "title": "기사 제목",
    "link": "https://...",
    "description": "기사 설명",
    "published_at": "2026-01-13T10:00:00",
    "raw_content": "Jina.ai로 추출한 원본 본문"  # 추가됨
}
```

**주요 작업:**
- JinaReaderService로 URL별 본문 추출
- 추출 실패한 기사는 필터링
- 최소 길이 검증

**개선 가능:** Group으로 병렬 추출
```python
from celery import chord, group

@shared_task
def extract_single_article(article):
    """단일 기사 본문 추출"""
    jina_service = JinaReaderService()
    content = jina_service.extract_content(article['link'])
    if content:
        article['raw_content'] = content
        return article
    return None

# 병렬 추출
workflow = chord(
    group(extract_single_article.s(article) for article in articles)
)(filter_null_results.s())  # None 제거
```

---

### 3단계: 본문 정제 + 요약 생성

**태스크:** `refine_and_summarize_task`

**입력:**
- 2단계의 출력 (본문이 포함된 리스트)

**출력:**
- `List[Dict]` - 정제된 본문 + 요약이 추가됨

**구조:**
```python
{
    "title": "...",
    "link": "...",
    "published_at": "...",
    "raw_content": "...",
    "refined_content": "정제된 본문",  # 추가됨
    "summary": "AI 생성 요약"  # 추가됨
}
```

**주요 작업:**
- RefineService로 본문 정제
- SummarizeService로 요약 생성 (Gemini API)
- 길이 검증 (30자 이상)

**주의사항:**
- Gemini API 할당량 제한 (무료 티어: 20건/일)
- 실패 시 재시도 로직 필요

---

### 4단계: 벡터 임베딩 생성

**태스크:** `create_embeddings_task`

**입력:**
- 3단계의 출력

**출력:**
- `List[Dict]` - 벡터 임베딩이 추가됨

**구조:**
```python
{
    "title": "...",
    "refined_content": "...",
    "summary": "...",
    "embedding": [0.123, 0.456, ...]  # 768차원 벡터 (추가됨)
}
```

**주요 작업:**
- EmbeddingService로 배치 임베딩 생성
- Gemini text-multilingual-embedding-002 모델 사용
- 768차원 벡터 생성

---

### 5단계: PostgreSQL 저장

**태스크:** `save_to_db_task`

**입력:**
- 4단계의 출력

**출력:**
- `List[Dict]` - news_id가 추가됨

**구조:**
```python
{
    "news_id": 12345,  # 추가됨 (DB에서 생성된 ID)
    "title": "...",
    "summary": "...",
    "refined_content": "...",
    "embedding": [...]
}
```

**주요 작업:**
- News 모델에 저장 (get_or_create)
- 중복 URL 처리
- 소프트 삭제 복구 (is_deleted=False)

---

### 6단계: 클러스터링 + OpenSearch 저장

**태스크:** `cluster_and_save_opensearch_task`

**입력:**
- 5단계의 출력 (news_id 포함)

**출력:**
- `Dict` - 최종 통계

**구조:**
```python
{
    "total_saved": 8,
    "duplicates_removed": 2,
    "opensearch_indexed": 8
}
```

**주요 작업:**
- NewsClusteringService로 DBSCAN 클러스터링
- 중복 제거 (대표 기사 선택)
- OpenSearchService로 벡터 저장
- 중복 뉴스 소프트 삭제 (PostgreSQL)

---

## 구현 가이드

### 파일 구조

```
news/
├── tasks/
│   ├── __init__.py
│   ├── search.py         # 1단계: 검색
│   ├── extraction.py     # 2단계: 본문 추출
│   ├── processing.py     # 3단계: 정제 + 요약
│   ├── embedding.py      # 4단계: 임베딩
│   ├── storage.py        # 5단계: DB 저장
│   ├── clustering.py     # 6단계: 클러스터링
│   └── workflows.py      # 워크플로우 정의
```

### 1. 태스크 구현

#### `news/tasks/search.py`

```python
"""
1단계: Naver API 뉴스 검색
"""
from celery import shared_task
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import logging

from news.services.naver_api import NaverSearchService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def search_news_task(self, keywords: List[str], max_articles_per_keyword: int = 10) -> List[Dict[str, Any]]:
    """
    Naver API로 뉴스 검색

    Args:
        keywords: 검색 키워드 리스트
        max_articles_per_keyword: 키워드당 최대 기사 수

    Returns:
        검색 결과 리스트 [{"title": "...", "link": "...", "published_at": "..."}]
    """
    logger.info(f"[Search] 검색 시작: {len(keywords)}개 키워드")

    naver_service = NaverSearchService()
    all_results = []
    seen_urls = set()

    def search_keyword(keyword: str) -> List[Dict[str, Any]]:
        """키워드별 검색"""
        try:
            results = naver_service.search(
                query=keyword,
                display_count=max_articles_per_keyword,
                sort="date"
            )
            logger.info(f"[Search] 키워드 '{keyword}': {len(results or [])}개 발견")
            return results or []
        except Exception as e:
            logger.error(f"[Search] 키워드 '{keyword}' 검색 실패: {str(e)}")
            return []

    # 병렬 검색
    max_workers = min(len(keywords), 4)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_keyword = {
            executor.submit(search_keyword, keyword): keyword
            for keyword in keywords
        }

        for future in as_completed(future_to_keyword):
            results = future.result()
            for article in results:
                url = article.get("link")
                # 중복 URL 제거
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(article)

    logger.info(f"[Search] 검색 완료: 총 {len(all_results)}개 (중복 제거 후)")
    return all_results
```

#### `news/tasks/extraction.py`

```python
"""
2단계: Jina.ai로 본문 추출
"""
from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.jina_api import JinaReaderService
from news.models import News

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def extract_content_batch_task(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Jina.ai로 본문 추출

    Args:
        articles: 검색 결과 리스트

    Returns:
        본문이 추가된 리스트
    """
    logger.info(f"[Extract] 본문 추출 시작: {len(articles)}개 기사")

    jina_service = JinaReaderService()
    extracted_articles = []

    for idx, article in enumerate(articles, 1):
        url = article.get("link")

        if not url:
            logger.warning(f"[Extract] URL 없음: 건너뜀")
            continue

        # DB 중복 체크
        if News.objects.filter(url=url).exists():
            logger.info(f"[Extract] 중복 URL 건너뜀: {url[:50]}...")
            continue

        try:
            # 본문 추출
            raw_content = jina_service.extract_content(url)

            if not raw_content:
                logger.warning(f"[Extract] [{idx}/{len(articles)}] 본문 추출 실패: {url[:50]}...")
                continue

            article['raw_content'] = raw_content
            extracted_articles.append(article)
            logger.debug(f"[Extract] [{idx}/{len(articles)}] 성공: {url[:50]}...")

        except Exception as e:
            logger.error(f"[Extract] [{idx}/{len(articles)}] 오류: {str(e)}")
            continue

    logger.info(f"[Extract] 본문 추출 완료: {len(extracted_articles)}개 성공")
    return extracted_articles
```

#### `news/tasks/processing.py`

```python
"""
3단계: 본문 정제 + AI 요약 생성
"""
from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.refiner import RefineService
from news.services.summarizer import SummarizeService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def refine_and_summarize_task(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    본문 정제 + Gemini 요약 생성

    Args:
        articles: 본문이 포함된 리스트

    Returns:
        정제된 본문 + 요약이 추가된 리스트
    """
    logger.info(f"[Process] 정제 및 요약 시작: {len(articles)}개 기사")

    refiner_service = RefineService()
    summarizer_service = SummarizeService()
    processed_articles = []

    for idx, article in enumerate(articles, 1):
        try:
            raw_content = article.get('raw_content', '')

            # 본문 정제
            refined_content = refiner_service.get_refined_body(raw_content)

            # 최소 길이 검증
            if not refined_content or len(refined_content.strip()) < 30:
                logger.warning(
                    f"[Process] [{idx}/{len(articles)}] 본문이 너무 짧음 (30자 미만): "
                    f"{article.get('link', '')[:50]}..."
                )
                continue

            # 요약 생성
            summary_result = summarizer_service.get_summary_only(refined_content)
            summary_text = summary_result.get("summary", "")

            article['refined_content'] = refined_content
            article['summary'] = summary_text
            processed_articles.append(article)

            logger.debug(f"[Process] [{idx}/{len(articles)}] 성공")

        except Exception as e:
            logger.error(f"[Process] [{idx}/{len(articles)}] 오류: {str(e)}")
            continue

    logger.info(f"[Process] 정제 및 요약 완료: {len(processed_articles)}개 성공")
    return processed_articles
```

#### `news/tasks/embedding.py`

```python
"""
4단계: 벡터 임베딩 생성
"""
from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def create_embeddings_task(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Gemini로 벡터 임베딩 생성

    Args:
        articles: 정제된 본문이 포함된 리스트

    Returns:
        벡터 임베딩이 추가된 리스트
    """
    logger.info(f"[Embedding] 임베딩 생성 시작: {len(articles)}개 기사")

    embedding_service = EmbeddingService()

    # 배치로 임베딩 생성
    texts = [article['refined_content'] for article in articles]
    embeddings = embedding_service.get_embeddings_batch(texts)

    if not embeddings or len(embeddings) != len(articles):
        logger.error(f"[Embedding] 임베딩 생성 실패: 예상={len(articles)}, 실제={len(embeddings or [])}")
        raise ValueError("임베딩 생성 실패")

    # 임베딩 추가
    articles_with_embeddings = []
    for article, embedding in zip(articles, embeddings):
        if embedding is None:
            logger.warning(f"[Embedding] 임베딩 None: {article.get('link', '')[:50]}...")
            continue

        article['embedding'] = embedding
        articles_with_embeddings.append(article)

    logger.info(f"[Embedding] 임베딩 생성 완료: {len(articles_with_embeddings)}개 성공")
    return articles_with_embeddings
```

#### `news/tasks/storage.py`

```python
"""
5단계: PostgreSQL 저장
"""
from celery import shared_task
from django.utils import timezone
from typing import List, Dict, Any
import logging

from news.models import News

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def save_to_db_task(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    PostgreSQL에 뉴스 저장

    Args:
        articles: 임베딩이 포함된 리스트

    Returns:
        news_id가 추가된 리스트
    """
    logger.info(f"[DB Save] PostgreSQL 저장 시작: {len(articles)}개 기사")

    saved_articles = []

    for idx, article in enumerate(articles, 1):
        try:
            url = article.get('link')

            # get_or_create로 중복 처리
            news, created = News.objects.get_or_create(
                url=url,
                defaults={
                    "title": article.get("title", ""),
                    "summary": article.get("summary", ""),
                    "published_at": article.get("published_at"),
                }
            )

            if not created:
                # 기존 뉴스 업데이트
                news.title = article.get("title", "")
                news.summary = article.get("summary", "")
                news.published_at = article.get("published_at")
                news.is_deleted = False  # 소프트 삭제 복구
                news.save()
                logger.info(f"[DB Save] [{idx}/{len(articles)}] 기존 뉴스 업데이트: news_id={news.news_id}")
            else:
                logger.info(f"[DB Save] [{idx}/{len(articles)}] 신규 뉴스 저장: news_id={news.news_id}")

            # news_id 추가
            article['news_id'] = news.news_id
            saved_articles.append(article)

        except Exception as e:
            logger.error(f"[DB Save] [{idx}/{len(articles)}] 저장 실패: {str(e)}")
            continue

    logger.info(f"[DB Save] PostgreSQL 저장 완료: {len(saved_articles)}개 성공")
    return saved_articles
```

#### `news/tasks/clustering.py`

```python
"""
6단계: 클러스터링 + OpenSearch 저장
"""
from celery import shared_task
from django.utils import timezone
from typing import List, Dict, Any
import logging

from news.utils.clustering import NewsClusteringService
from news.services.opensearch import OpenSearchService
from news.models import News

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def cluster_and_save_opensearch_task(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    DBSCAN 클러스터링 + 중복 제거 + OpenSearch 저장

    Args:
        articles: news_id와 임베딩이 포함된 리스트

    Returns:
        처리 통계
    """
    logger.info(f"[Clustering] 클러스터링 시작: {len(articles)}개 기사")

    if not articles:
        logger.warning("[Clustering] 처리할 기사가 없습니다.")
        return {"total_saved": 0, "duplicates_removed": 0, "opensearch_indexed": 0}

    clustering_service = NewsClusteringService(eps=0.1, min_samples=2)
    opensearch_service = OpenSearchService()

    # 1. 클러스터링 (단일 기사는 건너뜀)
    if len(articles) > 1:
        # 임베딩 추출
        embeddings = [article['embedding'] for article in articles]

        # DBSCAN 클러스터링
        labels = clustering_service.cluster_news(embeddings)

        # 중복 제거 (대표 기사 선택)
        news_items = [
            {
                "index": idx,
                "published_at": article.get("published_at"),
                "content_length": len(article.get("refined_content", "")),
            }
            for idx, article in enumerate(articles)
        ]

        keep_indices, duplicate_indices = clustering_service.deduplicate_by_cluster(
            labels, news_items, strategy="latest_longest"
        )

        logger.info(
            f"[Clustering] 클러스터링 완료: "
            f"유지={len(keep_indices)}개, 제거={len(duplicate_indices)}개"
        )
    else:
        # 단일 기사는 클러스터링 건너뜀
        keep_indices = [0]
        duplicate_indices = []
        logger.info("[Clustering] 단일 기사: 클러스터링 건너뜀")

    # 2. OpenSearch에 유지할 뉴스만 저장
    news_to_save = [
        {
            "news_id": articles[idx]["news_id"],
            "title": articles[idx].get("title", ""),
            "content": articles[idx].get("refined_content", ""),
            "content_vector": articles[idx]["embedding"],
            "published_at": articles[idx].get("published_at"),
        }
        for idx in keep_indices if idx < len(articles)
    ]

    if news_to_save:
        logger.info(f"[Clustering] OpenSearch 저장 시작: {len(news_to_save)}개")
        opensearch_service.save_news_vectors_batch(news_to_save)
        logger.info(f"[Clustering] OpenSearch 저장 완료")

    # 3. 중복 뉴스 소프트 삭제
    duplicate_news_ids = [
        articles[idx]["news_id"]
        for idx in duplicate_indices if idx < len(articles)
    ]

    if duplicate_news_ids:
        logger.info(f"[Clustering] 중복 뉴스 소프트 삭제: {len(duplicate_news_ids)}개")
        News.objects.filter(news_id__in=duplicate_news_ids).update(
            is_deleted=True,
            updated_at=timezone.now()
        )

    result = {
        "total_saved": len(news_to_save),
        "duplicates_removed": len(duplicate_indices),
        "opensearch_indexed": len(news_to_save),
    }

    logger.info(f"[Clustering] 완료: {result}")
    return result
```

### 2. 워크플로우 구성

#### `news/tasks/workflows.py`

```python
"""
Celery Canvas 워크플로우 정의
"""
from celery import chain, shared_task
import logging

from news.models import CrawlJob
from .search import search_news_task
from .extraction import extract_content_batch_task
from .processing import refine_and_summarize_task
from .embedding import create_embeddings_task
from .storage import save_to_db_task
from .clustering import cluster_and_save_opensearch_task

logger = logging.getLogger(__name__)


@shared_task
def scheduled_crawl_news(keywords=None, max_articles_per_keyword=10):
    """
    Celery Beat에서 호출되는 메인 워크플로우

    Args:
        keywords: 검색 키워드 리스트 (None이면 기본값 사용)
        max_articles_per_keyword: 키워드당 최대 기사 수

    Returns:
        CrawlJob ID
    """
    if keywords is None:
        keywords = ["AI", "반도체", "삼성전자", "SK하이닉스"]

    # CrawlJob 생성
    crawl_job = CrawlJob.objects.create(
        keywords=keywords,
        status="pending",
    )

    logger.info(
        f"[Workflow] CrawlJob {crawl_job.id} 생성: "
        f"키워드={keywords}, 최대 기사 수={max_articles_per_keyword}"
    )

    # Chain으로 워크플로우 구성 (순차 실행)
    workflow = chain(
        search_news_task.s(keywords, max_articles_per_keyword),
        extract_content_batch_task.s(),
        refine_and_summarize_task.s(),
        create_embeddings_task.s(),
        save_to_db_task.s(),
        cluster_and_save_opensearch_task.s(),
        finalize_crawl_job.s(crawl_job.id),  # 마지막 콜백
    )

    # 워크플로우 실행
    workflow.apply_async()

    logger.info(f"[Workflow] CrawlJob {crawl_job.id} 워크플로우 시작")
    return crawl_job.id


@shared_task
def finalize_crawl_job(result, job_id):
    """
    CrawlJob 완료 처리

    Args:
        result: 이전 태스크(cluster_and_save_opensearch_task)의 결과
        job_id: CrawlJob ID
    """
    try:
        crawl_job = CrawlJob.objects.get(id=job_id)

        # 통계 업데이트
        crawl_job.total_articles = result.get("total_saved", 0) + result.get("duplicates_removed", 0)
        crawl_job.successful_articles = result.get("total_saved", 0)
        crawl_job.failed_articles = 0  # 실패는 중간 태스크에서 처리됨
        crawl_job.save()

        # 완료 처리
        crawl_job.mark_as_completed()

        logger.info(
            f"[Workflow] CrawlJob {job_id} 완료: "
            f"성공={crawl_job.successful_articles}, "
            f"중복={result.get('duplicates_removed', 0)}"
        )

    except CrawlJob.DoesNotExist:
        logger.error(f"[Workflow] CrawlJob {job_id}를 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"[Workflow] CrawlJob {job_id} 완료 처리 실패: {str(e)}")
```

### 3. 패키지 초기화

#### `news/tasks/__init__.py`

```python
"""
뉴스 크롤링 Celery 태스크 패키지
"""
from .search import search_news_task
from .extraction import extract_content_batch_task
from .processing import refine_and_summarize_task
from .embedding import create_embeddings_task
from .storage import save_to_db_task
from .clustering import cluster_and_save_opensearch_task
from .workflows import scheduled_crawl_news

__all__ = [
    "search_news_task",
    "extract_content_batch_task",
    "refine_and_summarize_task",
    "create_embeddings_task",
    "save_to_db_task",
    "cluster_and_save_opensearch_task",
    "scheduled_crawl_news",
]
```

---

## Flower 모니터링

### Flower에서 볼 수 있는 정보

Flower (http://localhost:5555)에 접속하면 다음과 같이 표시됩니다:

#### **Tasks 탭**

```
✅ Active (실행 중)
   ├─ news.tasks.search.search_news_task (완료)
   ├─ news.tasks.extraction.extract_content_batch_task (완료)
   ├─ news.tasks.processing.refine_and_summarize_task (완료)
   ├─ news.tasks.embedding.create_embeddings_task (실행 중)  ← 현재 여기!
   ├─ news.tasks.storage.save_to_db_task (대기 중)
   └─ news.tasks.clustering.cluster_and_save_opensearch_task (대기 중)

📊 Succeeded (성공)
   ├─ news.tasks.search.search_news_task (3건)
   ├─ news.tasks.extraction.extract_content_batch_task (3건)
   └─ ...

❌ Failed (실패)
   └─ news.tasks.processing.refine_and_summarize_task (1건)
      실패 원인: Gemini API quota exceeded
```

#### **Workers 탭**

```
Worker: celery@celery-worker
Status: ✅ Online
Processed: 24 tasks

Active Tasks:
   └─ news.tasks.embedding.create_embeddings_task
      Started: 2026-01-13 15:30:45
      Runtime: 5.3s
```

#### **Monitor 탭**

실시간 그래프로 확인:
- 초당 처리된 태스크 수
- 성공/실패 비율
- Worker CPU/메모리 사용률

---

## 마이그레이션 가이드

### 단계별 마이그레이션

#### **1단계: 새 태스크 파일 생성**

```bash
mkdir -p news/tasks
touch news/tasks/__init__.py
touch news/tasks/search.py
touch news/tasks/extraction.py
touch news/tasks/processing.py
touch news/tasks/embedding.py
touch news/tasks/storage.py
touch news/tasks/clustering.py
touch news/tasks/workflows.py
```

#### **2단계: 기존 `news/tasks.py` 백업**

```bash
cp news/tasks.py news/tasks_old.py
```

#### **3단계: 새 태스크 구현**

위의 "구현 가이드" 섹션의 코드를 각 파일에 작성합니다.

#### **4단계: Celery Beat 설정 업데이트**

`config/settings.py` 수정:

```python
# Celery Beat Schedule
CELERY_BEAT_SCHEDULE = {
    "crawl-news-every-3-hours": {
        "task": "news.tasks.workflows.scheduled_crawl_news",  # 변경됨
        "schedule": 3 * 60 * 60,
        "kwargs": {
            "keywords": ["AI", "반도체", "삼성전자", "SK하이닉스"],
            "max_articles_per_keyword": 10,
        },
    },
}
```

#### **5단계: Celery Worker 재시작**

```bash
# Docker Compose 환경
docker compose restart celery-worker celery-beat

# 로그 확인
docker compose logs -f celery-worker celery-beat
```

#### **6단계: 테스트**

```bash
# Django 셸에서 수동 실행
docker compose exec app python manage.py shell

>>> from news.tasks.workflows import scheduled_crawl_news
>>> result = scheduled_crawl_news.delay()
>>> print(result.id)  # Task ID 출력
```

Flower에서 진행 상황 확인:
```
http://localhost:5555
```

#### **7단계: 검증**

1. **Flower에서 6개 태스크가 순차적으로 실행되는지 확인**
2. **PostgreSQL에서 뉴스 저장 확인**
   ```bash
   docker compose exec db psql -U admin -d stock_db -c "SELECT COUNT(*) FROM news WHERE is_deleted=false;"
   ```
3. **OpenSearch에서 벡터 저장 확인**
   ```bash
   docker compose exec opensearch curl "http://localhost:9200/news_vectors/_count"
   ```

#### **8단계: 기존 파일 삭제 (선택)**

검증이 완료되면:
```bash
rm news/tasks_old.py
```

---

## 트러블슈팅

### 문제 1: 태스크가 Flower에 나타나지 않음

**증상:**
- Celery Worker는 실행 중
- Flower는 접속 가능
- 하지만 태스크가 표시되지 않음

**원인:**
- Celery Worker가 새 태스크를 인식하지 못함

**해결:**
```bash
# Worker 재시작
docker compose restart celery-worker

# 로그 확인
docker compose logs -f celery-worker

# 다음과 같은 로그가 보여야 함:
# [tasks]
#   . news.tasks.search.search_news_task
#   . news.tasks.extraction.extract_content_batch_task
#   ...
```

---

### 문제 2: Chain 중간에 태스크가 실패

**증상:**
- `refine_and_summarize_task`에서 실패
- 이후 태스크(`create_embeddings_task`, `save_to_db_task` 등)가 실행되지 않음

**원인:**
- Chain은 중간 태스크가 실패하면 전체 워크플로우 중단

**해결 1: 에러 처리 추가**

```python
@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def refine_and_summarize_task(self, articles):
    try:
        # 기존 로직
        ...
    except Exception as e:
        logger.error(f"[Process] 오류: {str(e)}")
        # 빈 리스트 반환 (체인 계속 진행)
        return []
```

**해결 2: Chord 사용**

각 기사를 독립적으로 처리:

```python
from celery import chord, group

@shared_task
def process_single_article(article):
    """단일 기사 처리"""
    try:
        # 정제 + 요약
        ...
        return article
    except:
        return None

# 병렬 처리 + 실패 무시
workflow = chord(
    group(process_single_article.s(article) for article in articles)
)(filter_null_and_continue.s())
```

---

### 문제 3: Gemini API 할당량 초과

**증상:**
- `refine_and_summarize_task`에서 `quota exceeded` 에러
- 일부 기사만 처리되고 중단

**원인:**
- Gemini API 무료 티어 제한 (20건/일)

**해결 1: 재시도 간격 설정**

```python
from celery.exceptions import Retry

@shared_task(bind=True, max_retries=5)
def refine_and_summarize_task(self, articles):
    try:
        # 요약 생성
        summary = summarizer_service.get_summary_only(content)
    except Exception as e:
        if "quota" in str(e).lower():
            # 할당량 초과 시 1시간 후 재시도
            logger.warning("[Process] Gemini API 할당량 초과: 1시간 후 재시도")
            raise self.retry(exc=e, countdown=3600)
        else:
            raise
```

**해결 2: 배치 크기 제한**

```python
# 하루 최대 15개 기사만 처리
MAX_DAILY_ARTICLES = 15

@shared_task
def refine_and_summarize_task(self, articles):
    # 배치 크기 제한
    limited_articles = articles[:MAX_DAILY_ARTICLES]
    logger.info(f"[Process] 처리 제한: {len(limited_articles)}/{len(articles)}개")

    # 처리
    ...
```

---

### 문제 4: Redis 메모리 부족

**증상:**
- 큰 데이터(임베딩 벡터)를 전달할 때 Redis 메모리 초과
- `OOM command not allowed when used memory > 'maxmemory'`

**원인:**
- Chain으로 큰 데이터를 계속 전달하면 Redis에 쌓임

**해결: 데이터베이스에 중간 결과 저장**

```python
from news.models import CrawlJobCache

@shared_task
def create_embeddings_task(self, articles):
    # 임베딩 생성
    ...

    # Redis 대신 PostgreSQL에 임시 저장
    cache = CrawlJobCache.objects.create(
        job_id=job_id,
        data=articles  # JSONField
    )

    # 다음 태스크에는 cache_id만 전달
    return cache.id

@shared_task
def save_to_db_task(self, cache_id):
    # PostgreSQL에서 데이터 로드
    cache = CrawlJobCache.objects.get(id=cache_id)
    articles = cache.data

    # 처리
    ...

    # 캐시 삭제
    cache.delete()
```

---

### 문제 5: Flower에서 Task 세부 정보가 안 보임

**증상:**
- Flower에서 태스크는 표시되지만 인자나 결과가 보이지 않음

**원인:**
- Celery Result Backend가 설정되지 않음

**해결:**

`config/settings.py`:
```python
CELERY_RESULT_BACKEND = "redis://redis:6379/0"
CELERY_RESULT_EXTENDED = True  # 추가
CELERY_TASK_TRACK_STARTED = True  # 추가
```

Worker 재시작:
```bash
docker compose restart celery-worker
```

---

## 추가 최적화

### 1. 병렬 처리 (Group)

본문 추출을 병렬로 처리:

```python
from celery import group, chord

@shared_task
def extract_single_content(article):
    """단일 기사 본문 추출"""
    jina_service = JinaReaderService()
    content = jina_service.extract_content(article['link'])
    if content:
        article['raw_content'] = content
        return article
    return None

@shared_task
def filter_null_results(results):
    """None 제거"""
    return [r for r in results if r is not None]

# 워크플로우
workflow = chain(
    search_news_task.s(keywords, max_articles_per_keyword),

    # 병렬 본문 추출
    lambda articles: chord(
        group(extract_single_content.s(a) for a in articles)
    )(filter_null_results.s()),

    refine_and_summarize_task.s(),
    # ... 나머지
)
```

### 2. Chunks (대용량 처리)

수백 개의 기사를 배치로 나눔:

```python
from celery import chunks

# 100개씩 배치 처리
workflow = chunks(
    extract_single_content.s(),
    articles,
    100  # 배치 크기
)
```

### 3. 우선순위 설정

중요한 태스크를 먼저 처리:

```python
# 높은 우선순위
search_news_task.apply_async(
    args=[keywords, max_articles],
    priority=9  # 0-9, 9가 가장 높음
)

# 낮은 우선순위
cleanup_task.apply_async(priority=0)
```

---

## 참고 문서

- [Celery 공식 문서 - Canvas](https://docs.celeryproject.org/en/stable/userguide/canvas.html)
- [Flower 문서](https://flower.readthedocs.io/en/latest/)
- [뉴스 크롤링 구현 현황](../plans/news-crawling-implementation-status.md)
- [프로젝트 가이드](../../CLAUDE.md)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-01-13 | 1.0.0 | 초안 작성 |
