"""
배당 정보 동기화 서비스
"""

from decimal import Decimal, InvalidOperation
import logging
import re
from typing import List

from companies.models import Company, Dividend
from companies.services.dart_api import DartAPIClient, DartAPIError

logger = logging.getLogger(__name__)


class DividendService:
    """배당 정보 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    def sync_dividend_info(self, company: Company, year: int) -> List[Dividend]:
        """
        DART API에서 배당 정보를 조회하여 저장

        Args:
            company: Company 인스턴스
            year: 사업연도

        Returns:
            생성/업데이트된 Dividend 인스턴스 리스트
        """
        if not company.corp_code:
            raise ValueError(f"Company {company.stock_code}에 corp_code가 없습니다.")

        try:
            # DART API 호출
            data = self.dart_client.get_dividend_info(
                corp_code=company.corp_code,
                bsns_year=str(year),
                reprt_code="11011",  # 사업보고서
            )

            dividend_list = data.get("list", [])
            if not dividend_list:
                logger.info(f"배당 정보 없음: {company.stock_code} ({year}년)")
                return []

            # 디버깅: 첫 번째 아이템의 구조 로깅
            if dividend_list:
                logger.debug(
                    f"배당 정보 응답 구조 ({company.stock_code}): {dividend_list[0].keys()}"
                )

            dividends = []
            for item in dividend_list:
                try:
                    # DART API 배당 정보 응답 필드:
                    # - se: 구분 (예: "주당 현금배당금(원)", "현금배당금총액(원)", "현금배당성향(%)")
                    # - stock_knd: 주식 종류 (예: "보통주", "우선주")
                    # - thstrm: 당기 배당금
                    # - frmtrm: 전기 배당금
                    # - lwfr: 전전기 배당금

                    # se 필드로 "주당 현금배당금" 행만 필터링
                    se = item.get("se", "")
                    if "주당" not in se or "배당" not in se:
                        # 주당 배당금이 아닌 행은 스킵 (총액, 성향 등)
                        logger.debug(
                            f"주당 배당금 아님 (스킵): {company.stock_code} ({year}년) - se: {se}"
                        )
                        continue

                    # 주식 종류 확인 (보통주만 저장)
                    stock_knd = item.get("stock_knd", "")
                    if stock_knd and "우선주" in stock_knd:
                        logger.debug(
                            f"우선주 배당 정보 스킵: {company.stock_code} ({year}년) - {stock_knd}"
                        )
                        continue

                    # 주당 배당금 파싱 (당기 배당금 사용)
                    dividend_per_share_str = item.get("thstrm", "0")

                    # 문자열 정제: 쉼표, "원" 제거, 공백 제거
                    dividend_per_share_str = str(dividend_per_share_str).strip()
                    dividend_per_share_str = (
                        dividend_per_share_str.replace(",", "")
                        .replace("원", "")
                        .replace(" ", "")
                        .replace("\xa0", "")  # non-breaking space 제거
                    )

                    # 빈 문자열이거나 숫자가 아닌 경우 0으로 처리
                    if (
                        not dividend_per_share_str
                        or dividend_per_share_str == "-"
                        or dividend_per_share_str.lower() == "null"
                        or dividend_per_share_str == ""
                    ):
                        dividend_per_share = Decimal("0")
                    else:
                        # 숫자 외 문자 제거 (소수점은 유지)
                        dividend_per_share_str = re.sub(
                            r"[^\d.]", "", dividend_per_share_str
                        )
                        if not dividend_per_share_str:
                            dividend_per_share = Decimal("0")
                        else:
                            dividend_per_share = Decimal(dividend_per_share_str)

                    # 배당금이 0이면 건너뛰기 (배당 없음)
                    if dividend_per_share == 0:
                        logger.debug(
                            f"배당 없음 (0원): {company.stock_code} ({year}년)"
                        )
                        continue

                    # 배당 유형 (DART API 응답에 따라 조정 필요)
                    # 일반적으로 현금배당만 기록
                    dividend_type = "cash"

                    dividend, created = Dividend.objects.update_or_create(
                        company=company,
                        fiscal_year=year,
                        dividend_type=dividend_type,
                        defaults={
                            "dividend_per_share": dividend_per_share,
                        },
                    )
                    dividends.append(dividend)

                    if created:
                        logger.info(
                            f"배당 정보 생성: {company.stock_code} ({year}년) - {dividend_per_share}원"
                        )
                    else:
                        logger.info(
                            f"배당 정보 업데이트: {company.stock_code} ({year}년) - {dividend_per_share}원"
                        )

                except (KeyError, ValueError, InvalidOperation) as e:
                    logger.warning(
                        f"배당 데이터 파싱 오류: {company.stock_code} ({year}년) - "
                        f"에러: {e}, 원본 데이터: {item}"
                    )
                    continue

            logger.info(
                f"배당 정보 동기화 완료: {company.stock_code} ({year}년, {len(dividends)}건)"
            )
            return dividends

        except DartAPIError as e:
            logger.error(f"DART API 오류 (배당 정보): {e}")
            raise
