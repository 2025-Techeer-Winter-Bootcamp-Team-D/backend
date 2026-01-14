"""
뉴스 크롤링 Celery 태스크 (레거시 호환성)

이 파일은 하위 호환성을 위해 유지됩니다.
새로운 Canvas 워크플로우는 news.tasks.workflows를 사용하세요.
"""

# 새로운 Canvas 워크플로우로 리다이렉트
from news.tasks.workflows import scheduled_crawl_news

# 레거시 함수들은 병렬 처리로 변경되어 더 이상 사용되지 않음
# from news.tasks.search import search_news_task
# from news.tasks.extraction import extract_content_batch_task
# from news.tasks.processing import refine_and_summarize_task
# from news.tasks.embedding import create_embeddings_task
from news.tasks.storage import save_to_db_task
from news.tasks.clustering import cluster_and_save_opensearch_task

# 하위 호환성을 위한 레거시 함수 (deprecated)
from celery import shared_task
from news.models import CrawlJob
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def crawl_news_task(self, job_id, keywords, max_articles_per_keyword=10):
    """
    레거시 크롤링 태스크 (deprecated)

    새로운 Canvas 워크플로우를 사용하세요:
    from news.tasks.workflows import scheduled_crawl_news
    """
    logger.warning(
        f"[Deprecated] crawl_news_task는 더 이상 사용되지 않습니다. "
        f"news.tasks.workflows.scheduled_crawl_news를 사용하세요."
    )

    # 기존 로직을 유지하되, 새로운 워크플로우로 전환 권장
    # 하위 호환성을 위해 기존 코드는 tasks_old.py에 백업됨
    raise NotImplementedError(
        "이 태스크는 더 이상 사용되지 않습니다. "
        "news.tasks.workflows.scheduled_crawl_news를 사용하세요."
    )
