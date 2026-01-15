"""
YFinance 과거 주가 데이터 수집 서비스

yfinance API를 통해 한국 주식의 과거 OHLCV 데이터를 수집하고
통합 테이블(stock_prices_*)에 저장합니다.
"""

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pandas as pd
import yfinance as yf
from django.db import connection

from companies.models import Company

logger = logging.getLogger(__name__)


class YFinanceService:
    """yfinance를 통한 과거 주가 데이터 수집 서비스"""

    # 시간 단위별 설정
    INTERVAL_CONFIG = {
        "1m": {
            "period": "1d",  # 최근 1일
            "table": "stock_prices_1m",
            "yf_interval": "1m",
        },
        "15m": {
            "period": "5d",  # 최근 5일
            "table": "stock_prices_15m",
            "yf_interval": "15m",
        },
        "1h": {
            "period": "1mo",  # 최근 1달
            "table": "stock_prices_1h",
            "yf_interval": "1h",
        },
        "1d": {
            "period": "1y",  # 최근 1년
            "table": "stock_prices_1d",
            "yf_interval": "1d",
        },
    }

    def __init__(self, delay_between_requests: float = 1.0):
        """
        Args:
            delay_between_requests: API 요청 간 딜레이 (초). Rate limit 방지용.
        """
        self.delay_between_requests = delay_between_requests

    @staticmethod
    def get_market_from_db(stock_code: str) -> Optional[str]:
        """
        DB에서 종목의 시장 정보를 조회

        Args:
            stock_code: 6자리 종목코드

        Returns:
            시장 구분 ("KOSPI" 또는 "KOSDAQ"), 없으면 None
        """
        try:
            company = Company.objects.filter(stock_code=stock_code).first()
            if company and company.market:
                return company.market
            return None
        except Exception as e:
            logger.warning(f"Failed to get market from DB for {stock_code}: {e}")
            return None

    def get_ticker_symbol(self, stock_code: str, market: str = "KOSPI") -> str:
        """
        종목코드를 yfinance 티커 형식으로 변환

        Args:
            stock_code: 6자리 종목코드
            market: 시장 구분 (KOSPI/KOSDAQ)

        Returns:
            yfinance 티커 (예: 005930.KS)
        """
        suffix = ".KS" if market.upper() == "KOSPI" else ".KQ"
        return f"{stock_code}{suffix}"

    def fetch_ohlcv(
        self,
        stock_code: str,
        interval: str,
        market: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        yfinance에서 OHLCV 데이터 가져오기

        Args:
            stock_code: 종목코드 (6자리)
            interval: 시간 단위 (1m, 15m, 1h, 1d)
            market: 시장 구분 (KOSPI/KOSDAQ). None이면 DB에서 조회

        Returns:
            DataFrame with columns: [bucket, stock_code, open, high, low, close, volume, amount]
            또는 데이터가 없으면 None
        """
        if interval not in self.INTERVAL_CONFIG:
            raise ValueError(
                f"Invalid interval: {interval}. Valid: {list(self.INTERVAL_CONFIG.keys())}"
            )

        config = self.INTERVAL_CONFIG[interval]

        # 시장 결정: 파라미터 > DB 조회
        if market is None:
            market = self.get_market_from_db(stock_code)
            if market:
                logger.info(f"Market for {stock_code} from DB: {market}")
            else:
                logger.warning(
                    f"Market not found in DB for {stock_code}, cannot fetch data"
                )
                return None
        else:
            market = market.upper()

        # yfinance 티커 생성 및 데이터 조회
        ticker_symbol = self.get_ticker_symbol(stock_code, market)
        df = None

        try:
            logger.info(f"Fetching {interval} data for {ticker_symbol}")
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(
                period=config["period"],
                interval=config["yf_interval"],
            )

            if not df.empty:
                logger.info(
                    f"Successfully fetched data for {ticker_symbol} ({len(df)} rows)"
                )
            else:
                logger.warning(f"No data for {ticker_symbol}")
                return None

        except Exception as e:
            logger.exception(f"Error fetching {ticker_symbol}: {e}")
            return None

        if df is None or df.empty:
            logger.warning(f"No data returned for {stock_code} ({interval})")
            return None

        # 컬럼명 정규화
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )

        # 필요한 컬럼만 선택
        df = df[["open", "high", "low", "close", "volume"]]
        df["stock_code"] = stock_code
        df["amount"] = df["close"] * df["volume"]  # 거래대금 계산
        df["trade_count"] = 0  # yfinance는 체결 건수 미제공
        df["source"] = "yfinance"

        # 인덱스를 bucket 컬럼으로 변환
        df = df.reset_index()
        # 인덱스 이름이 Datetime 또는 Date일 수 있음
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "bucket"})
        elif "Date" in df.columns:
            df = df.rename(columns={"Date": "bucket"})
        else:
            # 첫 번째 컬럼이 시간 컬럼
            df = df.rename(columns={df.columns[0]: "bucket"})

        # 타임존 제거 (naive datetime으로 변환)
        if hasattr(df["bucket"].dt, "tz") and df["bucket"].dt.tz is not None:
            df["bucket"] = df["bucket"].dt.tz_localize(None)

        logger.info(f"Fetched {len(df)} rows for {market}:{stock_code} ({interval})")
        return df

    def save_to_database(
        self,
        df: pd.DataFrame,
        table_name: str,
        force: bool = False,
    ) -> int:
        """
        DataFrame을 DB에 저장 (UPSERT)

        Args:
            df: 저장할 데이터
            table_name: 테이블 이름
            force: True면 기존 데이터 덮어쓰기, False면 건너뛰기

        Returns:
            저장된 행 수
        """
        if df is None or df.empty:
            return 0

        saved_count = 0

        with connection.cursor() as cursor:
            for _, row in df.iterrows():
                try:
                    if force:
                        # UPSERT: 기존 데이터 덮어쓰기
                        sql = f"""
                            INSERT INTO {table_name} 
                            (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (stock_code, bucket) DO UPDATE SET
                                open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                close = EXCLUDED.close,
                                volume = EXCLUDED.volume,
                                amount = EXCLUDED.amount,
                                source = EXCLUDED.source,
                                updated_at = CURRENT_TIMESTAMP
                        """
                    else:
                        # INSERT IGNORE: 기존 데이터가 있으면 건너뛰기
                        sql = f"""
                            INSERT INTO {table_name} 
                            (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (stock_code, bucket) DO NOTHING
                        """

                    cursor.execute(
                        sql,
                        [
                            row["bucket"],
                            row["stock_code"],
                            float(row["open"]) if pd.notna(row["open"]) else None,
                            float(row["high"]) if pd.notna(row["high"]) else None,
                            float(row["low"]) if pd.notna(row["low"]) else None,
                            float(row["close"]) if pd.notna(row["close"]) else None,
                            int(row["volume"]) if pd.notna(row["volume"]) else 0,
                            float(row["amount"]) if pd.notna(row["amount"]) else 0,
                            (
                                int(row["trade_count"])
                                if pd.notna(row["trade_count"])
                                else 0
                            ),
                            row["source"],
                        ],
                    )
                    saved_count += cursor.rowcount

                except Exception as e:
                    logger.warning(f"Error inserting row: {e}")
                    continue

        return saved_count

    def sync_stock_history(
        self,
        stock_code: str,
        intervals: list[str] | None = None,
        market: Optional[str] = None,
    ) -> dict:
        """
        특정 종목의 히스토리 데이터 동기화

        Args:
            stock_code: 종목코드
            intervals: 동기화할 시간 단위 목록 (None이면 전체)
            market: 시장 구분 (KOSPI/KOSDAQ). None이면 DB에서 조회

        Returns:
            각 interval별 결과 딕셔너리

        Note:
            yfinance 데이터는 실시간 스트리밍에서 빠질 수 있는 정보를 보완하기 위해
            항상 기존 데이터를 덮어씁니다.
        """
        if intervals is None:
            intervals = ["1m", "15m", "1h", "1d"]

        results = {}

        for interval in intervals:
            try:
                # yfinance에서 데이터 가져오기
                df = self.fetch_ohlcv(stock_code, interval, market)

                if df is None or df.empty:
                    results[interval] = {
                        "status": "no_data",
                        "saved": 0,
                        "fetched": 0,
                    }
                    continue

                # DB에 저장 (yfinance는 항상 덮어쓰기)
                table_name = self.INTERVAL_CONFIG[interval]["table"]
                saved_count = self.save_to_database(df, table_name, force=True)

                results[interval] = {
                    "status": "success",
                    "saved": saved_count,
                    "fetched": len(df),
                }

                logger.info(
                    f"[{stock_code}] {interval}: fetched={len(df)}, saved={saved_count}"
                )

            except Exception as e:
                logger.exception(f"Error syncing {stock_code} ({interval}): {e}")
                results[interval] = {
                    "status": "error",
                    "saved": 0,
                    "fetched": 0,
                    "message": str(e),
                }

            # Rate limit 방지
            if self.delay_between_requests > 0:
                time.sleep(self.delay_between_requests)

        return results

    def sync_multiple_stocks(
        self,
        stock_codes: list[str],
        intervals: list[str] | None = None,
    ) -> dict:
        """
        여러 종목의 히스토리 데이터 동기화

        Args:
            stock_codes: 종목코드 목록
            intervals: 동기화할 시간 단위 목록

        Returns:
            종목별 결과 딕셔너리

        Note:
            yfinance 데이터는 실시간 스트리밍에서 빠질 수 있는 정보를 보완하기 위해
            항상 기존 데이터를 덮어씁니다.
        """
        results = {}

        for i, stock_code in enumerate(stock_codes):
            logger.info(f"Syncing {stock_code} ({i+1}/{len(stock_codes)})")
            # market은 각 종목별로 DB에서 조회하므로 None으로 전달
            results[stock_code] = self.sync_stock_history(stock_code, intervals, None)

        return results
