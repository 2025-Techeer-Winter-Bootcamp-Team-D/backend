"""
본문 정제 및 요약 생성 태스크

기사별로 병렬 정제 및 요약을 수행하고 결과를 집계합니다.
"""

from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.refiner import RefineService
from news.services.summarizer import SummarizeService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def refine_and_summarize_single_article_task(
    self, article: Dict[str, Any]
) -> Dict[str, Any] | None:
    """
    단일 기사의 본문 정제 및 Gemini 요약 생성

    처리 흐름:
    1. raw_content 유효성 검증
    2. 본문 정제 (광고, 메뉴 등 제거)
    3. 정제된 본문 길이 검증 (최소 30자)
    4. Gemini로 요약 생성
    5. 결과 추가 및 반환

    Returns:
        refined_content와 summary가 추가된 기사 딕셔너리 (실패 시 None)
    """
    try:
        raw_content = article.get("raw_content", "")

        # raw_content 유효성 검증
        if not raw_content:
            logger.warning(
                f"[Process] raw_content 없음: {article.get('link', '')[:50]}..."
            )
            return None

        refiner_service = RefineService()
        summarizer_service = SummarizeService()

        # 1단계: 본문 정제 (Trafilatura + Gemini)
        refined_content = refiner_service.get_refined_body(raw_content)

        # 정제된 본문 길이 검증 (너무 짧으면 요약 의미 없음)
        if not refined_content or len(refined_content.strip()) < 30:
            logger.warning(
                f"[Process] 본문이 너무 짧음 (30자 미만): {article.get('link', '')[:50]}..."
            )
            return None

        # 2단계: Gemini로 요약 생성
        summary_result = summarizer_service.get_summary_only(refined_content)
        summary_text = summary_result.get("summary", "")

        # 결과 추가
        article["refined_content"] = refined_content
        article["summary"] = summary_text

        logger.debug(f"[Process] 성공: {article.get('link', '')[:50]}...")
        return article

    except Exception as e:
        # 예외 발생 시 None 반환 (다른 기사 처리는 계속 진행)
        logger.error(f"[Process] 오류 ({article.get('link', '')[:50]}...): {str(e)}")
        return None


@shared_task
def aggregate_processing_results(
    results: List[Dict[str, Any] | None],
) -> List[Dict[str, Any]]:
    """
    정제 및 요약 결과를 집계하고 실패한 항목 제거

    입력: 각 기사별 처리 결과 (성공: Dict, 실패: None)
    출력: 성공한 기사만 포함된 리스트
    """
    # None인 항목(실패한 기사) 제거
    processed_articles = [r for r in results if r is not None]
    logger.info(f"[Process] 정제 및 요약 완료: {len(processed_articles)}개 성공")
    return processed_articles
