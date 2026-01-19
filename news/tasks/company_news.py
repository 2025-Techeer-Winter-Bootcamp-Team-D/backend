"""
기업별 뉴스 크롤링 태스크

특정 기업과 관련된 뉴스를 수집하여 News 테이블에 저장하고
CompanyNews 매핑 테이블에 관계를 생성합니다.
"""

from celery import shared_task, group
from typing import Dict, Any
import logging

from django.db import IntegrityError
from news.services.keyword_frequency import KeywordFrequencyService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def crawl_company_news_task(
    self, stock_code: str, max_articles: int = 10
) -> Dict[str, Any]:
    """
    단일 기업의 뉴스 크롤링

    1. 회사명으로 Naver 뉴스 검색
    2. 각 기사 본문 추출 및 정제
    3. 요약 및 메타데이터 추출
    4. News 테이블에 저장 (get_or_create)
    5. CompanyNews 매핑 생성

    Args:
        stock_code: 기업 종목코드
        max_articles: 최대 크롤링 기사 수

    Returns:
        {"success": int, "failed": int, "skipped": int}
    """
    from companies.models import Company
    from news.models import News, CompanyNews
    from news.services.naver_api import NaverSearchService
    from news.services.content_extractor import ContentExtractorService
    from news.services.refiner import RefineService
    from news.services.summarizer import SummarizeService
    from news.services.metadata_extractor import MetadataExtractorService

    try:
        company = Company.objects.get(stock_code=stock_code, is_deleted=False)
    except Company.DoesNotExist:
        logger.error(f"[CompanyNews] Company not found: {stock_code}")
        return {"success": 0, "failed": 0, "skipped": 0, "error": "Company not found"}

    logger.info(
        f"[CompanyNews] Starting crawl for {stock_code} ({company.company_name})"
    )

    # 서비스 초기화
    naver_service = NaverSearchService()
    extractor = ContentExtractorService()
    refiner = RefineService()
    summarizer = SummarizeService()
    metadata_extractor = MetadataExtractorService()

    # Naver API로 회사명 검색
    articles = naver_service.search(
        company.company_name, display_count=max_articles, sort="date"
    )

    if not articles:
        logger.warning(f"[CompanyNews] No articles found for {company.company_name}")
        return {"success": 0, "failed": 0, "skipped": 0}

    logger.info(
        f"[CompanyNews] Found {len(articles)} articles for {company.company_name}"
    )

    success_count = 0
    failed_count = 0
    skipped_count = 0

    for article in articles:
        url = article.get("link")
        title = article.get("title")
        published_at = article.get("published_at")

        if not url:
            failed_count += 1
            continue

        try:
            # URL로 기존 News 확인
            existing_news = News.objects.filter(url=url).first()

            if existing_news:
                # 기존 News가 있으면 매핑만 생성
                _, mapping_created = CompanyNews.objects.get_or_create(
                    company_id=stock_code,
                    news=existing_news,
                )
                if mapping_created:
                    success_count += 1
                    logger.debug(
                        f"[CompanyNews] Mapping created for existing news: {title[:30]}..."
                    )
                else:
                    skipped_count += 1
                    logger.debug(f"[CompanyNews] Mapping already exists: {url[:50]}...")
                continue

            # 새 뉴스인 경우 크롤링 진행

            # 1. 본문 추출 (Trafilatura)
            raw_content = extractor.extract_content(url)
            if not raw_content:
                logger.warning(
                    f"[CompanyNews] Failed to extract content: {url[:50]}..."
                )
                failed_count += 1
                continue

            # 2. 본문 정제
            refined_content = refiner.get_refined_body(raw_content)
            if not refined_content or len(refined_content.strip()) < 30:
                logger.warning(
                    f"[CompanyNews] Content too short after refining: {url[:50]}..."
                )
                failed_count += 1
                continue

            # 2.5. 뉴스 본문에서 기업명이 실제로 언급되는지 확인
            if not _is_content_relevant_to_company(title, refined_content, company):
                logger.debug(
                    f"[CompanyNews] Skipping article (not relevant): {title[:30]}..."
                )
                skipped_count += 1
                continue

            # 3. 요약 생성 (감성분석 포함)
            summary_result = summarizer.get_summary_only(refined_content)
            summary = summary_result.get("summary", "")
            sentiment = summary_result.get("sentiment", "neutral")

            # 4. 메타데이터 추출
            metadata = metadata_extractor.extract_all(url, refined_content)

            # 키워드 처리: 메타데이터 키워드만 사용 (가장 중요한 키워드는 primary_keyword에 별도 저장)
            keywords = metadata.get("keywords", [])

            # 5. News 테이블에 저장 (get_or_create)
            news, news_created = News.objects.get_or_create(
                url=url,
                defaults={
                    "title": title,
                    "summary": summary,
                    "content": refined_content,
                    "author": metadata.get("author"),
                    "press": metadata.get("press"),
                    "keywords": keywords,
                    "sentiment": (
                        sentiment
                        if sentiment in ["positive", "neutral", "negative"]
                        else "neutral"
                    ),
                    "published_at": published_at,
                },
            )

            # 기존 News인데 메타데이터가 없으면 업데이트
            if not news_created:
                updated = False
                if refined_content and not news.content:
                    news.content = refined_content
                    updated = True
                if metadata.get("author") and not news.author:
                    news.author = metadata.get("author")
                    updated = True
                if metadata.get("press") and not news.press:
                    news.press = metadata.get("press")
                    updated = True
                if metadata.get("keywords") and not news.keywords:
                    news.keywords = metadata.get("keywords", [])
                    updated = True
                if (
                    sentiment
                    and sentiment in ["positive", "neutral", "negative"]
                    and not news.sentiment
                ):
                    news.sentiment = sentiment
                    updated = True
                if updated:
                    news.save()

            # 6. 키워드 빈도수 업데이트 (신규 뉴스인 경우만)
            if news_created and metadata.get("keywords"):
                try:
                    KeywordFrequencyService.update_keyword_frequencies(
                        news, metadata.get("keywords", [])
                    )
                except Exception as e:
                    logger.warning(
                        f"[CompanyNews] 키워드 빈도수 업데이트 실패 (news_id={news.news_id}): {e}"
                    )

            # 7. CompanyNews 매핑 생성
            CompanyNews.objects.get_or_create(
                company_id=stock_code,
                news=news,
            )

            success_count += 1
            logger.debug(f"[CompanyNews] Saved: {title[:30]}...")

        except IntegrityError:
            # 중복 (race condition)
            skipped_count += 1
            logger.debug(f"[CompanyNews] Duplicate (IntegrityError): {url[:50]}...")
        except Exception as e:
            failed_count += 1
            logger.error(f"[CompanyNews] Failed to process article: {e}")

            # 재시도 가능한 에러면 재시도
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=2**self.request.retries)

    result = {
        "stock_code": stock_code,
        "company_name": company.company_name,
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
    }

    logger.info(
        f"[CompanyNews] Completed {stock_code}: "
        f"success={success_count}, failed={failed_count}, skipped={skipped_count}"
    )

    return result


@shared_task
def crawl_top_companies_news_task(
    top_n: int = 100, max_articles: int = 10
) -> Dict[str, Any]:
    """
    시가총액 상위 N개 기업의 뉴스 크롤링

    리소스 효율적 운영을 위해 주요 기업만 크롤링합니다.

    Args:
        top_n: 상위 N개 기업
        max_articles: 기업당 최대 기사 수

    Returns:
        {"scheduled_companies": int}
    """
    from companies.models import Company

    # 시가총액 상위 기업 조회
    top_companies = (
        Company.objects.filter(is_deleted=False)
        .exclude(market_amount__isnull=True)
        .exclude(market_amount=0)
        .order_by("-market_amount")[:top_n]
        .values_list("stock_code", flat=True)
    )

    company_list = list(top_companies)

    if not company_list:
        logger.warning("[CompanyNews] No companies found for crawling")
        return {"scheduled_companies": 0}

    logger.info(f"[CompanyNews] Scheduling crawl for top {len(company_list)} companies")

    # 병렬 크롤링 태스크 생성
    tasks = group(
        crawl_company_news_task.s(stock_code, max_articles)
        for stock_code in company_list
    )

    # 실행
    tasks.apply_async()

    return {"scheduled_companies": len(company_list)}


@shared_task
def crawl_single_company_news_sync(
    stock_code: str, max_articles: int = 10
) -> Dict[str, Any]:
    """
    단일 기업 뉴스 크롤링 (동기 실행용)

    테스트 또는 수동 실행 시 사용합니다.
    crawl_company_news_task와 동일하지만 동기적으로 실행됩니다.

    Args:
        stock_code: 기업 종목코드
        max_articles: 최대 크롤링 기사 수

    Returns:
        {"success": int, "failed": int, "skipped": int}
    """
    # 내부적으로 같은 로직 사용
    return crawl_company_news_task(stock_code, max_articles)


# Fallback 임계값: 검색 결과가 이 값 미만이면 기존 크롤링 사용
MIN_SEARCH_RESULTS = 3


@shared_task(bind=True, max_retries=3)
def sync_company_news_task(
    self, stock_code: str, max_news: int = 20, days_back: int = 30
) -> Dict[str, Any]:
    """
    기업 뉴스 동기화 (OpenSearch 검색 기반 + Fallback)

    1. OpenSearch에서 기업명으로 관련 뉴스 검색
    2. 검색 결과가 3개 미만이면 기존 크롤링 방식으로 fallback
    3. 3개 이상이면 검색 결과를 CompanyNews에 매핑

    Args:
        stock_code: 기업 종목코드
        max_news: 최대 뉴스 수 (기본값: 20)
        days_back: 검색 기간 (일, 기본값: 30)

    Returns:
        dict: 동기화 결과
    """
    from companies.models import Company
    from news.services.company_news_mapper import CompanyNewsMapperService

    try:
        company = Company.objects.get(stock_code=stock_code, is_deleted=False)
    except Company.DoesNotExist:
        logger.error(f"[SyncCompanyNews] Company not found: {stock_code}")
        return {"success": 0, "error": "Company not found"}

    logger.info(
        f"[SyncCompanyNews] Starting sync for {stock_code} ({company.company_name})"
    )

    try:
        mapper = CompanyNewsMapperService()

        # 1단계: OpenSearch 검색 시도
        search_results = mapper.search_company_news(
            company=company,
            max_news=max_news,
            days_back=days_back,
        )

        # 2단계: 결과가 3개 미만이면 기존 크롤링으로 fallback
        if len(search_results) < MIN_SEARCH_RESULTS:
            logger.info(
                f"[SyncCompanyNews] OpenSearch 검색 결과 부족 ({len(search_results)}개), "
                f"기존 크롤링으로 fallback: {company.company_name}"
            )
            # 기존 크롤링 태스크 직접 호출 (동기) - fallback 시 5개만 크롤링
            fallback_result = crawl_company_news_task(stock_code, 5)
            fallback_result["method"] = "crawling_fallback"
            fallback_result["search_count"] = len(search_results)
            return fallback_result

        # 3단계: 검색 결과를 CompanyNews에 매핑
        created, existing = mapper.map_news_to_company(
            company=company,
            search_results=search_results,
        )

        result = {
            "stock_code": stock_code,
            "company_name": company.company_name,
            "method": "opensearch",
            "search_count": len(search_results),
            "created": created,
            "existing": existing,
        }

        logger.info(
            f"[SyncCompanyNews] Completed {stock_code}: "
            f"method=opensearch, search={len(search_results)}, "
            f"created={created}, existing={existing}"
        )

        return result

    except Exception as e:
        logger.error(f"[SyncCompanyNews] Error during sync: {e}")

        # 재시도 가능한 에러면 재시도
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=2**self.request.retries)

        return {"success": 0, "error": str(e)}


def _is_content_relevant_to_company(title: str, content: str, company) -> bool:
    """
    뉴스 제목과 본문에서 기업명이 실제로 언급되는지 확인합니다.

    Args:
        title: 뉴스 제목
        content: 뉴스 본문
        company: Company 모델 인스턴스

    Returns:
        bool: 관련성이 있으면 True, 없으면 False
    """
    # 검색할 텍스트 (제목 + 본문 앞부분)
    search_text = (title or "") + " " + (content[:2000] if content else "")

    if not search_text.strip():
        return False

    # 회사명과 변형 버전 확인
    company_name = company.company_name
    if not company_name:
        return False

    # 회사명이 텍스트에 포함되어 있는지 확인
    if company_name in search_text:
        return True

    # 접미사 제거 버전도 확인
    suffixes = ["주식회사", "(주)", "㈜", " Inc.", " Corp.", " Co., Ltd."]
    for suffix in suffixes:
        if company_name.endswith(suffix):
            clean_name = company_name[: -len(suffix)].strip()
            if clean_name and len(clean_name) >= 2 and clean_name in search_text:
                return True
        elif suffix in company_name:
            clean_name = company_name.replace(suffix, "", 1).strip()
            if clean_name and len(clean_name) >= 2 and clean_name in search_text:
                return True

    return False
