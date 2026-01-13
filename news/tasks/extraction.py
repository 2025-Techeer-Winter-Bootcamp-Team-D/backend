"""
Jina.ai 본문 추출 태스크

기사별로 병렬 본문 추출을 수행하고 결과를 집계합니다.
"""

from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.jina_api import JinaReaderService
from news.models import News

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def extract_single_article_task(self, article: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    단일 기사의 본문 추출

    처리 흐름:
    1. URL 유효성 검증
    2. DB 중복 체크 (이미 저장된 기사는 건너뜀)
    3. Jina.ai로 본문 추출
    4. 추출 결과 검증 및 반환

    Returns:
        raw_content가 추가된 기사 딕셔너리 (실패 시 None)
    """
    url = article.get("link")

    # URL 유효성 검증
    if not url:
        logger.warning(f"[Extract] URL 없음: 건너뜀")
        return None

    # DB 중복 체크: 이미 저장된 기사는 추출하지 않음
    if News.objects.filter(url=url).exists():
        logger.info(f"[Extract] 중복 URL 건너뜀: {url[:50]}...")
        return None

    try:
        # Jina.ai API로 본문 추출
        jina_service = JinaReaderService()
        raw_content = jina_service.extract_content(url)

        # 추출 결과 검증
        if not raw_content:
            logger.warning(f"[Extract] 본문 추출 실패: {url[:50]}...")
            return None

        # 성공 시 raw_content 추가하여 반환
        article["raw_content"] = raw_content
        logger.debug(f"[Extract] 성공: {url[:50]}...")
        return article

    except Exception as e:
        # 예외 발생 시 None 반환 (다른 기사 처리는 계속 진행)
        logger.error(f"[Extract] 오류 ({url[:50]}...): {str(e)}")
        return None


@shared_task
def aggregate_extraction_results(
    results: List[Dict[str, Any] | None],
) -> List[Dict[str, Any]]:
    """
    본문 추출 결과를 집계하고 실패한 항목 제거

    입력: 각 기사별 추출 결과 (성공: Dict, 실패: None)
    출력: 성공한 기사만 포함된 리스트
    """
    # None인 항목(실패한 기사) 제거
    extracted_articles = [r for r in results if r is not None]
    logger.info(
        f"[Extract] 본문 추출 완료: {len(extracted_articles)}개 성공 "
        f"(전체 {len(results)}개 중)"
    )
    return extracted_articles
