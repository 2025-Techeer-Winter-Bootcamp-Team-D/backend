"""
Continuous Aggregate → 통합 테이블 동기화 Celery 태스크

내부용 Continuous Aggregate (_cagg_*)에서 집계된 데이터를
외부 조회용 통합 테이블 (stock_prices_*)로 주기적으로 동기화합니다.
"""

import logging
from celery import shared_task
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def sync_cagg_to_prices_1m(self):
    """
    1분봉 Continuous Aggregate → 통합 테이블 동기화
    30초마다 실행 권장
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stock_prices_1m 
                    (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
                SELECT 
                    bucket, 
                    stock_code, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume, 
                    amount, 
                    trade_count, 
                    'realtime', 
                    CURRENT_TIMESTAMP
                FROM _cagg_1m
                WHERE bucket >= NOW() - INTERVAL '10 minutes'
                ON CONFLICT (stock_code, bucket) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    trade_count = EXCLUDED.trade_count,
                    source = 'realtime',
                    updated_at = CURRENT_TIMESTAMP
            """
            )
            rowcount = cursor.rowcount
            logger.info(f"[sync_cagg_to_prices_1m] Synced {rowcount} rows")
            return {"interval": "1m", "synced_rows": rowcount}
    except Exception as e:
        logger.exception(f"[sync_cagg_to_prices_1m] Error: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_cagg_to_prices_15m(self):
    """
    15분봉 Continuous Aggregate → 통합 테이블 동기화
    5분마다 실행 권장
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stock_prices_15m 
                    (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
                SELECT 
                    bucket, 
                    stock_code, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume, 
                    amount, 
                    trade_count, 
                    'realtime', 
                    CURRENT_TIMESTAMP
                FROM _cagg_15m
                WHERE bucket >= NOW() - INTERVAL '1 hour'
                ON CONFLICT (stock_code, bucket) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    trade_count = EXCLUDED.trade_count,
                    source = 'realtime',
                    updated_at = CURRENT_TIMESTAMP
            """
            )
            rowcount = cursor.rowcount
            logger.info(f"[sync_cagg_to_prices_15m] Synced {rowcount} rows")
            return {"interval": "15m", "synced_rows": rowcount}
    except Exception as e:
        logger.exception(f"[sync_cagg_to_prices_15m] Error: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def sync_cagg_to_prices_1h(self):
    """
    1시간봉 Continuous Aggregate → 통합 테이블 동기화
    15분마다 실행 권장
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stock_prices_1h 
                    (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
                SELECT 
                    bucket, 
                    stock_code, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume, 
                    amount, 
                    trade_count, 
                    'realtime', 
                    CURRENT_TIMESTAMP
                FROM _cagg_1h
                WHERE bucket >= NOW() - INTERVAL '4 hours'
                ON CONFLICT (stock_code, bucket) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    trade_count = EXCLUDED.trade_count,
                    source = 'realtime',
                    updated_at = CURRENT_TIMESTAMP
            """
            )
            rowcount = cursor.rowcount
            logger.info(f"[sync_cagg_to_prices_1h] Synced {rowcount} rows")
            return {"interval": "1h", "synced_rows": rowcount}
    except Exception as e:
        logger.exception(f"[sync_cagg_to_prices_1h] Error: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_cagg_to_prices_1d(self):
    """
    1일봉 Continuous Aggregate → 통합 테이블 동기화
    1시간마다 실행 권장
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stock_prices_1d 
                    (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
                SELECT 
                    bucket, 
                    stock_code, 
                    open, 
                    high, 
                    low, 
                    close, 
                    volume, 
                    amount, 
                    trade_count, 
                    'realtime', 
                    CURRENT_TIMESTAMP
                FROM _cagg_1d
                WHERE bucket >= NOW() - INTERVAL '3 days'
                ON CONFLICT (stock_code, bucket) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    trade_count = EXCLUDED.trade_count,
                    source = 'realtime',
                    updated_at = CURRENT_TIMESTAMP
            """
            )
            rowcount = cursor.rowcount
            logger.info(f"[sync_cagg_to_prices_1d] Synced {rowcount} rows")
            return {"interval": "1d", "synced_rows": rowcount}
    except Exception as e:
        logger.exception(f"[sync_cagg_to_prices_1d] Error: {e}")
        raise self.retry(exc=e)


@shared_task
def sync_all_prices():
    """
    모든 시간 단위 동기화 (수동 실행용)
    """
    results = {}

    # 각 태스크를 순차 실행
    try:
        results["1m"] = sync_cagg_to_prices_1m.apply().get()
    except Exception as e:
        results["1m"] = {"error": str(e)}

    try:
        results["15m"] = sync_cagg_to_prices_15m.apply().get()
    except Exception as e:
        results["15m"] = {"error": str(e)}

    try:
        results["1h"] = sync_cagg_to_prices_1h.apply().get()
    except Exception as e:
        results["1h"] = {"error": str(e)}

    try:
        results["1d"] = sync_cagg_to_prices_1d.apply().get()
    except Exception as e:
        results["1d"] = {"error": str(e)}

    return results
