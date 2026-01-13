"""
벡터 임베딩 생성 태스크

기사별로 병렬 임베딩 생성을 수행하고 결과를 집계합니다.
"""

from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def create_single_embedding_task(
    self, article: Dict[str, Any]
) -> Dict[str, Any] | None:
    """
    단일 기사의 벡터 임베딩 생성

    처리 흐름:
    1. refined_content 유효성 검증
    2. Gemini Embedding API로 벡터 생성 (768차원)
    3. 결과 검증 및 반환

    Returns:
        embedding이 추가된 기사 딕셔너리 (실패 시 None)
    """
    try:
        refined_content = article.get("refined_content", "")

        # refined_content 유효성 검증
        if not refined_content:
            logger.warning(
                f"[Embedding] refined_content 없음: {article.get('link', '')[:50]}..."
            )
            return None

        # Gemini Embedding API로 벡터 생성
        embedding_service = EmbeddingService()
        result = embedding_service.get_embeddings_batch([refined_content])

        # 임베딩 결과 검증
        if not result or result[0] is None:
            logger.warning(
                f"[Embedding] 임베딩 생성 실패: {article.get('link', '')[:50]}..."
            )
            return None

        # 성공 시 embedding 추가하여 반환
        article["embedding"] = result[0]
        logger.debug(f"[Embedding] 성공: {article.get('link', '')[:50]}...")
        return article

    except Exception as e:
        # 예외 발생 시 None 반환 (다른 기사 처리는 계속 진행)
        logger.error(f"[Embedding] 오류 ({article.get('link', '')[:50]}...): {str(e)}")
        return None


@shared_task
def aggregate_embedding_results(
    results: List[Dict[str, Any] | None],
) -> List[Dict[str, Any]]:
    """
    임베딩 생성 결과를 집계하고 실패한 항목 제거

    입력: 각 기사별 임베딩 결과 (성공: Dict, 실패: None)
    출력: 성공한 기사만 포함된 리스트
    """
    # None인 항목(실패한 기사) 제거
    articles_with_embeddings = [r for r in results if r is not None]
    logger.info(f"[Embedding] 임베딩 생성 완료: {len(articles_with_embeddings)}개 성공")
    return articles_with_embeddings
