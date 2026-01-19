"""
재무 지표 계산 Celery 태스크
"""
from celery import shared_task
import logging

from companies.models import Company, FinancialStatement
from companies.services.financial_metrics import FinancialMetricsService
from companies.services.dividend import DividendService
from companies.services.dart_api import DartAPIError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def calculate_financial_metrics_task(self, stock_code: str, fiscal_year: int):
    """
    특정 기업의 특정 연도 재무 지표 계산

    Args:
        stock_code: 종목코드
        fiscal_year: 사업연도
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        # 사업보고서 재무제표 조회
        financial_statement = FinancialStatement.objects.filter(
            company=company, fiscal_year=fiscal_year, report_code="11011"  # 사업보고서
        ).first()

        if not financial_statement:
            logger.warning(f"재무제표 없음: {stock_code} ({fiscal_year}년)")
            return

        # 재무 지표 계산
        service = FinancialMetricsService()
        service.update_financial_metrics(financial_statement)

        logger.info(f"재무 지표 계산 완료: {stock_code} ({fiscal_year}년)")

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except Exception as e:
        logger.error(f"재무 지표 계산 오류: {stock_code} - {e}")
        raise self.retry(countdown=60, exc=e)


@shared_task(bind=True, max_retries=3)
def sync_dividend_and_calculate_task(self, stock_code: str, fiscal_year: int):
    """
    배당 정보 동기화 후 재무 지표 계산

    Args:
        stock_code: 종목코드
        fiscal_year: 사업연도
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        # 1. 배당 정보 동기화
        dividend_service = DividendService()
        try:
            dividend_service.sync_dividend_info(company, fiscal_year)
        except DartAPIError as e:
            # 배당 정보가 없는 경우 (status: 013)는 경고만 출력하고 계속 진행
            error_message = str(e)
            if "013" in error_message or "조회된 데이타가 없습니다" in error_message:
                logger.info(
                    f"배당 정보 없음 (정상): {stock_code} ({fiscal_year}년) - {e}"
                )
            else:
                # 그 외 DART API 오류는 재시도
                raise

        # 2. 재무 지표 계산
        calculate_financial_metrics_task.delay(stock_code, fiscal_year)

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except DartAPIError as e:
        logger.error(f"DART API 오류: {stock_code} - {e}")
        raise self.retry(countdown=60, exc=e)
    except Exception as e:
        logger.error(f"배당 동기화 및 지표 계산 오류: {stock_code} - {e}")
        raise self.retry(countdown=60, exc=e)


@shared_task
def calculate_all_companies_metrics():
    """
    모든 기업의 최신 연도 재무 지표 계산 (주기적 실행용)
    """
    from datetime import datetime

    current_year = datetime.now().year
    companies = Company.objects.filter(is_deleted=False, corp_code__isnull=False)

    total = companies.count()
    logger.info(f"전체 기업 재무 지표 계산 시작: {total}개 기업")

    for company in companies:
        try:
            # 최근 3년 재무 지표 계산
            for year in range(current_year - 3, current_year):
                sync_dividend_and_calculate_task.delay(company.stock_code, year)
        except Exception as e:
            logger.error(f"재무 지표 계산 작업 등록 실패: {company.stock_code} - {e}")

    logger.info(f"전체 기업 재무 지표 계산 작업 등록 완료: {total}개")
