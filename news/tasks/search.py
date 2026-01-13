"""
Naver API 뉴스 검색 태스크

키워드별로 병렬 검색을 수행하고 결과를 집계합니다.
"""

from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.naver_api import NaverSearchService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def search_single_keyword_task(
    self, keyword: str, max_articles_per_keyword: int = 10
) -> List[Dict[str, Any]]:
    """
    단일 키워드로 뉴스 검색

    Returns:
        검색 결과 리스트 [{"title": "...", "link": "...", "published_at": "..."}]
    """
    try:
        # Naver API로 키워드 검색
        naver_service = NaverSearchService()
        results = naver_service.search(
            query=keyword, display_count=max_articles_per_keyword, sort="date"
        )
        logger.info(f"[Search] 키워드 '{keyword}': {len(results or [])}개 발견")
        return results or []
    except Exception as e:
        # 재시도 가능한 오류인 경우 재시도
        if self.request.retries < self.max_retries:
            logger.warning(
                f"[Search] 키워드 '{keyword}' 검색 실패 (재시도 {self.request.retries + 1}/{self.max_retries}): {str(e)}"
            )
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
        
        # 최대 재시도 횟수 초과 시 빈 리스트 반환
        logger.error(f"[Search] 키워드 '{keyword}' 검색 최종 실패: {str(e)}")
        return []


@shared_task
def aggregate_search_results(
    results: List[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    여러 키워드 검색 결과를 집계하고 중복 URL 제거

    입력: 각 키워드별 검색 결과 리스트의 리스트
    출력: 중복 제거된 단일 검색 결과 리스트
    """
    all_results = []
    seen_urls = set()

    # 각 키워드의 검색 결과를 순회하며 중복 제거
    for keyword_results in results:
        if not keyword_results:
            continue
        for article in keyword_results:
            url = article.get("link")
            # URL 기준으로 중복 제거 (여러 키워드에서 같은 기사가 검색될 수 있음)
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(article)

    logger.info(f"[Search] 검색 완료: 총 {len(all_results)}개 (중복 제거 후)")
    return all_results
