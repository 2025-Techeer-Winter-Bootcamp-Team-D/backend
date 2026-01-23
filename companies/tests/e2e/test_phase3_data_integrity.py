# companies/tests/e2e/test_phase3_data_integrity.py

"""
Phase 3: 데이터 정합성 검증 테스트
- Company 데이터
- FinancialStatement 데이터
- Report 데이터
- Price 데이터
"""

import time
import logging
from typing import Dict, Any
from companies.models import Company, FinancialStatement, Report
from core.models import StockPrice1d

logger = logging.getLogger(__name__)


class Phase3DataIntegrityTest:
    """Phase 3: 데이터 정합성 검증 테스트"""

    @staticmethod
    def run() -> Dict[str, Any]:
        """Phase 3 전체 테스트 실행"""
        start_time = time.time()
        results = {
            "status": "success",
            "duration": 0,
            "checks": {}
        }

        try:
            # Company 데이터 검증
            results["checks"]["company_data"] = Phase3DataIntegrityTest._check_company_data()

            # FinancialStatement 데이터 검증
            results["checks"]["financial_data"] = Phase3DataIntegrityTest._check_financial_data()

            # Report 데이터 검증
            results["checks"]["report_data"] = Phase3DataIntegrityTest._check_report_data()

            # Price 데이터 검증
            results["checks"]["price_data"] = Phase3DataIntegrityTest._check_price_data()

        except Exception as e:
            logger.error(f"Phase 3 실행 중 오류 발생: {str(e)}")
            results["status"] = "error"
            results["error"] = str(e)

        results["duration"] = round(time.time() - start_time, 2)
        return results

    @staticmethod
    def _check_company_data() -> Dict[str, Any]:
        """Company 데이터 검증"""
        start_time = time.time()
        try:
            # 최소 1개 이상의 기업 존재 확인
            company_count = Company.objects.filter(is_deleted=False).count()
            if company_count == 0:
                return {
                    "status": "error",
                    "duration": round(time.time() - start_time, 2),
                    "error": "Company 데이터가 없습니다",
                    "count": 0
                }

            # 필수 필드 검증
            invalid_companies = Company.objects.filter(
                is_deleted=False
            ).filter(
                stock_code__isnull=True
            ) | Company.objects.filter(
                company_name__isnull=True
            ) | Company.objects.filter(
                company_name=""
            )

            invalid_count = invalid_companies.count()

            # corp_code와 stock_code 유효성 확인
            invalid_corp_code = Company.objects.filter(
                is_deleted=False,
                corp_code__isnull=False
            ).exclude(
                corp_code__regex=r'^\d{8}$'  # 8자리 숫자
            ).count()

            invalid_stock_code = Company.objects.filter(
                is_deleted=False
            ).exclude(
                stock_code__regex=r'^\d{6}$'  # 6자리 숫자
            ).count()

            # 삼성전자 존재 확인 (테스트용)
            samsung = Company.objects.filter(stock_code="005930", is_deleted=False).first()

            is_valid = (
                invalid_count == 0
                and invalid_corp_code == 0
                and invalid_stock_code == 0
            )
            return {
                "status": "ok" if is_valid else "warning",
                "duration": round(time.time() - start_time, 2),
                "count": company_count,
                "invalid_required_fields": invalid_count,
                "invalid_corp_code": invalid_corp_code,
                "invalid_stock_code": invalid_stock_code,
                "samsung_exists": bool(samsung),
                "samsung_name": samsung.company_name if samsung else None
            }

        except Exception as e:
            logger.error(f"Company 데이터 검증 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }

    @staticmethod
    def _check_financial_data() -> Dict[str, Any]:
        """FinancialStatement 데이터 검증"""
        start_time = time.time()
        try:
            # 재무제표 데이터 존재 확인
            financial_count = FinancialStatement.objects.count()

            # 2024년 이하 데이터만 존재하는지 확인 (2025-2026 제외)
            future_data = FinancialStatement.objects.filter(fiscal_year__gte=2025).count()

            # 최신 연도 확인
            latest_year = FinancialStatement.objects.order_by('-fiscal_year').first()
            latest_fiscal_year = latest_year.fiscal_year if latest_year else None

            # 재무 지표 값 범위 검증 (음수 가능, 하지만 None이 아니어야 함)
            invalid_values = FinancialStatement.objects.filter(
                revenue__isnull=False,
                revenue__lt=0,
                revenue__gt=-1000000000000000  # 비정상적으로 큰 음수
            ).count()

            # 기업과의 관계 검증
            orphan_financials = FinancialStatement.objects.filter(company__isnull=True).count()

            return {
                "status": "ok" if future_data == 0 and orphan_financials == 0 else "warning",
                "duration": round(time.time() - start_time, 2),
                "count": financial_count,
                "latest_year": latest_fiscal_year,
                "future_data_count": future_data,
                "invalid_values": invalid_values,
                "orphan_records": orphan_financials
            }

        except Exception as e:
            logger.error(f"FinancialStatement 데이터 검증 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }

    @staticmethod
    def _check_report_data() -> Dict[str, Any]:
        """Report 데이터 검증"""
        start_time = time.time()
        try:
            # 보고서 데이터 존재 확인
            report_count = Report.objects.count()

            # 보고서 제출일 형식 검증
            invalid_dates = Report.objects.filter(submitted_at__isnull=True).count()

            # 기업과의 관계 검증
            orphan_reports = Report.objects.filter(company__isnull=True).count()

            # rcept_no 중복 확인 (unique=True이므로 0이어야 함)
            from django.db.models import Count
            duplicate_rcept_no = Report.objects.values('rcept_no').annotate(
                count=Count('rcept_no')
            ).filter(count__gt=1).count()

            # 가장 최근 보고서 확인
            latest_report = Report.objects.order_by('-submitted_at').first()
            latest_date = latest_report.submitted_at if latest_report else None

            return {
                "status": "ok" if orphan_reports == 0 and duplicate_rcept_no == 0 else "warning",
                "duration": round(time.time() - start_time, 2),
                "count": report_count,
                "invalid_dates": invalid_dates,
                "orphan_records": orphan_reports,
                "duplicate_rcept_no": duplicate_rcept_no,
                "latest_date": latest_date.isoformat() if latest_date else None
            }

        except Exception as e:
            logger.error(f"Report 데이터 검증 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }

    @staticmethod
    def _check_price_data() -> Dict[str, Any]:
        """Price 데이터 검증"""
        start_time = time.time()
        try:
            # 주가 데이터 존재 확인 (1일봉 기준)
            price_count = StockPrice1d.objects.count()

            if price_count == 0:
                return {
                    "status": "warning",
                    "duration": round(time.time() - start_time, 2),
                    "message": "주가 데이터가 없습니다",
                    "count": 0
                }

            # 가격 값 유효성 검증 (> 0)
            invalid_prices = StockPrice1d.objects.filter(close_price__lte=0).count()

            # 최신 주가 데이터 확인
            latest_price = StockPrice1d.objects.order_by('-time').first()
            latest_date = latest_price.time if latest_price else None

            # 시계열 데이터 정렬 확인 (최근 10개 샘플)
            recent_prices = StockPrice1d.objects.order_by('-time')[:10]
            is_sorted = all(
                recent_prices[i].time >= recent_prices[i + 1].time
                for i in range(len(recent_prices) - 1)
            ) if len(recent_prices) > 1 else True

            return {
                "status": "ok" if invalid_prices == 0 and is_sorted else "warning",
                "duration": round(time.time() - start_time, 2),
                "count": price_count,
                "invalid_prices": invalid_prices,
                "latest_date": latest_date.isoformat() if latest_date else None,
                "is_sorted": is_sorted
            }

        except Exception as e:
            logger.error(f"Price 데이터 검증 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }
