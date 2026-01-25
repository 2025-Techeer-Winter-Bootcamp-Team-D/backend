# companies/services/company_cleanup.py
"""
재무지표가 없는 기업 정리 서비스
"""

import logging
from typing import Dict, Any, List
from decimal import Decimal

from django.db import transaction

from companies.models import Company, FinancialStatement

logger = logging.getLogger(__name__)


class CompanyCleanupService:
    """재무지표가 유효하지 않은 기업을 정리하는 서비스"""

    @staticmethod
    def is_metric_empty(value) -> bool:
        """재무지표 값이 비어있는지 확인 (null, 0, Decimal(0))"""
        if value is None:
            return True
        if isinstance(value, (int, float, Decimal)) and value == 0:
            return True
        return False

    @staticmethod
    def check_company_has_valid_metrics(stock_code: str) -> bool:
        """
        기업의 가장 최근 재무제표에서 유효한 재무지표가 있는지 확인

        Returns:
            True: 유효한 지표가 하나라도 있음
            False: per, pbr, roe, debt_ratio, dividend_yield 모두 0이거나 null
        """
        # 가장 최근 재무제표 조회
        latest_statement = (
            FinancialStatement.objects.filter(company_id=stock_code)
            .order_by("-fiscal_year", "-report_code")
            .first()
        )

        if not latest_statement:
            # 재무제표가 없으면 유효하지 않음
            return False

        # 5가지 지표 중 하나라도 유효한 값이 있으면 True
        metrics = [
            latest_statement.per,
            latest_statement.pbr,
            latest_statement.roe,
            latest_statement.debt_ratio,
            latest_statement.dividend_yield,
        ]

        for metric in metrics:
            if not CompanyCleanupService.is_metric_empty(metric):
                return True

        return False

    @staticmethod
    def find_companies_without_valid_metrics() -> List[str]:
        """
        유효한 재무지표가 없는 기업 목록 조회

        Returns:
            삭제 대상 기업의 stock_code 리스트
        """
        # 삭제되지 않은 모든 기업 조회
        companies = Company.objects.filter(is_deleted=False).values_list(
            "stock_code", flat=True
        )

        invalid_companies = []

        for stock_code in companies:
            if not CompanyCleanupService.check_company_has_valid_metrics(stock_code):
                invalid_companies.append(stock_code)

        return invalid_companies

    @staticmethod
    @transaction.atomic
    def cleanup_companies_without_metrics(dry_run: bool = True) -> Dict[str, Any]:
        """
        재무지표가 모두 0이거나 null인 기업을 soft delete

        Args:
            dry_run: True면 실제 삭제하지 않고 대상만 조회

        Returns:
            처리 결과 통계
        """
        logger.info(
            f"[CompanyCleanup] 재무지표 없는 기업 정리 시작 (dry_run={dry_run})"
        )

        # 삭제 대상 기업 조회
        invalid_companies = CompanyCleanupService.find_companies_without_valid_metrics()
        total_invalid = len(invalid_companies)

        logger.info(f"[CompanyCleanup] 삭제 대상 기업 수: {total_invalid}")

        # 삭제 대상 기업 상세 정보 조회
        companies_info = list(
            Company.objects.filter(stock_code__in=invalid_companies).values(
                "stock_code", "company_name", "market"
            )
        )

        result = {
            "dry_run": dry_run,
            "total_checked": Company.objects.filter(is_deleted=False).count(),
            "total_invalid": total_invalid,
            "deleted_count": 0,
            "companies": companies_info,
        }

        if not dry_run and invalid_companies:
            # 실제 삭제 수행 (soft delete)
            deleted_count = Company.objects.filter(
                stock_code__in=invalid_companies
            ).update(is_deleted=True)

            result["deleted_count"] = deleted_count
            logger.info(f"[CompanyCleanup] {deleted_count}개 기업 삭제 완료")

        return result

    @staticmethod
    def get_cleanup_preview() -> Dict[str, Any]:
        """
        삭제 대상 기업 미리보기 (dry_run)
        """
        return CompanyCleanupService.cleanup_companies_without_metrics(dry_run=True)

    @staticmethod
    def execute_cleanup() -> Dict[str, Any]:
        """
        실제 삭제 수행
        """
        return CompanyCleanupService.cleanup_companies_without_metrics(dry_run=False)
