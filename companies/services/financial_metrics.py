"""
재무 지표 계산 서비스
PER, PBR, ROE, 부채비율, 배당수익률을 계산합니다.
"""

from decimal import Decimal, InvalidOperation
import logging
from typing import Optional

from companies.models import FinancialStatement, Dividend

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
        total_liabilities: Optional[int], total_equity: Optional[int]
    ) -> Optional[Decimal]:
        """
        부채비율 계산

        Args:
            total_liabilities: 총부채
            total_equity: 총자본

        Returns:
            부채비율 (%), None if 계산 불가
        """
        if total_liabilities is None or total_equity is None:
            return None
        if total_equity <= 0:
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
    def calculate_pbr(
        market_cap: int, total_assets: Optional[int], total_liabilities: Optional[int]
    ) -> Optional[Decimal]:
        """
        PBR (주가순자산비율) 계산

        Args:
            market_cap: 시가총액
            total_assets: 총자산
            total_liabilities: 총부채

        Returns:
            PBR (배), None if 계산 불가
        """
        if total_assets is None or total_liabilities is None:
            return None

        try:
            # 순자산 = 총자산 - 총부채
            net_assets = Decimal(total_assets) - Decimal(total_liabilities)
            if net_assets <= 0:
                return None

            pbr = Decimal(market_cap) / net_assets
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

    @staticmethod
    def calculate_eps(
        net_income: int, market_cap: int, current_price: int
    ) -> Optional[Decimal]:
        """
        EPS (주당순이익) 계산

        Args:
            net_income: 당기순이익
            market_cap: 시가총액
            current_price: 현재 주가

        Returns:
            EPS (원), None if 계산 불가
        """
        if not net_income or net_income <= 0:
            return None
        if not market_cap or market_cap <= 0:
            return None
        if not current_price or current_price <= 0:
            return None

        try:
            # 발행주식수 = 시가총액 / 주가
            shares_outstanding = Decimal(market_cap) / Decimal(current_price)
            if shares_outstanding <= 0:
                return None

            # EPS = 당기순이익 / 발행주식수
            eps = Decimal(net_income) / shares_outstanding
            return round(eps, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_operating_profit_margin(
        operating_profit: int, revenue: int
    ) -> Optional[Decimal]:
        """
        영업이익률 계산

        Args:
            operating_profit: 영업이익
            revenue: 매출액

        Returns:
            영업이익률 (%), None if 계산 불가
        """
        if not revenue or revenue <= 0:
            return None

        try:
            operating_margin = (Decimal(operating_profit) / Decimal(revenue)) * 100
            return round(operating_margin, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_yoy_growth(
        current_value: int, previous_value: int
    ) -> Optional[Decimal]:
        """
        YoY (Year over Year) 성장률 계산

        Args:
            current_value: 현재 연도 값
            previous_value: 전년도 값

        Returns:
            YoY 성장률 (%), None if 계산 불가
        """
        if previous_value is None or previous_value == 0:
            return None

        try:
            yoy = (
                (Decimal(current_value) - Decimal(previous_value))
                / Decimal(previous_value)
            ) * 100
            return round(yoy, 2)
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
            financial_statement.total_liabilities,
            financial_statement.total_equity,
        )

        # 3. PER 계산 (시가총액 + 재무제표)
        per = self.calculate_per(
            company.market_amount, financial_statement.net_income or 0
        )

        # 4. PBR 계산 (시가총액 + 순자산)
        pbr = self.calculate_pbr(
            company.market_amount,
            financial_statement.total_assets,
            financial_statement.total_liabilities,
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

        # 6. EPS 계산 (당기순이익 + 시가총액 + 현재가)
        eps = None
        try:
            from core.models import StockPrice1d

            latest_price = (
                StockPrice1d.objects.filter(stock_code=company.stock_code)
                .order_by("-bucket")
                .first()
            )

            if latest_price and latest_price.close:
                eps = self.calculate_eps(
                    financial_statement.net_income or 0,
                    company.market_amount,
                    int(latest_price.close),
                )
        except Exception as e:
            logger.warning(f"EPS 계산 실패: {company.stock_code} - {e}")

        # 7. 영업이익률 계산
        operating_profit_margin = self.calculate_operating_profit_margin(
            financial_statement.operating_profit or 0,
            financial_statement.revenue or 0,
        )

        # 8. YoY 성장률 계산 (전년도 대비)
        yoy_revenue = None
        yoy_operating_profit = None
        yoy_net_income = None

        try:
            # 같은 보고서 코드의 전년도 데이터 조회
            previous_statement = FinancialStatement.objects.filter(
                company=company,
                fiscal_year=financial_statement.fiscal_year - 1,
                report_code=financial_statement.report_code,
            ).first()

            if previous_statement:
                if financial_statement.revenue and previous_statement.revenue:
                    yoy_revenue = self.calculate_yoy_growth(
                        financial_statement.revenue, previous_statement.revenue
                    )

                if (
                    financial_statement.operating_profit
                    and previous_statement.operating_profit
                ):
                    yoy_operating_profit = self.calculate_yoy_growth(
                        financial_statement.operating_profit,
                        previous_statement.operating_profit,
                    )

                if financial_statement.net_income and previous_statement.net_income:
                    yoy_net_income = self.calculate_yoy_growth(
                        financial_statement.net_income, previous_statement.net_income
                    )
        except Exception as e:
            logger.warning(
                f"YoY 성장률 계산 실패: {company.stock_code} ({financial_statement.fiscal_year}년) - {e}"
            )

        return {
            "roe": roe,
            "debt_ratio": debt_ratio,
            "per": per,
            "pbr": pbr,
            "dividend_yield": dividend_yield,
            "eps": eps,
            "operating_profit_margin": operating_profit_margin,
            "yoy_revenue": yoy_revenue,
            "yoy_operating_profit": yoy_operating_profit,
            "yoy_net_income": yoy_net_income,
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
        financial_statement.eps = metrics["eps"]
        financial_statement.operating_profit_margin = metrics["operating_profit_margin"]
        financial_statement.yoy_revenue = metrics["yoy_revenue"]
        financial_statement.yoy_operating_profit = metrics["yoy_operating_profit"]
        financial_statement.yoy_net_income = metrics["yoy_net_income"]
        financial_statement.metrics_calculated_at = timezone.now()

        financial_statement.save(
            update_fields=[
                "roe",
                "debt_ratio",
                "per",
                "pbr",
                "dividend_yield",
                "eps",
                "operating_profit_margin",
                "yoy_revenue",
                "yoy_operating_profit",
                "yoy_net_income",
                "metrics_calculated_at",
            ]
        )

        logger.info(
            f"재무 지표 계산 완료: {financial_statement.company.stock_code} "
            f"({financial_statement.fiscal_year}년)"
        )

        return financial_statement
