# companies/tasks/kis_market_amount.py
"""
KIS REST API를 통한 시가총액 갱신 Celery 작업
장 마감 후 전체 기업의 시가총액을 배치로 갱신
"""
import time
import logging
from celery import shared_task

from companies.models import Company
from companies.services.company_info import CompanyInfoService

logger = logging.getLogger(__name__)

# API Rate Limit 대응: 요청 간 딜레이 (초)
REQUEST_DELAY = 0.5


@shared_task(bind=True, max_retries=3)
def sync_market_amount(self, stock_code: str):
    """
    단건 시가총액 갱신

    Args:
        stock_code: 종목코드
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        service = CompanyInfoService()
        success = service.sync_market_amount_only(company)

        if success:
            logger.info(f"시가총액 갱신 완료: {stock_code}")
        else:
            logger.warning(f"시가총액 갱신 실패 (값 없음): {stock_code}")

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except Exception as e:
        logger.error(f"시가총액 갱신 중 오류 ({stock_code}): {e}")
        # 30초 후 재시도
        raise self.retry(countdown=30, exc=e)


@shared_task
def sync_all_market_amount():
    """
    전체 기업 시가총액 배치 갱신

    장 마감 후 Celery Beat에서 호출하여 모든 기업의 시가총액을 갱신
    API Rate Limit 대응을 위해 요청 간 딜레이 적용
    """
    companies = Company.objects.filter(is_deleted=False)
    total = companies.count()
    logger.info(f"전체 기업 시가총액 갱신 시작: {total}개 기업")

    success_count = 0
    fail_count = 0
    service = CompanyInfoService()

    for company in companies:
        try:
            success = service.sync_market_amount_only(company)
            if success:
                success_count += 1
            else:
                fail_count += 1
                logger.warning(f"시가총액 갱신 실패: {company.stock_code}")

            # API Rate Limit 대응
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            fail_count += 1
            logger.error(f"시가총액 갱신 중 오류 ({company.stock_code}): {e}")

    logger.info(
        f"전체 기업 시가총액 갱신 완료: 성공 {success_count}건, 실패 {fail_count}건"
    )

    return {
        "total": total,
        "success": success_count,
        "fail": fail_count,
    }


@shared_task
def sync_all_market_amount_async():
    """
    전체 기업 시가총액 비동기 배치 갱신

    각 기업별로 별도 Celery task를 생성하여 병렬 처리
    KIS API rate limit (초당 2회) 준수를 위해 countdown으로 스케줄링
    """
    companies = Company.objects.filter(is_deleted=False)
    total = companies.count()
    logger.info(f"전체 기업 시가총액 갱신 작업 등록 시작: {total}개 기업")

    for idx, company in enumerate(companies):
        try:
            # KIS API rate limit 준수: 초당 2회 제한 (0.6초 간격)
            # countdown을 사용하여 순차적으로 스케줄링
            countdown = idx * REQUEST_DELAY
            sync_market_amount.apply_async(
                args=(company.stock_code,), countdown=countdown
            )
        except Exception as e:
            logger.error(f"시가총액 갱신 작업 등록 실패: {company.stock_code} - {e}")

    logger.info(f"전체 기업 시가총액 갱신 작업 등록 완료: {total}개")
