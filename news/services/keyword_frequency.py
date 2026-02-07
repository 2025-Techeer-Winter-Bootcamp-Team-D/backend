"""
키워드 빈도수 관리 서비스

뉴스 저장 시 AI 추출 키워드의 빈도수를 업데이트합니다.
"""

from django.db import transaction
from django.utils import timezone
from typing import List, Optional
from datetime import datetime as dt_datetime
import logging

from news.models import KeywordFrequency, News

logger = logging.getLogger(__name__)


class KeywordFrequencyService:
    """키워드 빈도수 관리 서비스"""

    @staticmethod
    @transaction.atomic
    def update_keyword_frequencies(
        news: News, keywords: Optional[List[str]] = None
    ) -> None:
        """
        뉴스의 키워드 빈도수를 업데이트합니다.

        Args:
            news: News 모델 인스턴스
            keywords: 키워드 리스트 (None이면 news.keywords 사용)
        """
        if keywords is None:
            keywords = news.keywords or []

        if not keywords:
            return

        published_at = news.published_at or news.created_at
        now = timezone.now()

        for keyword in keywords:
            if not isinstance(keyword, str):
                continue

            keyword = keyword.strip()
            if not keyword:
                continue

            keyword_lower = keyword.lower()

            # 키워드 빈도수 업데이트 또는 생성
            keyword_freq, created = KeywordFrequency.objects.get_or_create(
                keyword=keyword_lower,
                defaults={
                    "frequency": 1,
                    "doc_count": 1,
                    "first_seen_at": published_at,
                    "last_seen_at": published_at,
                },
            )

            if not created:
                # 기존 키워드인 경우 빈도수 증가
                keyword_freq.frequency += 1

                # 최종 등장일 업데이트
                should_update_doc_count = False
                if published_at:
                    if (
                        keyword_freq.last_seen_at is None
                        or published_at > keyword_freq.last_seen_at
                    ):
                        keyword_freq.last_seen_at = published_at
                        should_update_doc_count = True
                else:
                    if (
                        keyword_freq.last_seen_at is None
                        or keyword_freq.last_seen_at < now
                    ):
                        keyword_freq.last_seen_at = now
                        should_update_doc_count = True

                # 문서 수 증가 (최종 등장일이 업데이트된 경우만)
                # 주의: 이 로직은 완벽하지 않을 수 있음 (같은 뉴스가 여러 번 저장되면 중복 카운트 가능)
                # 더 정확한 구현을 위해서는 News-KeywordFrequency ManyToMany 관계 필요
                if should_update_doc_count:
                    keyword_freq.doc_count += 1

                keyword_freq.save()

        logger.debug(
            f"Updated keyword frequencies for news {news.news_id}: {len(keywords)} keywords"
        )

    @staticmethod
    def get_top_keywords(
        size: int = 15,
        published_after: Optional[dt_datetime] = None,
        exclude_keywords: Optional[List[str]] = None,
        min_doc_count: int = 2,
    ) -> List[dict]:
        """
        상위 키워드 빈도수를 조회합니다.

        Args:
            size: 반환할 상위 키워드 개수 (기본값: 15)
            published_after: 이 날짜 이후의 뉴스만 고려 (datetime, 선택적)
            exclude_keywords: 제외할 키워드 리스트 (선택적)
            min_doc_count: 최소 문서 수 (이 값 이상 등장한 키워드만 반환, 기본값: 2)

        Returns:
            list: 키워드 빈도수 리스트. 각 항목은 다음을 포함:
                - keyword: str (키워드)
                - count: int (빈도수)
                - doc_count: int (등장한 문서 수)
        """
        queryset = KeywordFrequency.objects.all()

        # 최소 문서 수 필터
        queryset = queryset.filter(doc_count__gte=min_doc_count)

        # 날짜 필터: published_after 이후에 등장한 키워드만
        if published_after:
            queryset = queryset.filter(last_seen_at__gte=published_after)

        # 제외 키워드 필터
        if exclude_keywords:
            exclude_set = {kw.lower().strip() for kw in exclude_keywords}
            queryset = queryset.exclude(keyword__in=exclude_set)

        # 빈도수 기준 내림차순 정렬
        queryset = queryset.order_by("-frequency", "-doc_count")[:size]

        # 결과 형식 변환
        results = []
        for kw_freq in queryset:
            results.append(
                {
                    "keyword": kw_freq.keyword,
                    "count": kw_freq.frequency,
                    "doc_count": kw_freq.doc_count,
                }
            )

        return results
