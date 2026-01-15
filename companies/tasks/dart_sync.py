# companies/tasks/dart_sync.py
"""
DART 데이터 동기화 Celery 작업
주기적으로 DART API에서 기업 정보, 재무제표, 보고서를 동기화하는 작업
"""
from celery import shared_task
from typing import List
import logging

from companies.models import Company
from companies.services.company_info import CompanyInfoService
from companies.services.financial import FinancialService
from companies.services.reports import ReportsService
from companies.services.dart_api import DartAPIError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_company_info_from_dart(self, stock_code: str):
    """
    DART에서 기업 기본 정보 동기화

    Args:
        stock_code: 종목코드
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        if not company.corp_code:
            logger.warning(f"Corp code not found for {stock_code}")
            return

        service = CompanyInfoService()
        service.sync_company_info(company)

        logger.info(f"기업 정보 동기화 완료: {stock_code}")

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except DartAPIError as e:
        logger.error(f"DART API error: {e}")
        # 60초 후 재시도
        raise self.retry(countdown=60, exc=e)
    except Exception as e:
        logger.error(f"Error syncing company info: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def sync_financial_statements(self, stock_code: str, year: int):
    """
    DART에서 재무제표 동기화

    Args:
        stock_code: 종목코드
        year: 사업연도
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        if not company.corp_code:
            logger.warning(f"Corp code not found for {stock_code}")
            return

        service = FinancialService()
        # 사업보고서(11011)만 조회 (기본값)
        statements = service.sync_financial_statements(
            company, year, sync_all_reports=False
        )

        logger.info(
            f"재무제표 동기화 완료: {stock_code} ({year}년, {len(statements)}개 보고서)"
        )

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except DartAPIError as e:
        # "조회된 데이타가 없습니다" (status: 013)는 재시도 불필요
        error_message = str(e)
        if "013" in error_message or "조회된 데이타가 없습니다" in error_message:
            logger.warning(
                f"재무제표 데이터 없음 (정상): {stock_code} ({year}년) - {e}"
            )
            return  # 재시도하지 않고 종료
        else:
            logger.error(f"DART API error: {e}")
            raise self.retry(countdown=60, exc=e)
    except Exception as e:
        logger.error(f"Error syncing financial statements: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def sync_company_reports(
    self, stock_code: str, days: int = 365, incremental: bool = True
):
    """
    DART에서 보고서 목록 동기화 (증분 동기화, 주요 공시만)

    Args:
        stock_code: 종목코드
        days: 조회할 기간 (일 단위, 기본값: 365일, incremental=True일 때는 fallback으로만 사용)
        incremental: 증분 동기화 여부 (기본값: True, 마지막 동기화 이후 보고서만)
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        if not company.corp_code:
            logger.warning(f"Corp code not found for {stock_code}")
            return

        service = ReportsService()
        # 증분 동기화 + 주요 공시만 (정기공시 + 주요사항보고)
        reports = service.sync_reports(
            company, days=days, incremental=incremental, report_types=["A", "B"]
        )

        logger.info(
            f"보고서 동기화 완료: {stock_code} ({len(reports)}건, 증분 동기화: {incremental})"
        )

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except DartAPIError as e:
        logger.error(f"DART API error: {e}")
        raise self.retry(countdown=60, exc=e)
    except Exception as e:
        logger.error(f"Error syncing reports: {e}")
        raise


@shared_task
def sync_all_company_info():
    """
    모든 기업의 기본 정보 동기화 (주기적 실행용)
    """
    companies = Company.objects.filter(is_deleted=False, corp_code__isnull=False)
    total = companies.count()
    logger.info(f"전체 기업 정보 동기화 시작: {total}개 기업")

    for company in companies:
        try:
            sync_company_info_from_dart.delay(company.stock_code)
        except Exception as e:
            logger.error(f"기업 정보 동기화 작업 등록 실패: {company.stock_code} - {e}")

    logger.info(f"전체 기업 정보 동기화 작업 등록 완료: {total}개")


@shared_task
def sync_all_reports():
    """
    모든 기업의 보고서 목록 동기화 (주기적 실행용)
    증분 동기화 + 주요 공시만 (정기공시 + 주요사항보고)
    """
    companies = Company.objects.filter(is_deleted=False, corp_code__isnull=False)
    total = companies.count()
    logger.info(
        f"전체 기업 보고서 동기화 시작: {total}개 기업 (증분 동기화, 주요 공시만)"
    )

    for company in companies:
        try:
            sync_company_reports.delay(company.stock_code, days=365, incremental=True)
        except Exception as e:
            logger.error(f"보고서 동기화 작업 등록 실패: {company.stock_code} - {e}")

    logger.info(f"전체 기업 보고서 동기화 작업 등록 완료: {total}개")

@shared_task
def sync_all_rankings():
    """
    모든 산업의 시가총액 순위 동기화 (주기적 실행용)
    """
    from companies.tasks.rankings import update_all_rankings_task
    try:
        update_all_rankings_task.delay()
        logger.info("산업 시가총액 순위 동기화 작업 등록 완료")
    except Exception as e:
        logger.exception("산업 시가총액 순위 동기화 작업 등록 실패")