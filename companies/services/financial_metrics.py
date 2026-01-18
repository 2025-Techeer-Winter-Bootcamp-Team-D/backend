"""
재무 지표 계산 서비스
PER, PBR, ROE, 부채비율, 배당수익률을 계산합니다.
"""

from decimal import Decimal, InvalidOperation
import logging
from typing import Optional

from companies.models import Company, FinancialStatement, Dividend

logger = logging.getLogger(__name__)


class FinancialMetricsService:
    """재무 지표 계산 서비스"""

    @staticmethod
    def calculate_roe(net_income: int, total_equity: int) -> Optional[Decimal]:
        """
        ROE (자기자본이익률) 계산

        Args:
            net_income: 당기순이익
            total_equity: 총자본

        Returns:
            ROE (%), None if 계산 불가
        """
        if not total_equity or total_equity <= 0:
            return None

        try:
            roe = (Decimal(net_income) / Decimal(total_equity)) * 100
            return round(roe, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_debt_ratio(
        total_liabilities: int, total_equity: int
    ) -> Optional[Decimal]:
        """
        부채비율 계산

        Args:
            total_liabilities: 총부채
            total_equity: 총자본

        Returns:
            부채비율 (%), None if 계산 불가
        """
        if not total_equity or total_equity <= 0:
            return None

        try:
            debt_ratio = (Decimal(total_liabilities) / Decimal(total_equity)) * 100
            return round(debt_ratio, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_per(market_cap: int, net_income: int) -> Optional[Decimal]:
        """
        PER (주가수익비율) 계산

        Args:
            market_cap: 시가총액
            net_income: 당기순이익

        Returns:
            PER (배), None if 계산 불가
        """
        if not net_income or net_income <= 0:
            return None

        try:
            per = Decimal(market_cap) / Decimal(net_income)
            return round(per, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_pbr(market_cap: int, total_equity: int) -> Optional[Decimal]:
        """
        PBR (주가순자산비율) 계산

        Args:
            market_cap: 시가총액
            total_equity: 총자본

        Returns:
            PBR (배), None if 계산 불가
        """
        if not total_equity or total_equity <= 0:
            return None

        try:
            pbr = Decimal(market_cap) / Decimal(total_equity)
            return round(pbr, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_dividend_yield(
        dividend_per_share: Decimal, current_price: int
    ) -> Optional[Decimal]:
        """
        배당수익률 계산

        Args:
            dividend_per_share: 주당 배당금
            current_price: 현재 주가

        Returns:
            배당수익률 (%), None if 계산 불가
        """
        if not current_price or current_price <= 0:
            return None

        try:
            dividend_yield = (dividend_per_share / Decimal(current_price)) * 100
            return round(dividend_yield, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    def calculate_all_metrics(self, financial_statement: FinancialStatement) -> dict:
        """
        재무제표에 대한 모든 지표 계산

        Args:
            financial_statement: FinancialStatement 인스턴스

        Returns:
            계산된 지표 딕셔너리
        """
        company = financial_statement.company

        # 1. ROE 계산 (재무제표 데이터만 사용)
        roe = self.calculate_roe(
            financial_statement.net_income or 0, financial_statement.total_equity or 0
        )

        # 2. 부채비율 계산 (재무제표 데이터만 사용)
        debt_ratio = self.calculate_debt_ratio(
            financial_statement.total_liabilities or 0,
            financial_statement.total_equity or 0,
        )

        # 3. PER 계산 (시가총액 + 재무제표)
        per = self.calculate_per(
            company.market_amount, financial_statement.net_income or 0
        )

        # 4. PBR 계산 (시가총액 + 재무제표)
        pbr = self.calculate_pbr(
            company.market_amount, financial_statement.total_equity or 0
        )

        # 5. 배당수익률 계산 (배당금 + 현재가)
        dividend_yield = None
        try:
            # 해당 연도 배당금 조회
            dividend = Dividend.objects.filter(
                company=company,
                fiscal_year=financial_statement.fiscal_year,
                dividend_type="cash",
            ).first()

            if dividend:
                # 현재가 조회 (최신 일봉 종가)
                from core.models import StockPrice1d

                latest_price = (
                    StockPrice1d.objects.filter(stock_code=company.stock_code)
                    .order_by("-bucket")
                    .first()
                )

                if latest_price and latest_price.close:
                    dividend_yield = self.calculate_dividend_yield(
                        dividend.dividend_per_share, int(latest_price.close)
                    )
        except Exception as e:
            logger.warning(f"배당수익률 계산 실패: {company.stock_code} - {e}")

        return {
            "roe": roe,
            "debt_ratio": debt_ratio,
            "per": per,
            "pbr": pbr,
            "dividend_yield": dividend_yield,
        }

    def update_financial_metrics(
        self, financial_statement: FinancialStatement
    ) -> FinancialStatement:
        """
        재무제표의 지표를 계산하여 업데이트

        Args:
            financial_statement: FinancialStatement 인스턴스

        Returns:
            업데이트된 FinancialStatement 인스턴스
        """
        from django.utils import timezone

        metrics = self.calculate_all_metrics(financial_statement)

        financial_statement.roe = metrics["roe"]
        financial_statement.debt_ratio = metrics["debt_ratio"]
        financial_statement.per = metrics["per"]
        financial_statement.pbr = metrics["pbr"]
        financial_statement.dividend_yield = metrics["dividend_yield"]
        financial_statement.metrics_calculated_at = timezone.now()

        financial_statement.save(
            update_fields=[
                "roe",
                "debt_ratio",
                "per",
                "pbr",
                "dividend_yield",
                "metrics_calculated_at",
            ]
        )

        logger.info(
            f"재무 지표 계산 완료: {financial_statement.company.stock_code} "
            f"({financial_statement.fiscal_year}년)"
        )

        return financial_statement
