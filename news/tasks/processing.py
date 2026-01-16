"""
본문 정제, 요약 생성 및 메타데이터 추출 태스크

기사별로 병렬 정제, 요약 및 메타데이터 추출을 수행하고 결과를 집계합니다.
"""

from celery import shared_task
from typing import List, Dict, Any
import logging

from news.services.refiner import RefineService
from news.services.summarizer import SummarizeService
from news.services.metadata_extractor import MetadataExtractorService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def refine_and_summarize_single_article_task(
    self, article: Dict[str, Any]
) -> Dict[str, Any] | None:
    """
    단일 기사의 본문 정제, Gemini 요약 생성 및 메타데이터 추출

    처리 흐름:
    1. raw_content 유효성 검증
    2. 본문 정제 완료 (광고, 메뉴 등 제거)
    3. 정제 결과 검증 (정제 실패 시 요약하지 않음)
    4. 정제된 본문 길이 검증 (최소 30자)
    5. 정제가 완료된 텍스트(refined_content)로만 요약 생성
    6. 메타데이터 추출 (저자, 언론사, 키워드)
    7. 결과 추가 및 반환

    중요: 요약은 반드시 정제가 완료된 텍스트(refined_content)를 사용합니다.
          정제가 실패하거나 완료되지 않으면 요약을 수행하지 않습니다.

    Returns:
        refined_content, summary, 메타데이터가 추가된 기사 딕셔너리 (실패 시 None)
    """
    try:
        raw_content = article.get("raw_content", "")
        url = article.get("link", "")

        # raw_content 유효성 검증
        if not raw_content:
            logger.warning(
                f"[Process] raw_content 없음: {url[:50]}..."
            )
            return None

        refiner_service = RefineService()

        # 1단계: 본문 정제 (Trafilatura + Gemini)
        # 정제가 완전히 끝난 후에만 다음 단계로 진행
        refined_content = refiner_service.get_refined_body(raw_content)

        # 정제 결과 검증: 정제가 실패하거나 결과가 없으면 요약하지 않음
        if not refined_content:
            logger.warning(
                f"[Process] 본문 정제 실패: {url[:50]}..."
            )
            return None

        # 정제된 본문 길이 검증 (너무 짧으면 요약 의미 없음)
        if len(refined_content.strip()) < 30:
            logger.warning(
                f"[Process] 정제된 본문이 너무 짧음 (30자 미만): {url[:50]}..."
            )
            return None

        # 정제 완료 확인 로그
        logger.debug(
            f"[Process] 본문 정제 완료: {len(refined_content)}자 - {url[:50]}..."
        )

        # 2단계: 정제가 완료된 텍스트로만 요약 생성
        # 정제된 텍스트(refined_content)를 사용하여 요약 진행
        summarizer_service = SummarizeService()
        summary_result = summarizer_service.get_summary_only(refined_content)
        summary_text = summary_result.get("summary", "")

        # 3단계: 메타데이터 추출 (저자, 언론사, 키워드)
        # 예외 발생 시에도 기사 처리를 계속 진행하도록 안전한 기본값 사용
        metadata = {}
        try:
            metadata_extractor = MetadataExtractorService()
            metadata = metadata_extractor.extract_all(url, refined_content)
        except Exception as e:
            logger.warning(
                f"메타데이터 추출 실패 (기사 처리는 계속 진행): {url} - {e}"
            )
            # 안전한 기본값 설정
            metadata = {"author": None, "press": None, "keywords": []}

        # 결과 추가
        article["refined_content"] = refined_content
        article["summary"] = summary_text
        article["author"] = metadata.get("author")
        article["press"] = metadata.get("press")
        article["keywords"] = metadata.get("keywords", [])

        logger.debug(f"[Process] 정제, 요약 및 메타데이터 추출 성공: {url[:50]}...")
        return article

    except Exception as e:
        # 재시도 가능한 오류인 경우 재시도
        if self.request.retries < self.max_retries:
            logger.warning(
                f"[Process] 정제/요약/메타데이터 실패 (재시도 {self.request.retries + 1}/{self.max_retries}): {article.get('link', '')[:50]}... - {str(e)}"
            )
            raise self.retry(exc=e, countdown=2**self.request.retries)

        # 최대 재시도 횟수 초과 시 None 반환
        logger.error(
            f"[Process] 정제/요약/메타데이터 최종 실패: {article.get('link', '')[:50]}... - {str(e)}"
        )
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
