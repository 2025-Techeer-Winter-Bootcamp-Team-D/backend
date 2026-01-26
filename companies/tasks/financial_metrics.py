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


@shared_task(bind=True)
def recalculate_all_financial_metrics_task(self, report_code: str = "11011"):
    """
    모든 재무제표의 재무 지표를 재계산

    공식 변경 등으로 기존 데이터를 일괄 재계산할 때 사용합니다.

    Args:
        report_code: 보고서 코드 (기본: 11011 사업보고서)

    Returns:
        dict: 처리 결과 통계
    """
    service = FinancialMetricsService()

    # 해당 보고서 코드의 모든 재무제표 조회
    statements = FinancialStatement.objects.filter(
        report_code=report_code,
        company__is_deleted=False,
    ).select_related("company")

    total = statements.count()
    success = 0
    failed = 0
    errors = []

    logger.info(f"전체 재무 지표 재계산 시작: {total}건 (report_code={report_code})")

    for fs in statements:
        try:
            service.update_financial_metrics(fs)
            success += 1

            if success % 100 == 0:
                logger.info(f"재계산 진행 중: {success}/{total}")

        except Exception as e:
            failed += 1
            error_msg = f"{fs.company.stock_code} ({fs.fiscal_year}): {e}"
            errors.append(error_msg)
            logger.error(f"재계산 실패: {error_msg}")

    result = {
        "total": total,
        "success": success,
        "failed": failed,
        "errors": errors[:10],  # 처음 10개 오류만 반환
    }

    logger.info(
        f"전체 재무 지표 재계산 완료: 성공 {success}건, 실패 {failed}건 / 총 {total}건"
    )

    return result
