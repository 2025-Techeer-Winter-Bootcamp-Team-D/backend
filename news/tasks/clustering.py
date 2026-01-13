"""
6단계: 클러스터링 + OpenSearch 저장

OpenSearch에 저장되는 항목:
- 본문(refined_content): 정제된 본문 텍스트
- 벡터 임베딩(embedding): 768차원 벡터
- 메타데이터: news_id, title, published_at

PostgreSQL에는 이미 메타데이터(요약 포함)가 저장되어 있음.
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
def cluster_and_save_opensearch_task(
    self, articles: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    DBSCAN 클러스터링 + 중복 제거 + OpenSearch 저장

    이 단계에서 OpenSearch에 저장:
    - 본문(refined_content): 벡터 검색을 위한 텍스트
    - 벡터 임베딩(embedding): 768차원 벡터
    - 메타데이터: news_id, title, published_at

    Args:
        articles: news_id, 임베딩, refined_content가 포함된 리스트

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
        embeddings = [article["embedding"] for article in articles]

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

    try:
        # 2. OpenSearch에 유지할 뉴스만 저장
        news_to_save = [
            {
                "news_id": articles[idx]["news_id"],
                "title": articles[idx].get("title", ""),
                "content": articles[idx].get("refined_content", ""),
                "content_vector": articles[idx]["embedding"],
                "published_at": articles[idx].get("published_at"),
            }
            for idx in keep_indices
            if idx < len(articles)
        ]

        if news_to_save:
            logger.info(f"[Clustering] OpenSearch 저장 시작: {len(news_to_save)}개")
            opensearch_service.save_news_vectors_batch(news_to_save)
            logger.info(f"[Clustering] OpenSearch 저장 완료")

        # 3. 중복 뉴스 소프트 삭제
        duplicate_news_ids = [
            articles[idx]["news_id"] for idx in duplicate_indices if idx < len(articles)
        ]

        if duplicate_news_ids:
            logger.info(f"[Clustering] 중복 뉴스 소프트 삭제: {len(duplicate_news_ids)}개")
            News.objects.filter(news_id__in=duplicate_news_ids).update(
                is_deleted=True, updated_at=timezone.now()
            )

        result = {
            "total_saved": len(news_to_save),
            "duplicates_removed": len(duplicate_indices),
            "opensearch_indexed": len(news_to_save),
        }

        logger.info(f"[Clustering] 완료: {result}")
        return result

    except Exception as e:
        # 재시도 가능한 오류인 경우 재시도
        if self.request.retries < self.max_retries:
            logger.warning(
                f"[Clustering] 클러스터링/저장 실패 (재시도 {self.request.retries + 1}/{self.max_retries}): {str(e)}"
            )
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
        
        # 최대 재시도 횟수 초과 시 빈 결과 반환
        logger.error(f"[Clustering] 클러스터링/저장 최종 실패: {str(e)}")
        return {"total_saved": 0, "duplicates_removed": 0, "opensearch_indexed": 0}
