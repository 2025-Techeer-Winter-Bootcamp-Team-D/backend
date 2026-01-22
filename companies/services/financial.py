# companies/services/financial.py
"""
재무 지표 서비스
DART API를 통해 재무제표를 조회하고 FinancialStatement, RevenueComposition 모델에 저장하는 서비스
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

from companies.models import Company, FinancialStatement, RevenueComposition
from companies.services.dart_api import DartAPIClient, DartAPIError

logger = logging.getLogger(__name__)


class FinancialService:
    """재무 지표 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    @staticmethod
    def _normalize_unit(value: int, unit_info: Optional[str] = None) -> int:
        """
        재무 데이터 단위 정규화 (천원/백만원 -> 원 단위)

        DART API는 일반적으로 원 단위로 제공하지만, 일부는 천원 단위일 수 있음.
        단위 정보는 응답의 currency 필드나 별도 단위 필드에서 확인 가능.

        Args:
            value: 금액 값
            unit_info: 단위 정보 (예: "천원", "백만원", "원", "KRW")

        Returns:
            원 단위로 정규화된 값
        """
        if not value or value == 0:
            return value

        # unit_info가 없는 경우 기본값으로 처리 (DART API는 대부분 원 단위)
        if not unit_info:
            return value

        unit_info_lower = str(unit_info).lower().strip()

        # 단위 변환 (원 단위로 통일)
        if (
            "천원" in unit_info_lower
            or "thousand" in unit_info_lower
            or "k" == unit_info_lower
        ):
            return value * 1000
        elif (
            "백만원" in unit_info_lower
            or "million" in unit_info_lower
            or "m" == unit_info_lower
        ):
            return value * 1000000
        elif "억원" in unit_info_lower or "hundred million" in unit_info_lower:
            return value * 100000000
        elif (
            "원" in unit_info_lower
            or "krw" in unit_info_lower
            or "won" in unit_info_lower
        ):
            # 원 단위는 그대로 반환
            return value
        else:
            # 알 수 없는 단위는 원 단위로 가정 (기본값)
            logger.debug(f"알 수 없는 단위 정보: {unit_info}, 원 단위로 가정")
            return value

    @staticmethod
    def _validate_financial_data(
        financial_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        재무 데이터 유효성 검증 (Sanity Check)

        검증 항목:
        1. 회계 등식: total_assets == total_liabilities + total_equity (오차 1% 허용)
        2. 매출액-영업이익 관계: revenue >= operating_profit (영업이익은 매출액보다 클 수 없음)
        3. 영업이익-당기순이익 관계: operating_profit >= net_income (일반적으로)
        4. 자산/부채/자본은 양수여야 함 (음수는 특수한 경우에만 가능)
        5. 극단값 검증 (비정상적으로 큰 값 체크)

        Args:
            financial_data: 검증할 재무 데이터 딕셔너리

        Returns:
            (is_valid, error_message) 튜플
        """
        total_assets = financial_data.get("total_assets")
        total_liabilities = financial_data.get("total_liabilities")
        total_equity = financial_data.get("total_equity")
        revenue = financial_data.get("revenue")
        operating_profit = financial_data.get("operating_profit")
        net_income = financial_data.get("net_income")

        # 극단값 검증 (비정상적으로 큰 값 체크)
        MAX_REASONABLE_VALUE = 10**18  # 1경원 (극단값 임계값)
        for key, value in financial_data.items():
            if value is not None and abs(value) > MAX_REASONABLE_VALUE:
                error_msg = f"극단값 발견: {key} = {value:,}원 (임계값: {MAX_REASONABLE_VALUE:,}원)"
                logger.warning(error_msg)
                # 극단값은 경고만 출력하고 검증은 통과 (데이터 오류일 수 있지만 저장은 허용)

        # 1. 회계 등식 검증: total_assets == total_liabilities + total_equity
        if (
            total_assets is not None
            and total_liabilities is not None
            and total_equity is not None
        ):
            if total_assets > 0:
                expected_sum = total_liabilities + total_equity
                # 오차 범위 1% 허용 (회계 처리 차이, 반올림 오차 등)
                tolerance = abs(total_assets) * 0.01
                difference = abs(total_assets - expected_sum)

                if difference > tolerance:
                    error_msg = (
                        f"회계 등식 위배: total_assets ({total_assets:,}) != "
                        f"total_liabilities ({total_liabilities:,}) + total_equity ({total_equity:,}). "
                        f"차이: {difference:,}원 (허용 오차: {tolerance:,.0f}원, "
                        f"오차율: {difference/abs(total_assets)*100:.2f}%)"
                    )
                    return False, error_msg
            elif total_assets < 0:
                # 자산이 음수인 경우는 특수한 경우이지만 경고
                logger.warning(
                    f"자산이 음수: total_assets = {total_assets:,}원 (특수한 경우일 수 있음)"
                )

        # 2. revenue >= operating_profit 검증
        # 영업이익은 매출액보다 클 수 없음 (영업이익이 음수일 수는 있음)
        if revenue is not None and operating_profit is not None:
            # revenue는 양수여야 함
            if revenue > 0:
                # operating_profit이 revenue보다 크면 잘못된 데이터
                if operating_profit > revenue:
                    error_msg = (
                        f"매출액-영업이익 관계 위배: revenue ({revenue:,}) < "
                        f"operating_profit ({operating_profit:,})"
                    )
                    return False, error_msg
            elif revenue < 0:
                # 매출액이 음수인 경우는 특수한 경우이지만 경고
                logger.warning(
                    f"매출액이 음수: revenue = {revenue:,}원 (특수한 경우일 수 있음)"
                )

        # 3. operating_profit >= net_income 검증 (일반적으로)
        # 당기순이익은 영업이익보다 클 수 있음 (영업외수익 등)
        # 하지만 일반적으로 영업이익 >= 당기순이익 (세금, 영업외비용 등)
        # 이 검증은 경고만 출력 (데이터 오류일 수 있지만 저장은 허용)
        if operating_profit is not None and net_income is not None:
            if operating_profit > 0 and net_income > operating_profit * 1.5:
                # 당기순이익이 영업이익보다 50% 이상 크면 의심스러움
                logger.warning(
                    f"영업이익-당기순이익 관계 의심: operating_profit ({operating_profit:,}) < "
                    f"net_income ({net_income:,}) (영업외수익이 큰 경우일 수 있음)"
                )

        # 4. 필수 필드 존재 여부 검증 (경고만)
        required_fields = [
            "revenue",
            "operating_profit",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
        ]
        missing_fields = [
            field for field in required_fields if financial_data.get(field) is None
        ]
        if missing_fields:
            logger.debug(
                f"재무 데이터 필드 누락: {missing_fields} (일부 기업은 특정 필드가 없을 수 있음)"
            )

        return True, None

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
                - None이면 sync_all_reports에 따라 처리
            sync_all_reports: 모든 보고서 코드 조회 여부 (기본값: False)
                - True: 11011, 11012, 11013, 11014 모두 조회
                - False: report_code만 조회 (기본값: 11011)

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
                # statement가 None이 아니면 추가 (빈 레코드라도 추가)
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
                    # 빈 레코드 생성 (재시도 가능하도록)
                    try:
                        statement = FinancialStatement.objects.update_or_create(
                            company=company,
                            fiscal_year=year,
                            report_code=rc,
                            defaults={
                                "revenue": None,
                                "operating_profit": None,
                                "net_income": None,
                                "total_assets": None,
                                "total_liabilities": None,
                                "total_equity": None,
                            },
                        )[0]
                        all_statements.append(statement)
                    except Exception as save_error:
                        logger.warning(
                            f"빈 레코드 생성 실패: {company.stock_code} ({year}년, {rc}) - {save_error}"
                        )
                    continue
                else:
                    logger.warning(
                        f"재무제표 조회 실패: {company.stock_code} ({year}년, {rc}) - {e}"
                    )
                    # 빈 레코드 생성 시도
                    try:
                        statement = FinancialStatement.objects.update_or_create(
                            company=company,
                            fiscal_year=year,
                            report_code=rc,
                            defaults={
                                "revenue": None,
                                "operating_profit": None,
                                "net_income": None,
                                "total_assets": None,
                                "total_liabilities": None,
                                "total_equity": None,
                            },
                        )[0]
                        all_statements.append(statement)
                    except Exception as save_error:
                        logger.warning(
                            f"빈 레코드 생성 실패: {company.stock_code} ({year}년, {rc}) - {save_error}"
                        )
                    continue
            except Exception as e:
                logger.warning(
                    f"재무제표 동기화 중 오류: {company.stock_code} ({year}년, {rc}) - {e}"
                )
                # 예외 발생 시에도 빈 레코드 생성 시도
                try:
                    statement = FinancialStatement.objects.update_or_create(
                        company=company,
                        fiscal_year=year,
                        report_code=rc,
                        defaults={
                            "revenue": None,
                            "operating_profit": None,
                            "net_income": None,
                            "total_assets": None,
                            "total_liabilities": None,
                            "total_equity": None,
                        },
                    )[0]
                    all_statements.append(statement)
                    logger.info(
                        f"재무제표 빈 레코드 생성 완료 (오류 발생 후): {company.stock_code} ({year}년, {rc})"
                    )
                except Exception as save_error:
                    logger.error(
                        f"빈 레코드 생성도 실패: {company.stock_code} ({year}년, {rc}) - {save_error}"
                    )
                continue

        logger.info(
            f"재무제표 동기화 완료: {company.stock_code} ({year}년, {len(all_statements)}개 보고서)"
        )

        # 재무제표 동기화 후 매출 구성 동기화 (사업보고서만)
        # 사업보고서가 있는 경우에만 매출 구성 동기화 시도
        annual_statement = next(
            (s for s in all_statements if s.report_code == "11011"), None
        )
        if annual_statement:
            try:
                self.sync_revenue_composition(company, year)
            except Exception as e:
                # 매출 구성 동기화 실패는 경고만 출력 (치명적 오류 아님)
                logger.warning(
                    f"매출 구성 동기화 실패: {company.stock_code} ({year}년) - {e}"
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

            # 추출된 데이터 로깅 (검증 전)
            logger.debug(
                f"추출된 재무 데이터 (검증 전): {company.stock_code} "
                f"({year}년, {report_code}) - {financial_data}"
            )

            # 데이터 추출 실패 체크 (모든 필드가 None이거나 비어있는 경우)
            has_data = financial_data and any(
                v is not None and v != 0 for v in financial_data.values()
            )
            if not has_data:
                logger.warning(
                    f"재무 데이터 추출 실패 (모든 필드가 비어있음): {company.stock_code} "
                    f"({year}년, {report_code}) - DART API 응답에 재무 지표가 없을 수 있음"
                )
                # 데이터가 비어있어도 빈 레코드 생성 (나중에 재시도 가능하도록)
                financial_data = {}  # 빈 딕셔너리로 초기화

            # 단위 정규화 (DART API 응답에서 단위 정보 추출 및 정규화)
            # DART API는 일반적으로 원 단위로 제공하지만, 일부는 천원 단위일 수 있음
            # currency 필드는 통화 정보만 제공하고, 단위(원/천원/백만원)는 별도 확인 필요
            # 현재는 기본적으로 원 단위로 가정 (DART API 공식 문서 기준)
            # 필요시 응답의 currency 필드나 별도 단위 필드를 확인하여 정규화 가능

            # 데이터 유효성 검증 (Sanity Check)
            is_valid, error_message = self._validate_financial_data(financial_data)
            if not is_valid:
                # 검증 실패 시 상세 로깅
                logger.warning(
                    f"재무 데이터 유효성 검증 실패 (경고): "
                    f"{company.stock_code} ({year}년, {report_code}) - {error_message}"
                )
                logger.warning(
                    f"검증 실패 상세 데이터: {company.stock_code} ({year}년, {report_code}) - "
                    f"total_assets={financial_data.get('total_assets')}, "
                    f"total_liabilities={financial_data.get('total_liabilities')}, "
                    f"total_equity={financial_data.get('total_equity')}, "
                    f"revenue={financial_data.get('revenue')}, "
                    f"operating_profit={financial_data.get('operating_profit')}"
                )
                # 검증 실패 시에도 부분 데이터 저장 허용 (데이터 누락 방지)
                # 경고만 출력하고 저장은 계속 진행
                logger.warning(
                    f"검증 실패했지만 부분 데이터 저장 진행: {company.stock_code} ({year}년, {report_code})"
                )

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
            data_status = "완전" if has_data else "부분(빈 데이터)"
            logger.info(
                f"재무제표 {action} 완료 ({data_status}): {company.stock_code} ({year}년, {report_code})"
            )

            return financial_statement

        except DartAPIError as e:
            # DART API 오류 시에도 빈 레코드 생성 (재시도 가능하도록)
            error_message = str(e)
            if "013" in error_message or "조회된 데이타가 없습니다" in error_message:
                logger.warning(
                    f"재무제표 데이터 없음 (빈 레코드 생성): {company.stock_code} ({year}년, {report_code}) - {e}"
                )
                # 빈 레코드 생성
                financial_statement, created = (
                    FinancialStatement.objects.update_or_create(
                        company=company,
                        fiscal_year=year,
                        report_code=report_code,
                        defaults={
                            "revenue": None,
                            "operating_profit": None,
                            "net_income": None,
                            "total_assets": None,
                            "total_liabilities": None,
                            "total_equity": None,
                        },
                    )
                )
                action = "생성" if created else "업데이트"
                logger.info(
                    f"재무제표 빈 레코드 {action} 완료: {company.stock_code} ({year}년, {report_code})"
                )
                return financial_statement
            else:
                logger.error(f"DART API 오류 (재무제표 조회): {e}")
                # 다른 DART API 오류는 재시도 가능하도록 예외 발생
                raise
        except Exception as e:
            # 예외 발생 시에도 최소한 빈 레코드라도 저장 (데이터 누락 방지)
            logger.error(
                f"재무제표 동기화 중 오류 발생 (빈 레코드 저장 시도): "
                f"{company.stock_code} ({year}년, {report_code}) - {e}"
            )
            try:
                # 빈 레코드 생성 시도
                financial_statement, created = (
                    FinancialStatement.objects.update_or_create(
                        company=company,
                        fiscal_year=year,
                        report_code=report_code,
                        defaults={
                            "revenue": None,
                            "operating_profit": None,
                            "net_income": None,
                            "total_assets": None,
                            "total_liabilities": None,
                            "total_equity": None,
                        },
                    )
                )
                action = "생성" if created else "업데이트"
                logger.warning(
                    f"재무제표 빈 레코드 {action} 완료 (오류 발생 후): {company.stock_code} ({year}년, {report_code})"
                )
                return financial_statement
            except Exception as save_error:
                # 빈 레코드 저장도 실패하면 예외 발생
                logger.error(
                    f"재무제표 빈 레코드 저장도 실패: {company.stock_code} ({year}년, {report_code}) - {save_error}"
                )
                raise

    def _extract_financial_data(
        self, account_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        DART API 응답에서 주요 재무 지표 추출

        DART API 재무제표 응답 구조:
        - list: 계정과목 리스트
        - 각 항목: account_id (계정과목 코드), account_nm (계정과목명),
                   thstrm_amount (당기금액), frmtrm_amount (전기금액),
                   sj_div (재무제표 구분), currency (통화), ord (정렬순서)

        Args:
            account_list: DART API 응답의 list 필드 (계정과목 리스트)

        Returns:
            재무 지표 딕셔너리 (원 단위)
        """
        financial_data = {}

        # DART API 응답에서 단위 정보 추출 (첫 번째 항목에서 확인)
        # currency 필드는 통화 정보만 제공하고, 단위(원/천원/백만원)는 별도 확인 필요
        # 일반적으로 DART API는 원 단위로 제공하지만, 일부는 천원 단위일 수 있음
        unit_multiplier = 1  # 기본값: 원 단위

        # 계정과목 코드 우선 매핑 (IFRS 기준)
        # DART API 공식 문서 기준 계정과목 코드
        # 우선순위: 특정 계정 > 일반 계정
        account_code_map = {
            # 매출액 관련
            "ifrs-full_Revenue": "revenue",
            "dart_OperatingRevenues": "revenue",  # 영업수익 (금융회사 등)
            "dart_TotalRevenue": "revenue",  # 총수익
            # 영업이익 관련
            # ifrs-full_ProfitLossFromOperatingActivities는 실제 응답에 없을 수 있음
            "ifrs-full_ProfitLossFromOperatingActivities": "operating_profit",
            "dart_OperatingIncomeLoss": "operating_profit",  # DART 코드 (실제 응답에 있음)
            # 당기순이익 관련
            # ifrs-full_ProfitLoss는 여러 번 나타날 수 있음 (총 당기순이익, 지배기업소유주지분, 비지배지분)
            # 지배기업소유주지분을 우선 사용 (주주 관점에서 더 중요)
            "ifrs-full_ProfitLossAttributableToOwnersOfParent": "net_income",  # 지배기업소유주지분 (우선)
            "ifrs-full_ProfitLoss": "net_income",  # 총 당기순이익 (fallback)
            "dart_ProfitLoss": "net_income",  # DART 코드
            # 자산 관련
            "ifrs-full_Assets": "total_assets",
            "dart_TotalAssets": "total_assets",  # DART 코드
            # 부채 관련
            "ifrs-full_Liabilities": "total_liabilities",
            "dart_TotalLiabilities": "total_liabilities",  # DART 코드
            # 자본 관련
            "ifrs-full_Equity": "total_equity",
            "dart_TotalEquity": "total_equity",  # DART 코드
        }

        # 우선순위가 높은 계정 코드 (나중에 덮어쓰지 않도록)
        priority_account_codes = {
            "net_income": "ifrs-full_ProfitLossAttributableToOwnersOfParent",
        }

        # 계정과목명 기반 매핑 (account_id가 없거나 다른 경우 대비)
        # 정확한 매칭을 위해 우선순위와 제외 키워드 명시
        account_nm_patterns = {
            "revenue": {
                "keywords": [
                    "매출액",
                    "매출",
                    "영업수익",
                    "영업수익(손익계산서상)",
                    "수익",
                ],
                "exclude": ["비용", "손실", "지출"],
                "priority": 1,  # 우선순위 (낮을수록 높음)
            },
            "operating_profit": {
                "keywords": ["영업이익", "영업손익"],
                "exclude": ["순이익", "당기순이익", "법인세"],
                "priority": 2,
            },
            "net_income": {
                "keywords": ["당기순이익", "순이익", "당기순손익"],
                "exclude": ["영업이익", "영업손익"],
                "priority": 3,
            },
            "total_assets": {
                "keywords": ["총자산", "자산총계"],
                "exclude": [
                    "부채",
                    "자본",
                    "부채와자본총계",
                    "부채총계",
                    "자본총계",
                ],
                "priority": 1,
            },
            "total_liabilities": {
                "keywords": ["총부채", "부채총계"],
                "exclude": [
                    "자산",
                    "자본",
                    "부채와자본총계",
                    "자산총계",
                    "총자산",
                    "자본총계",
                    "총자본",
                ],
                "priority": 1,
            },
            "total_equity": {
                "keywords": ["자본총계", "총자본"],
                "exclude": [
                    "자본금",  # 자본금은 자본총계가 아님
                    "부채",
                    "자산",
                    "부채와자본총계",
                    "자산총계",
                    "총자산",
                    "부채총계",
                    "총부채",
                ],
                "priority": 1,
            },
        }

        # account_id로 먼저 매핑 시도 (가장 정확)
        for account in account_list:
            account_id = account.get("account_id", "").strip()
            account_nm = account.get("account_nm", "").strip()
            thstrm_amount = account.get("thstrm_amount", "").strip()
            sj_div = account.get(
                "sj_div", ""
            ).strip()  # 재무제표 구분 (BS: 재무상태표, IS: 손익계산서)

            # account_id로 매핑
            if account_id and account_id in account_code_map:
                key = account_code_map[account_id]

                # 우선순위 계정 코드 체크
                # 우선순위가 높은 계정이 이미 매핑되었으면 낮은 우선순위 계정은 스킵
                priority_code = priority_account_codes.get(key)
                if priority_code and priority_code != account_id:
                    # 우선순위 계정이 이미 매핑되었는지 확인
                    if key in financial_data:
                        logger.debug(
                            f"우선순위 계정 이미 매핑됨 (스킵): {account_nm} ({account_id}) - "
                            f"우선순위: {priority_code}"
                        )
                        continue

                # 재무제표 구분 검증 (예: 총자산은 BS에만 있어야 함)
                if key == "total_assets" and sj_div != "BS":
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} ({account_id}) - sj_div: {sj_div}"
                    )
                    continue
                if key == "total_liabilities" and sj_div != "BS":
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} ({account_id}) - sj_div: {sj_div}"
                    )
                    continue
                if key == "total_equity" and sj_div != "BS":
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} ({account_id}) - sj_div: {sj_div}"
                    )
                    continue
                if (
                    key in ["revenue", "operating_profit", "net_income"]
                    and sj_div != "IS"
                ):
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} ({account_id}) - sj_div: {sj_div}"
                    )
                    continue

                # 값 추출 및 저장
                if thstrm_amount and thstrm_amount != "":
                    try:
                        value = int(thstrm_amount) * unit_multiplier

                        # 0이 아닌 값만 고려
                        # ifrs-full_ProfitLoss 등은 여러 번 나타날 수 있음 (지배기업소유주지분, 비지배지분 등)
                        # 우선순위 계정 코드가 있으면 우선 사용, 없으면 가장 큰 절댓값 선택
                        if value != 0:
                            existing_value = financial_data.get(key, 0)

                            # 우선순위 계정 코드인 경우 무조건 사용 (덮어쓰기)
                            if priority_code and priority_code == account_id:
                                financial_data[key] = value
                                logger.debug(
                                    f"재무 지표 추출 (우선순위 account_id): {key} = {value:,}원 "
                                    f"({account_nm}, {account_id}, sj_div: {sj_div})"
                                )
                            # 우선순위 계정이 아니고 이미 값이 있으면 더 큰 절댓값 선택
                            elif key not in financial_data or abs(value) > abs(
                                existing_value
                            ):
                                financial_data[key] = value
                                logger.debug(
                                    f"재무 지표 추출 (account_id): {key} = {value:,}원 "
                                    f"({account_nm}, {account_id}, sj_div: {sj_div})"
                                )
                            elif existing_value != 0:
                                logger.debug(
                                    f"재무 지표 건너뜀 (더 큰 값 존재): {key} = {value:,}원 "
                                    f"(기존값: {existing_value:,}원, {account_nm}, {account_id})"
                                )
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"금액 파싱 실패: {account_nm} ({account_id}) = {thstrm_amount}, 오류: {e}"
                        )

        # account_id 매핑 실패 시 계정과목명으로 매핑 시도
        for account in account_list:
            account_id = account.get("account_id", "").strip()
            account_nm = account.get("account_nm", "").strip()
            thstrm_amount = account.get("thstrm_amount", "").strip()
            sj_div = account.get("sj_div", "").strip()

            # account_id로 이미 매핑된 경우 스킵
            if account_id and account_id in account_code_map:
                continue

            # 계정과목명이 없으면 스킵
            if not account_nm:
                continue

            # 계정과목명 기반 매핑
            matched_key = None
            matched_priority = float("inf")

            for field, pattern in account_nm_patterns.items():
                # 이미 account_id로 매핑된 필드는 스킵
                if field in financial_data:
                    continue

                # 키워드 매칭
                keyword_matched = any(
                    keyword in account_nm for keyword in pattern["keywords"]
                )

                # 제외 키워드 체크
                exclude_matched = any(
                    exclude in account_nm for exclude in pattern["exclude"]
                )

                if keyword_matched and not exclude_matched:
                    # 우선순위가 더 높은 매칭 발견
                    if pattern["priority"] < matched_priority:
                        matched_key = field
                        matched_priority = pattern["priority"]

            # 재무제표 구분 검증
            if matched_key:
                if matched_key == "total_assets" and sj_div != "BS":
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} - sj_div: {sj_div}"
                    )
                    continue
                if matched_key == "total_liabilities" and sj_div != "BS":
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} - sj_div: {sj_div}"
                    )
                    continue
                if matched_key == "total_equity" and sj_div != "BS":
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} - sj_div: {sj_div}"
                    )
                    continue
                if (
                    matched_key in ["revenue", "operating_profit", "net_income"]
                    and sj_div != "IS"
                ):
                    logger.debug(
                        f"재무제표 구분 불일치 (스킵): {account_nm} - sj_div: {sj_div}"
                    )
                    continue

                # 값 추출 및 저장
                if thstrm_amount and thstrm_amount != "":
                    try:
                        value = int(thstrm_amount) * unit_multiplier

                        # 0이 아닌 값만 고려
                        # 계정과목명 매핑도 여러 번 나타날 수 있으므로 가장 큰 절댓값 선택
                        if value != 0:
                            # 이미 값이 있으면 더 큰 절댓값 선택
                            existing_value = financial_data.get(matched_key, 0)
                            if matched_key not in financial_data or abs(value) > abs(
                                existing_value
                            ):
                                financial_data[matched_key] = value
                                logger.debug(
                                    f"재무 지표 추출 (account_nm): {matched_key} = {value:,}원 "
                                    f"({account_nm}, sj_div: {sj_div})"
                                )
                            elif existing_value != 0:
                                logger.debug(
                                    f"재무 지표 건너뜀 (더 큰 값 존재): {matched_key} = {value:,}원 "
                                    f"(기존값: {existing_value:,}원, {account_nm})"
                                )
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"금액 파싱 실패: {account_nm} = {thstrm_amount}, 오류: {e}"
                        )

        return financial_data

    def sync_revenue_composition(
        self, company: Company, year: int
    ) -> List[RevenueComposition]:
        """
        매출 구성 데이터 동기화
        해당 연도의 사업보고서 또는 반기보고서(Report)가 처리되어 있으면 extracted_info에서
        revenue_composition을 추출하여 RevenueComposition 테이블에 저장합니다.
        사업보고서가 우선적으로 사용되며, 없으면 반기보고서를 사용합니다.

        Args:
            company: Company 인스턴스
            year: 사업연도

        Returns:
            RevenueComposition 인스턴스 리스트
        """
        from companies.models import Report

        # 해당 연도의 사업보고서 또는 반기보고서 찾기
        # 우선순위: 사업보고서 > 반기보고서
        # 먼저 사업보고서 찾기
        report = (
            Report.objects.filter(
                company=company,
                report_name__icontains="사업보고서",
                submitted_at__year=year,
                processing_status="completed",
                extracted_info__isnull=False,
            )
            .order_by("-submitted_at")
            .first()
        )

        # 사업보고서가 없으면 반기보고서 찾기
        if not report:
            report = (
                Report.objects.filter(
                    company=company,
                    report_name__icontains="반기보고서",
                    submitted_at__year=year,
                    processing_status="completed",
                    extracted_info__isnull=False,
                )
                .order_by("-submitted_at")
                .first()
            )

        if not report:
            logger.debug(
                f"매출 구성 동기화: 처리된 사업/반기보고서 없음 - {company.stock_code} ({year}년)"
            )
            return []
        extracted_info = report.extracted_info

        if not extracted_info or "revenue_composition" not in extracted_info:
            logger.debug(
                f"매출 구성 동기화: extracted_info에 revenue_composition 없음 - "
                f"{company.stock_code} ({year}년, report_id: {report.id})"
            )
            return []

        revenue_composition_data = extracted_info.get("revenue_composition", [])

        if not revenue_composition_data:
            logger.debug(
                f"매출 구성 동기화: revenue_composition 데이터 없음 - "
                f"{company.stock_code} ({year}년)"
            )
            return []

        saved_compositions = []
        others_segment = None  # "기타" 항목 저장용
        segments_data = []  # (segment_name, revenue, ratio) 튜플 리스트

        # 1단계: 모든 항목 수집 및 파싱
        for segment in revenue_composition_data:
            # 필수 키 검증: segment 필드가 있고 비어있지 않은지 확인
            segment_name = segment.get("segment") if isinstance(segment, dict) else None
            if not segment_name or not str(segment_name).strip():
                logger.warning(
                    f"매출 구성 항목 건너뜀 (segment 누락/비어있음): "
                    f"{company.stock_code} ({year}년), segment_data={segment}"
                )
                continue

            segment_name = str(segment_name).strip()

            # "기타" 항목은 나중에 처리
            if segment_name == "기타":
                others_segment = segment
                continue

            # revenue를 int로 안전하게 변환
            try:
                revenue_value = segment.get("revenue", 0)
                if revenue_value is None:
                    revenue_value = 0
                revenue_value = int(revenue_value)

                # 매출(revenue)은 음수가 될 수 없음 - 마이너스 값은 건너뜀
                if revenue_value < 0:
                    logger.warning(
                        f"매출 구성 항목 건너뜀 (revenue가 마이너스): "
                        f"{company.stock_code} ({year}년), segment={segment_name}, revenue={revenue_value}"
                    )
                    continue
            except (ValueError, TypeError):
                logger.warning(
                    f"매출 구성 항목 revenue 변환 실패, 건너뜀: "
                    f"{company.stock_code} ({year}년), revenue={segment.get('revenue')}"
                )
                continue

            # ratio 파싱
            ratio_value = segment.get("ratio")
            if ratio_value is not None:
                try:
                    # 문자열 "58.1%" 또는 "0.58" 형태 처리
                    if isinstance(ratio_value, str):
                        ratio_value = ratio_value.replace("%", "").strip()
                    ratio_value = float(ratio_value)

                    # 소수점 형태(0.58)인 경우 백분율(58%)로 변환
                    # 1.0을 초과하면 이미 백분율로 간주, 1.0 이하면 소수점으로 간주
                    if ratio_value <= 1.0:
                        ratio_value = ratio_value * 100.0
                        logger.debug(
                            f"매출 구성 ratio 소수점→백분율 변환: {company.stock_code} ({year}년) - "
                            f"{segment_name}: {ratio_value / 100.0} → {ratio_value}%"
                        )
                except (ValueError, TypeError):
                    logger.warning(
                        f"매출 구성 항목 ratio 변환 실패, None 사용: "
                        f"{company.stock_code} ({year}년), ratio={segment.get('ratio')}"
                    )
                    ratio_value = None

            segments_data.append((segment_name, revenue_value, ratio_value))

        # 2단계: ratio 합계 계산 및 정규화 필요 여부 확인
        total_ratio = sum(
            ratio for _, _, ratio in segments_data if ratio is not None and ratio > 0
        )
        total_revenue = sum(revenue for _, revenue, _ in segments_data)

        # ratio 합계가 100%를 초과하면 정규화
        needs_normalization = total_ratio > 100.0
        if needs_normalization:
            logger.warning(
                f"매출 구성비 합계가 100% 초과: {company.stock_code} ({year}년) - "
                f"합계: {total_ratio:.2f}%, 정규화 수행"
            )
            # 각 ratio를 합계로 나누어 100%로 정규화
            normalization_factor = total_ratio / 100.0
            segments_data = [
                (
                    name,
                    revenue,
                    ratio / normalization_factor if ratio is not None else None,
                )
                for name, revenue, ratio in segments_data
            ]
            total_ratio = 100.0

        # 3단계: ratio가 없는 항목은 revenue 기반으로 계산
        segments_without_ratio = [
            (name, revenue) for name, revenue, ratio in segments_data if ratio is None
        ]
        if segments_without_ratio and total_revenue > 0:
            for name, revenue in segments_without_ratio:
                calculated_ratio = (revenue / total_revenue) * 100.0
                # 해당 항목의 ratio 업데이트
                segments_data = [
                    (n, r, calculated_ratio if n == name else ratio)
                    for n, r, ratio in segments_data
                ]
                total_ratio += calculated_ratio

        # 4단계: DB에 저장
        for segment_name, revenue_value, ratio_value in segments_data:
            # ratio 소수점 2자리로 반올림
            if ratio_value is not None:
                ratio_value = round(ratio_value, 2)

            composition, created = RevenueComposition.objects.update_or_create(
                company=company,
                fiscal_year=year,
                segment_name=segment_name,
                defaults={
                    "revenue": revenue_value,
                    "ratio": ratio_value,
                },
            )
            saved_compositions.append(composition)

            action = "생성" if created else "업데이트"
            logger.debug(
                f"매출 구성 {action}: {company.stock_code} ({year}년) - "
                f"{segment_name}: {revenue_value:,}원 ({ratio_value}%)"
            )

        # 5단계: "기타" 항목 처리 (정규화 후 total_ratio 사용)
        if others_segment:
            segment_name = "기타"
            # 정규화 후 total_ratio는 100.0이므로, 기타 항목은 0이 됨
            # 하지만 원본 데이터에 기타 항목이 있으면 저장
            others_ratio = max(0.0, 100.0 - total_ratio)  # 최소 0

            # ratio가 0이면 저장하지 않음
            if others_ratio <= 0:
                logger.debug(
                    f"매출 구성 기타 항목 제외 (ratio가 0): "
                    f"{company.stock_code} ({year}년), 계산값: 100 - {total_ratio:.2f} = {others_ratio:.2f}"
                )
            else:
                # revenue는 원본 데이터 사용 (마이너스여도 상관없음 - ratio만 계산)
                try:
                    revenue_value = others_segment.get("revenue", 0)
                    if revenue_value is None:
                        revenue_value = 0
                    else:
                        revenue_value = int(revenue_value)
                        # 마이너스면 0으로 설정 (매출은 음수가 될 수 없음)
                        if revenue_value < 0:
                            revenue_value = 0
                except (ValueError, TypeError):
                    revenue_value = 0

                # RevenueComposition 저장 또는 업데이트
                composition, created = RevenueComposition.objects.update_or_create(
                    company=company,
                    fiscal_year=year,
                    segment_name=segment_name,
                    defaults={
                        "revenue": revenue_value,
                        "ratio": round(others_ratio, 2),  # 소수점 2자리로 반올림
                    },
                )
                saved_compositions.append(composition)

                action = "생성" if created else "업데이트"
                logger.debug(
                    f"매출 구성 {action} (기타): {company.stock_code} ({year}년) - "
                    f"{segment_name}: {revenue_value:,}원 "
                    f"(ratio: {round(others_ratio, 2)}%, 계산값: 100 - {total_ratio:.2f})"
                )

        logger.info(
            f"매출 구성 동기화 완료: {company.stock_code} ({year}년) - "
            f"{len(saved_compositions)}개 부문 저장"
        )

        return saved_compositions

    def get_financial_statements(
        self,
        company: Company,
        years: Optional[int] = None,
        report_code: Optional[str] = None,
    ) -> List[FinancialStatement]:
        """
        기업의 재무제표 조회

        Args:
            company: Company 인스턴스
            years: 조회할 최근 연도 수 (None이면 최근 3년, 예: 3이면 최근 3년치)
            report_code: 보고서 코드 필터 (None이면 모든 보고서, "11011"이면 사업보고서만)

        Returns:
            FinancialStatement 인스턴스 리스트
        """
        if years is None:
            years = 3  # 기본값: 최근 3년

        # 최근 N년치 연도 리스트 생성
        current_year = datetime.now().year
        year_list = [current_year - i for i in range(years)]

        queryset = FinancialStatement.objects.filter(
            company=company, fiscal_year__in=year_list
        )

        # 보고서 코드 필터링 (기본값: 사업보고서만)
        if report_code:
            queryset = queryset.filter(report_code=report_code)
        else:
            # 기본값: 사업보고서(11011)만 조회하여 중복 데이터 방지
            queryset = queryset.filter(report_code="11011")

        financial_statements = queryset.order_by("-fiscal_year", "-report_code")

        return list(financial_statements)

    def get_revenue_composition(
        self, company: Company, year: Optional[int] = None
    ) -> List[RevenueComposition]:
        """
        기업의 매출 구성 조회

        Args:
            company: Company 인스턴스
            year: 조회할 연도 (None이면 최신 연도, 해당 연도 데이터 없으면 사용 가능한 최신 연도 반환)

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

        # 지정된 연도의 데이터 조회
        revenue_compositions = RevenueComposition.objects.filter(
            company=company, fiscal_year=year
        ).order_by("-revenue")

        if revenue_compositions.exists():
            return list(revenue_compositions)

        # 해당 연도 데이터가 없으면 사용 가능한 최신 연도 반환
        latest = (
            RevenueComposition.objects.filter(company=company)
            .order_by("-fiscal_year")
            .first()
        )
        if latest:
            logger.debug(
                f"매출 구성: {year}년 데이터 없음, {latest.fiscal_year}년 데이터 반환"
            )
            return list(
                RevenueComposition.objects.filter(
                    company=company, fiscal_year=latest.fiscal_year
                ).order_by("-revenue")
            )

        return []
