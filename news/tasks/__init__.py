"""
뉴스 크롤링 Celery 태스크 패키지
"""

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
from .workflows import scheduled_crawl_news
from .company_news import (
    crawl_company_news_task,
    crawl_top_companies_news_task,
    crawl_single_company_news_sync,
)

__all__ = [
    # Search tasks
    "search_single_keyword_task",
    "aggregate_search_results",
    # Extraction tasks
    "extract_single_article_task",
    "aggregate_extraction_results",
    # Processing tasks
    "refine_and_summarize_single_article_task",
    "aggregate_processing_results",
    # Embedding tasks
    "create_single_embedding_task",
    "aggregate_embedding_results",
    # Storage and clustering
    "save_to_db_task",
    "cluster_and_save_opensearch_task",
    # Workflow
    "scheduled_crawl_news",
    # Company news tasks
    "crawl_company_news_task",
    "crawl_top_companies_news_task",
    "crawl_single_company_news_sync",
]
