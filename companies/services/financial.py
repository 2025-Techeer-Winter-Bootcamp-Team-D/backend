# companies/services/financial.py
"""
재무 지표 서비스
DART API를 통해 재무제표를 조회하고 FinancialStatement, RevenueComposition 모델에 저장하는 서비스
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from companies.models import Company, FinancialStatement, RevenueComposition
from companies.services.dart_api import DartAPIClient, DartAPIError

logger = logging.getLogger(__name__)


class FinancialService:
    """재무 지표 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    def sync_financial_statements(
        self,
        company: Company,
        year: int,
        report_code: Optional[str] = None,
        sync_all_reports: bool = False,
    ) -> List[FinancialStatement]:
        """
        DART API에서 재무제표를 조회하여 FinancialStatement 모델에 저장

        Args:
            company: Company 인스턴스
            year: 사업연도 (예: 2024)
            report_code: 보고서 코드 (11011: 사업보고서, 11012: 반기보고서 등)
                       None이면 sync_all_reports에 따라 처리
            sync_all_reports: 모든 보고서 코드 조회 여부 (기본값: False)
                             True: 11011, 11012, 11013, 11014 모두 조회
                             False: report_code만 조회 (기본값: 11011)

        Returns:
            생성/업데이트된 FinancialStatement 인스턴스 리스트

        Raises:
            DartAPIError: DART API 호출 실패 시
            ValueError: corp_code가 없는 경우
        """
        if not company.corp_code:
            raise ValueError(
                f"Company {company.stock_code}에 corp_code가 설정되지 않았습니다."
            )

        # 보고서 코드 리스트 결정
        if sync_all_reports:
            report_codes = [
                "11011",
                "11012",
                "11013",
                "11014",
            ]  # 사업, 반기, 1분기, 3분기
        elif report_code:
            report_codes = [report_code]
        else:
            report_codes = ["11011"]  # 기본값: 사업보고서만

        all_statements = []

        for rc in report_codes:
            try:
                statement = self._sync_single_financial_statement(company, year, rc)
                if statement:
                    all_statements.append(statement)
            except DartAPIError as e:
                # "조회된 데이타가 없습니다" (status: 013)는 정상 (해당 보고서가 없을 수 있음)
                error_message = str(e)
                if (
                    "013" in error_message
                    or "조회된 데이타가 없습니다" in error_message
                ):
                    logger.debug(
                        f"재무제표 데이터 없음 (정상): {company.stock_code} ({year}년, {rc})"
                    )
                    continue
                else:
                    logger.warning(
                        f"재무제표 조회 실패: {company.stock_code} ({year}년, {rc}) - {e}"
                    )
                    continue
            except Exception as e:
                logger.warning(
                    f"재무제표 동기화 중 오류: {company.stock_code} ({year}년, {rc}) - {e}"
                )
                continue

        logger.info(
            f"재무제표 동기화 완료: {company.stock_code} ({year}년, {len(all_statements)}개 보고서)"
        )

        return all_statements

    def _sync_single_financial_statement(
        self, company: Company, year: int, report_code: str
    ) -> Optional[FinancialStatement]:
        """
        단일 보고서 코드의 재무제표 조회 및 저장

        Args:
            company: Company 인스턴스
            year: 사업연도
            report_code: 보고서 코드

        Returns:
            생성/업데이트된 FinancialStatement 인스턴스 또는 None
        """
        try:
            # DART API에서 재무제표 조회
            data = self.dart_client.get_financial_statements(
                company.corp_code, str(year), report_code
            )

            # DART API 응답에서 재무 지표 추출
            # DART API는 여러 계정과목을 리스트로 반환
            # 주요 계정과목 코드:
            # - 매출액: ifrs-full_Revenue
            # - 영업이익: ifrs-full_OperatingIncomeLoss
            # - 당기순이익: ifrs-full_ProfitLoss
            # - 총자산: ifrs-full_Assets
            # - 총부채: ifrs-full_Liabilities
            # - 총자본: ifrs-full_Equity

            financial_data = self._extract_financial_data(data.get("list", []))

            # 추출된 데이터 로깅
            logger.debug(
                f"추출된 재무 데이터: {company.stock_code} ({year}년, {report_code}) - {financial_data}"
            )

            # FinancialStatement 저장 또는 업데이트
            # update_or_create의 defaults에는 None도 명시적으로 포함해야 업데이트됨
            defaults_dict = {}
            for key in [
                "revenue",
                "operating_profit",
                "net_income",
                "total_assets",
                "total_liabilities",
                "total_equity",
            ]:
                if key in financial_data:
                    defaults_dict[key] = financial_data[key]
                # None도 명시적으로 포함 (null로 업데이트하기 위해)
                else:
                    defaults_dict[key] = None

            financial_statement, created = FinancialStatement.objects.update_or_create(
                company=company,
                fiscal_year=year,
                report_code=report_code,
                defaults=defaults_dict,
            )

            action = "생성" if created else "업데이트"
            logger.debug(
                f"재무제표 {action} 완료: {company.stock_code} ({year}년, {report_code})"
            )

            return financial_statement

        except DartAPIError as e:
            logger.error(f"DART API 오류 (재무제표 조회): {e}")
            raise
        except Exception as e:
            logger.error(f"재무제표 동기화 중 오류 발생: {e}")
            raise

    def _extract_financial_data(
        self, account_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        DART API 응답에서 주요 재무 지표 추출

        Args:
            account_list: DART API 응답의 list 필드 (계정과목 리스트)

        Returns:
            재무 지표 딕셔너리
        """
        financial_data = {}

        # 계정과목 코드 매핑
        # 실제 DART API에서 사용하는 계정과목 코드 (test_dart_financial.py로 확인)
        # 보고서 타입이나 기업에 따라 다른 코드를 사용할 수 있으므로 여러 코드 지원
        account_code_map = {
            "ifrs-full_Revenue": "revenue",  # 매출액
            "ifrs-full_ProfitLossFromOperatingActivities": "operating_profit",  # 영업이익
            "dart_OperatingIncomeLoss": "operating_profit",  # 영업이익 (DART 코드)
            "ifrs-full_ProfitLoss": "net_income",  # 당기순이익
            "ifrs-full_Assets": "total_assets",  # 총자산
            "ifrs-full_Liabilities": "total_liabilities",  # 총부채
            "ifrs-full_Equity": "total_equity",  # 총자본
        }

        for account in account_list:
            account_nm = account.get("account_nm", "")
            account_id = account.get("account_id", "")
            thstrm_amount = account.get("thstrm_amount", "")  # 당기금액

            # 계정과목 코드로 매핑
            if account_id in account_code_map:
                key = account_code_map[account_id]
                # 이미 값이 있으면 건너뛰기 (첫 번째 유효한 값만 사용)
                if key in financial_data:
                    continue
                # 금액 문자열을 정수로 변환 (예: "302231000000000" -> 302231000000000)
                try:
                    if thstrm_amount and thstrm_amount != "":
                        value = int(thstrm_amount)
                        # 0이 아닌 값만 저장 (0 값은 무시)
                        if value != 0:
                            financial_data[key] = value
                            logger.debug(
                                f"재무 지표 추출: {key} = {value} ({account_nm}, {account_id})"
                            )
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Invalid amount format: {account_nm} ({account_id}) = {thstrm_amount}, error: {e}"
                    )

        return financial_data

    def sync_revenue_composition(
        self, company: Company, year: int
    ) -> List[RevenueComposition]:
        """
        매출 구성 데이터 동기화
        주의: DART API에서 직접 매출 구성을 제공하지 않으므로,
        사업보고서의 사업부문별 매출 정보를 별도로 파싱해야 함.
        현재는 기본 구조만 제공.

        Args:
            company: Company 인스턴스
            year: 사업연도

        Returns:
            RevenueComposition 인스턴스 리스트
        """
        # TODO: 사업보고서 원문에서 매출 구성 정보 추출 필요
        # 현재는 빈 리스트 반환
        logger.warning(
            f"매출 구성 동기화는 아직 구현되지 않았습니다. {company.stock_code} ({year}년)"
        )
        return []

    def get_financial_statements(
        self, company: Company, years: Optional[List[int]] = None
    ) -> List[FinancialStatement]:
        """
        기업의 재무제표 조회

        Args:
            company: Company 인스턴스
            years: 조회할 연도 리스트 (None이면 최근 3년)

        Returns:
            FinancialStatement 인스턴스 리스트
        """
        if years is None:
            # 최근 3년 조회
            current_year = datetime.now().year
            years = [current_year - i for i in range(3)]

        financial_statements = FinancialStatement.objects.filter(
            company=company, fiscal_year__in=years
        ).order_by("-fiscal_year", "-report_code")

        return list(financial_statements)

    def get_revenue_composition(
        self, company: Company, year: Optional[int] = None
    ) -> List[RevenueComposition]:
        """
        기업의 매출 구성 조회

        Args:
            company: Company 인스턴스
            year: 조회할 연도 (None이면 최신 연도)

        Returns:
            RevenueComposition 인스턴스 리스트
        """
        if year is None:
            # 최신 연도 조회
            latest = (
                RevenueComposition.objects.filter(company=company)
                .order_by("-fiscal_year")
                .first()
            )
            if latest:
                year = latest.fiscal_year
            else:
                return []

        revenue_compositions = RevenueComposition.objects.filter(
            company=company, fiscal_year=year
        ).order_by("-revenue")

        return list(revenue_compositions)
