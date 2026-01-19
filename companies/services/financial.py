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

        # 금융회사 등 특수한 경우를 위한 account_id 매핑 추가
        # 금융회사는 매출액 대신 영업수익 등을 사용할 수 있음
        account_code_map_extended = {
            **account_code_map,
            # 금융회사 매출 관련 계정과목 코드 (추가 가능)
            "dart_TotalRevenue": "revenue",  # 총수익
            "dart_OperatingRevenues": "revenue",  # 영업수익
        }

        # 계정과목명 기반 매핑 (account_id가 없거나 다른 경우 대비)
        account_nm_keywords = {
            "revenue": ["매출액", "매출", "영업수익", "영업수익(손익계산서상)", "수익"],
            "operating_profit": ["영업이익", "영업손익"],
            "net_income": ["당기순이익", "순이익", "당기순손익"],
            "total_assets": ["총자산", "자산총계"],
            "total_liabilities": ["총부채", "부채총계"],
            "total_equity": ["총자본", "자본총계", "자본"],
        }

        for account in account_list:
            account_nm = account.get("account_nm", "")
            account_id = account.get("account_id", "")
            thstrm_amount = account.get("thstrm_amount", "")  # 당기금액

            # 계정과목 코드로 먼저 매핑 시도
            key = None
            if account_id in account_code_map_extended:
                key = account_code_map_extended[account_id]
            # account_id 매핑 실패 시 계정과목명으로 매핑 시도
            elif account_nm:
                account_nm_upper = account_nm.upper()
                for field, keywords in account_nm_keywords.items():
                    # 이미 값이 있으면 건너뛰기 (첫 번째 유효한 값만 사용)
                    if field in financial_data:
                        continue
                    for keyword in keywords:
                        if keyword in account_nm or keyword.upper() in account_nm_upper:
                            key = field
                            break
                    if key:
                        break

            if key:
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
        total_ratio = 0.0  # 나머지 항목들의 ratio 합

        # 먼저 "기타" 항목을 제외한 나머지 항목 처리
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

            # ratio가 숫자 또는 None인지 검증
            ratio_value = segment.get("ratio")
            if ratio_value is not None:
                try:
                    # 문자열 "58.1%" 형태 처리
                    if isinstance(ratio_value, str):
                        ratio_value = ratio_value.replace("%", "").strip()
                    ratio_value = float(ratio_value)
                    # 유효한 ratio만 합산
                    if ratio_value > 0:
                        total_ratio += ratio_value
                except (ValueError, TypeError):
                    logger.warning(
                        f"매출 구성 항목 ratio 변환 실패, None 사용: "
                        f"{company.stock_code} ({year}년), ratio={segment.get('ratio')}"
                    )
                    ratio_value = None

            # RevenueComposition 저장 또는 업데이트
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

        # "기타" 항목 처리: ratio를 100 - (나머지 ratio 합)으로 계산
        # ratio가 0이면 저장하지 않음
        if others_segment:
            segment_name = "기타"
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
                    f"{segment_name}: {revenue_value:,}원 (ratio: {round(others_ratio, 2)}%, 계산값: 100 - {total_ratio:.2f})"
                )

        logger.info(
            f"매출 구성 동기화 완료: {company.stock_code} ({year}년) - "
            f"{len(saved_compositions)}개 부문 저장"
        )

        return saved_compositions

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
