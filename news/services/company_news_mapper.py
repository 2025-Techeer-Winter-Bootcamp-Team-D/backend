"""
기업 뉴스 매핑 서비스

OpenSearch 검색 결과를 CompanyNews 테이블에 매핑합니다.
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone

from companies.models import Company
from news.models import News, CompanyNews
from news.services.opensearch import OpenSearchService

logger = logging.getLogger(__name__)


class CompanyNewsMapperService:
    """
    OpenSearch 검색 결과를 CompanyNews에 매핑하는 서비스

    - 기업명으로 OpenSearch에서 관련 뉴스 검색
    - 검색된 뉴스를 CompanyNews 테이블에 매핑
    """

    def __init__(self):
        self.opensearch = OpenSearchService()

    def search_company_news(
        self,
        company: Company,
        max_news: int = 20,
        days_back: int = 30,
        min_score: float = None,
    ) -> list:
        """
        기업명으로 OpenSearch에서 관련 뉴스를 검색합니다.

        Args:
            company: Company 모델 인스턴스
            max_news: 최대 검색 결과 수 (기본값: 20)
            days_back: 검색할 기간 (일, 기본값: 30)
            min_score: 최소 관련성 점수 (선택적)

        Returns:
            list: 검색 결과 리스트 (news_id, title, score, published_at)
        """
        # 검색 키워드 생성 (기업명 변형 처리)
        keywords = self._get_search_keywords(company)

        # 날짜 필터
        published_after = timezone.now() - timedelta(days=days_back)

        all_results = []
        seen_news_ids = set()

        # 각 키워드로 검색
        for keyword in keywords:
            results = self.opensearch.search_news_by_keyword(
                keyword=keyword,
                size=max_news,
                min_score=min_score,
                published_after=published_after,
            )

            # 중복 제거하며 결과 병합
            for result in results:
                news_id = result.get("news_id")
                if news_id and news_id not in seen_news_ids:
                    seen_news_ids.add(news_id)
                    all_results.append(result)

        # 점수 기준 정렬 후 상위 N개 반환
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_results[:max_news]

    def _get_search_keywords(self, company: Company) -> list:
        """
        회사명의 검색 키워드 변형을 생성합니다.

        Args:
            company: Company 모델 인스턴스

        Returns:
            list: 검색 키워드 리스트
        """
        keywords = []
        name = company.company_name

        if name:
            keywords.append(name)

            # 접미사 제거 버전 추가
            suffixes = ["주식회사", "(주)", "㈜", " Inc.", " Corp.", " Co., Ltd."]
            for suffix in suffixes:
                if name.endswith(suffix):
                    clean_name = name[: -len(suffix)].strip()
                    if clean_name and clean_name not in keywords:
                        keywords.append(clean_name)
                elif suffix in name:
                    clean_name = name.replace(suffix, "", 1).strip()
                    if clean_name and clean_name not in keywords:
                        keywords.append(clean_name)

        return keywords

    def map_news_to_company(
        self,
        company: Company,
        search_results: list = None,
        max_news: int = 20,
        days_back: int = 30,
    ) -> tuple:
        """
        검색 결과를 CompanyNews에 매핑합니다.

        Args:
            company: Company 모델 인스턴스
            search_results: 이미 검색된 결과 (없으면 새로 검색)
            max_news: 최대 매핑할 뉴스 수 (기본값: 20)
            days_back: 검색 기간 (일, 기본값: 30)

        Returns:
            tuple: (새로 매핑된 수, 이미 매핑된 수)
        """
        # 검색 결과가 없으면 새로 검색
        if search_results is None:
            search_results = self.search_company_news(
                company=company,
                max_news=max_news,
                days_back=days_back,
            )

        if not search_results:
            logger.info(f"No search results for company: {company.company_name}")
            return 0, 0

        # news_id 목록 추출
        news_ids = [r.get("news_id") for r in search_results if r.get("news_id")]

        if not news_ids:
            return 0, 0

        # PostgreSQL에서 News 조회 (삭제되지 않은 것만)
        existing_news = News.objects.filter(news_id__in=news_ids, is_deleted=False)

        created_count = 0
        existing_count = 0

        for news in existing_news:
            obj, created = CompanyNews.objects.get_or_create(
                company=company,
                news=news,
            )
            if created:
                created_count += 1
            else:
                existing_count += 1

        logger.info(
            f"Mapped news to {company.company_name}: "
            f"created={created_count}, existing={existing_count}"
        )

        return created_count, existing_count
