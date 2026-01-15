"""
yfinance 과거 데이터 동기화 Celery 태스크

yfinance API를 통해 과거 OHLCV 데이터를 수집하고
통합 테이블에 저장합니다.
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_stock_history_task(
    self,
    stock_code: str,
    intervals: list[str] | None = None,
):
    """
    단일 종목 히스토리 동기화 태스크

    Args:
        stock_code: 종목코드
        intervals: 동기화할 시간 단위 목록

    Returns:
        동기화 결과

    Note:
        시장 정보(KOSPI/KOSDAQ)는 Company.market 필드에서 자동으로 조회됩니다.
        yfinance 데이터는 항상 기존 데이터를 덮어씁니다.
    """
    try:
        from core.services.yfinance_service import YFinanceService

        service = YFinanceService(delay_between_requests=0.5)
        # market은 None으로 전달 -> DB에서 조회
        results = service.sync_stock_history(stock_code, intervals, None)

        return {
            "stock_code": stock_code,
            "results": results,
            "status": "completed",
        }

    except Exception as e:
        logger.exception(f"Error syncing {stock_code}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=1)
def sync_multiple_stocks_task(
    self,
    stock_codes: list[str],
    intervals: list[str] | None = None,
):
    """
    여러 종목 히스토리 동기화 태스크

    Args:
        stock_codes: 종목코드 목록
        intervals: 동기화할 시간 단위 목록

    Returns:
        동기화 결과

    Note:
        각 종목의 시장 정보는 Company.market 필드에서 자동으로 조회됩니다.
        yfinance 데이터는 항상 기존 데이터를 덮어씁니다.
    """
    try:
        from core.services.yfinance_service import YFinanceService

        service = YFinanceService(delay_between_requests=1.0)
        results = service.sync_multiple_stocks(stock_codes, intervals)

        return {
            "total_stocks": len(stock_codes),
            "results": results,
            "status": "completed",
        }

    except Exception as e:
        logger.exception(f"Error syncing multiple stocks: {e}")
        raise


@shared_task
def sync_all_favorites_history_task(
    intervals: list[str] | None = None,
):
    """
    모든 사용자의 즐겨찾기 종목 히스토리 동기화

    즐겨찾기에 등록된 종목들의 과거 데이터를 우선적으로 동기화합니다.
    yfinance 데이터는 항상 기존 데이터를 덮어씁니다.
    """
    try:
        from users.models import Favorite

        # 즐겨찾기에 등록된 고유 종목코드 목록
        stock_codes = list(
            Favorite.objects.filter(is_deleted=False)
            .values_list("stock_code", flat=True)
            .distinct()
        )

        if not stock_codes:
            logger.info("No favorites found to sync")
            return {"synced": 0, "message": "No favorites found"}

        logger.info(f"Syncing {len(stock_codes)} favorite stocks")

        # 각 종목별로 개별 태스크 실행 (병렬 처리)
        # 시장 정보는 Company.market에서 자동으로 조회됩니다
        for stock_code in stock_codes:
            sync_stock_history_task.delay(
                stock_code=stock_code,
                intervals=intervals,
            )

        return {
            "queued": len(stock_codes),
            "stock_codes": stock_codes,
            "status": "queued",
        }

    except Exception as e:
        logger.exception(f"Error syncing favorites: {e}")
        return {"error": str(e)}
