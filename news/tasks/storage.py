"""
5단계: PostgreSQL 저장

PostgreSQL에는 메타데이터(제목, URL, 요약)만 저장합니다.
임베딩 벡터는 저장하지 않으며, 다음 단계(OpenSearch)로 전달됩니다.
"""

from celery import shared_task
from typing import List, Dict, Any
import logging

from news.models import News

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def save_to_db_task(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    PostgreSQL에 뉴스 메타데이터 저장

    저장 항목:
    - title: 뉴스 제목
    - url: 원본 링크 (unique)
    - summary: AI 생성 요약문
    - published_at: 발행일

    저장하지 않는 항목:
    - embedding: 벡터 임베딩 (OpenSearch에 저장)
    - refined_content: 정제된 본문 (OpenSearch에 저장)

    Args:
        articles: 요약 및 임베딩이 포함된 리스트 (임베딩은 전달용, 저장하지 않음)

    Returns:
        news_id가 추가된 리스트 (임베딩 포함, 다음 단계로 전달)
    """
    logger.info(
        f"[DB Save] PostgreSQL 저장 시작: {len(articles)}개 기사 "
        f"(메타데이터만 저장, 임베딩은 OpenSearch로 전달)"
    )

    saved_articles = []

    try:
        for idx, article in enumerate(articles, 1):
            try:
                url = article.get("link")

                # PostgreSQL에 메타데이터만 저장 (요약 포함)
                # 임베딩은 저장하지 않음 (OpenSearch에 저장)
                news, created = News.objects.get_or_create(
                    url=url,
                    defaults={
                        "title": article.get("title", ""),
                        "summary": article.get("summary", ""),  # 요약만 저장
                        "published_at": article.get("published_at"),
                    },
                )

                if not created:
                    # 기존 뉴스 업데이트
                    news.title = article.get("title", "")
                    news.summary = article.get("summary", "")
                    news.published_at = article.get("published_at")
                    news.is_deleted = False  # 소프트 삭제 복구
                    news.save()
                    logger.info(
                        f"[DB Save] [{idx}/{len(articles)}] 기존 뉴스 업데이트: news_id={news.news_id}"
                    )
                else:
                    logger.info(
                        f"[DB Save] [{idx}/{len(articles)}] 신규 뉴스 저장: news_id={news.news_id}"
                    )

                # news_id 추가
                article["news_id"] = news.news_id
                saved_articles.append(article)

            except Exception as e:
                logger.error(f"[DB Save] [{idx}/{len(articles)}] 저장 실패: {str(e)}")
                continue

        logger.info(f"[DB Save] PostgreSQL 저장 완료: {len(saved_articles)}개 성공")
        return saved_articles

    except Exception as e:
        # 재시도 가능한 오류인 경우 재시도
        if self.request.retries < self.max_retries:
            logger.warning(
                f"[DB Save] PostgreSQL 저장 실패 (재시도 {self.request.retries + 1}/{self.max_retries}): {str(e)}"
            )
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
        
        # 최대 재시도 횟수 초과 시 부분 결과라도 반환
        logger.error(f"[DB Save] PostgreSQL 저장 최종 실패: {str(e)}")
        return saved_articles
