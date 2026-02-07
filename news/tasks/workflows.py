"""
뉴스 크롤링 워크플로우

Celery Canvas를 사용하여 병렬 처리 파이프라인을 구성합니다.
각 단계는 group/chord 패턴으로 병렬 실행되며, 실패한 항목은 자동으로 필터링됩니다.

워크플로우:
  1. 검색: 키워드별 병렬 검색 → 중복 제거
  2. 추출: 기사별 병렬 본문 추출 → 실패 필터링
  3. 정제+요약: 기사별 병렬 정제 및 요약 → 실패 필터링
  4. 임베딩: 기사별 병렬 임베딩 생성 → 실패 필터링
  5. 저장: PostgreSQL 저장 (순차)
  6. 클러스터링: 중복 제거 및 OpenSearch 저장 (순차)
"""

from celery import chain, chord, group, shared_task
import logging

from news.models import CrawlJob
from .search import (
    search_single_keyword_task,
    aggregate_search_results,
)
from .extraction import (
    extract_single_article_task,
    aggregate_extraction_results,
)
from .processing import (
    refine_and_summarize_single_article_task,
    aggregate_processing_results,
)
from .embedding import (
    create_single_embedding_task,
    aggregate_embedding_results,
)
from .storage import save_to_db_task
from .clustering import cluster_and_save_opensearch_task

logger = logging.getLogger(__name__)


@shared_task
def start_search_phase(keywords, max_articles_per_keyword, job_id):
    """
    검색 단계: 키워드별 병렬 검색 후 추출 단계로 전달

    처리 흐름:
    1. 각 키워드별로 병렬 검색 태스크 생성 (group)
    2. 모든 검색 완료 후 결과 집계 (chord callback)
    3. 중복 제거 후 추출 단계로 전달
    """
    logger.info(f"[Workflow] 검색 단계 시작: {len(keywords)}개 키워드")

    # 키워드별 병렬 검색 태스크 그룹 생성
    search_group = group(
        search_single_keyword_task.s(keyword, max_articles_per_keyword)
        for keyword in keywords
    )

    # 검색 완료 후 집계 → 추출 단계로 연결
    workflow = chord(search_group)(
        aggregate_search_results.s() | start_extraction_phase.s(job_id)
    )

    return workflow


@shared_task
def start_extraction_phase(articles, job_id):
    """
    추출 단계: 기사별 병렬 본문 추출 후 정제+요약 단계로 전달

    처리 흐름:
    1. 각 기사별로 병렬 본문 추출 태스크 생성 (group)
    2. 모든 추출 완료 후 결과 집계 (chord callback)
    3. 실패한 항목 제거 후 정제+요약 단계로 전달
    """
    if not articles:
        logger.warning("[Workflow] 추출할 기사가 없습니다.")
        start_processing_phase.apply_async(args=[[], job_id])
        return []

    logger.info(f"[Workflow] 추출 단계 시작: {len(articles)}개 기사")

    # 기사별 병렬 본문 추출 태스크 그룹 생성
    extraction_group = group(
        extract_single_article_task.s(article) for article in articles
    )

    # 추출 완료 후 집계 → 정제+요약 단계로 연결
    workflow = chord(extraction_group)(
        aggregate_extraction_results.s() | start_processing_phase.s(job_id)
    )

    return workflow


@shared_task
def start_processing_phase(articles, job_id):
    """
    정제+요약 단계: 기사별 병렬 정제 및 요약 후 임베딩 단계로 전달
    """
    if not articles:
        logger.warning("[Workflow] 처리할 기사가 없습니다.")
        start_embedding_phase.apply_async(args=[[], job_id])
        return []

    logger.info(f"[Workflow] 정제+요약 단계 시작: {len(articles)}개 기사")

    processing_group = group(
        refine_and_summarize_single_article_task.s(article) for article in articles
    )

    workflow = chord(processing_group)(
        aggregate_processing_results.s() | start_embedding_phase.s(job_id)
    )

    return workflow


@shared_task
def start_embedding_phase(articles, job_id):
    """
    임베딩 단계: 기사별 병렬 임베딩 생성 후 저장 단계로 전달
    """
    if not articles:
        logger.warning("[Workflow] 임베딩할 기사가 없습니다.")
        start_storage_phase.apply_async(args=[[], job_id])
        return []

    logger.info(f"[Workflow] 임베딩 단계 시작: {len(articles)}개 기사")

    embedding_group = group(
        create_single_embedding_task.s(article) for article in articles
    )

    workflow = chord(embedding_group)(
        aggregate_embedding_results.s() | start_storage_phase.s(job_id)
    )

    return workflow


@shared_task
def start_storage_phase(articles, job_id):
    """
    저장 단계: PostgreSQL 저장 후 클러스터링 단계로 전달
    """
    if not articles:
        logger.warning("[Workflow] 저장할 기사가 없습니다.")
        start_clustering_phase.apply_async(args=[[], job_id])
        return []

    logger.info(f"[Workflow] 저장 단계 시작: {len(articles)}개 기사")

    workflow = chain(
        save_to_db_task.s(articles),
        start_clustering_phase.s(job_id),
    )

    return workflow.apply_async()


@shared_task
def start_clustering_phase(articles, job_id):
    """
    클러스터링 단계: 중복 제거 및 OpenSearch 저장 후 완료 처리
    """
    if not articles:
        logger.warning("[Workflow] 클러스터링할 기사가 없습니다.")
        finalize_crawl_job.apply_async(
            args=[
                {"total_saved": 0, "duplicates_removed": 0, "opensearch_indexed": 0},
                job_id,
            ]
        )
        return []

    logger.info(f"[Workflow] 클러스터링 단계 시작: {len(articles)}개 기사")

    workflow = chain(
        cluster_and_save_opensearch_task.s(articles),
        finalize_crawl_job.s(job_id),
    )

    return workflow.apply_async()


@shared_task
def scheduled_crawl_news(keywords=None, max_articles_per_keyword=10):
    """
    뉴스 크롤링 메인 워크플로우

    Celery Beat에서 주기적으로 호출되거나 수동으로 실행할 수 있습니다.

    일반 크롤링 모드: 넓은 범위의 카테고리 키워드를 사용하여
    특정 키워드에 편향되지 않은 일반적인 뉴스를 수집합니다.
    """
    if keywords is None:
        # 기본값: 일반 크롤링용 넓은 범위 카테고리
        keywords = [
            "경제",  # 경제 일반
            "증권",  # 증권/주식
            "기업",  # 기업 뉴스
            "IT",  # IT/기술
            "기술",  # 기술 일반
            "산업",  # 산업 전반
            "무역",  # 무역/수출입
            "금융",  # 금융
        ]

    # CrawlJob 생성
    crawl_job = CrawlJob.objects.create(
        keywords=keywords,
        status="pending",
    )

    logger.info(
        f"[Workflow] CrawlJob {crawl_job.id} 생성: "
        f"키워드={keywords}, 최대 기사 수={max_articles_per_keyword}"
    )

    start_search_phase.apply_async(
        args=[keywords, max_articles_per_keyword, crawl_job.id]
    )

    logger.info(f"[Workflow] CrawlJob {crawl_job.id} 워크플로우 시작")
    return crawl_job.id


@shared_task
def finalize_crawl_job(result, job_id):
    """
    CrawlJob 완료 처리 및 통계 업데이트
    """
    try:
        crawl_job = CrawlJob.objects.get(id=job_id)

        crawl_job.total_articles = result.get("total_saved", 0) + result.get(
            "duplicates_removed", 0
        )
        crawl_job.successful_articles = result.get("total_saved", 0)
        crawl_job.failed_articles = 0
        crawl_job.save()

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
        try:
            crawl_job = CrawlJob.objects.get(id=job_id)
            crawl_job.mark_as_failed(str(e))
        except CrawlJob.DoesNotExist:
            logger.error(
                f"[Workflow] CrawlJob {job_id} 실패 처리 중에도 찾을 수 없습니다."
            )
        except Exception as inner_e:
            logger.exception(
                f"[Workflow] CrawlJob {job_id} 실패 처리 중 오류 발생: {str(inner_e)}"
            )
