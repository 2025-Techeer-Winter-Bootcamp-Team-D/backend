# companies/services/company_info.py
"""
기업 기본 정보 서비스
DART API를 통해 기업 기본 정보를 조회하고 Company 모델에 저장하는 서비스
KIS REST API를 통해 시가총액을 갱신하는 기능 포함
"""
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from companies.models import Company
from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.services.kis_quote import get_market_amount, get_kis_quote_client
from companies.services.logo import get_logo_url

logger = logging.getLogger(__name__)


class CompanyInfoService:
    """기업 기본 정보 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    def sync_company_info(self, company: Company) -> Company:
        """
        DART API에서 기업 기본 정보를 조회하여 Company 모델 업데이트
        KIS REST API를 통해 시가총액도 함께 갱신

        Args:
            company: 업데이트할 Company 인스턴스

        Returns:
            업데이트된 Company 인스턴스

        Raises:
            DartAPIError: DART API 호출 실패 시
            ValueError: corp_code가 없는 경우
        """
        if not company.corp_code:
            raise ValueError(
                f"Company {company.stock_code}에 corp_code가 설정되지 않았습니다."
            )

        try:
            # DART API에서 기업개황 조회
            data = self.dart_client.get_company_info(company.corp_code)

            # DART API 응답 데이터 매핑
            # DART API 응답 필드명: corp_name, ceo_nm, est_dt, hm_url, adres, induty_code 등
            if data.get("corp_name"):
                company.company_name = data["corp_name"]
            if data.get("ceo_nm"):
                company.ceo_name = data["ceo_nm"]
            if data.get("est_dt"):
                # est_dt 형식: "19690113" (YYYYMMDD)
                try:
                    company.establishment_date = datetime.strptime(
                        data["est_dt"], "%Y%m%d"
                    ).date()
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid establishment_date format: {data.get('est_dt')}"
                    )
            if data.get("hm_url"):
                company.homepage_url = data["hm_url"]
            if data.get("adres"):
                company.address = data["adres"]

            # 시장 구분 매핑 (corp_cls → market)
            # DART API corp_cls: Y(유가증권/KOSPI), K(코스닥/KOSDAQ)
            corp_cls = data.get("corp_cls")
            if corp_cls:
                market_mapping = {
                    "Y": "KOSPI",
                    "K": "KOSDAQ",
                }
                market = market_mapping.get(corp_cls)
                if market:
                    company.market = market
                    logger.info(
                        f"시장 구분 매핑: {company.stock_code} → {corp_cls} → {market}"
                    )
                else:
                    logger.warning(
                        f"지원하지 않는 시장 구분: {company.stock_code} → corp_cls={corp_cls}"
                    )

            # 업종코드는 sync_corp_codes에서만 관리하므로 여기서는 저장하지 않음

            # KIS REST API를 통해 시가총액 갱신 (실패해도 전체 동기화는 계속)
            market_amount_synced = False
            try:
                market_amount_synced = self._sync_market_amount(company)
                if market_amount_synced:
                    logger.info(
                        f"시가총액 갱신 성공: {company.stock_code} → {company.market_amount:,}원"
                    )
                else:
                    logger.warning(
                        f"시가총액 갱신 실패 (값 없음): {company.stock_code} - 기존 값 유지"
                    )
            except Exception as e:
                # 시가총액 갱신 실패는 일시적 오류일 수 있으므로 로그만 남기고 계속 진행
                logger.warning(
                    f"시가총액 갱신 실패 (기업 정보 동기화는 계속 진행): "
                    f"{company.stock_code} - {e}"
                )

            # Logo.dev를 통해 로고 URL 갱신
            self._sync_logo_url(company)

            # 마지막 정보 동기화 시간 업데이트 (시가총액 갱신은 제외)
            from django.utils import timezone

            company.last_info_synced_at = timezone.now()

            company.save()
            logger.info(
                f"기업 정보 동기화 완료: {company.stock_code} ({company.company_name})"
            )

            return company

        except DartAPIError as e:
            logger.error(f"DART API 오류 (기업 정보 조회): {e}")
            raise
        except Exception as e:
            logger.error(f"기업 정보 동기화 중 오류 발생: {e}")
            raise

    def _sync_market_amount(self, company: Company) -> bool:
        """
        KIS REST API를 통해 시가총액을 갱신 (내부 헬퍼)

        Args:
            company: Company 인스턴스

        Returns:
            갱신 성공 여부

        Raises:
            requests.RequestException: 네트워크 오류, 타임아웃, HTTP 5xx 등 일시적 오류
            requests.HTTPError: HTTP 5xx 서버 오류
            requests.Timeout: 요청 타임아웃
        """
        import requests

        # KIS 클라이언트를 직접 호출하여 일시적 오류를 감지할 수 있도록 함
        client = get_kis_quote_client()

        try:
            # get_stock_quote_or_raise를 사용하여 일시적 오류 시 예외 발생
            quote = client.get_stock_quote_or_raise(company.stock_code)

            if not quote:
                # 데이터 없음은 비일시적 오류로 간주 (재시도 불필요)
                logger.warning(
                    f"시가총액 조회 실패 (값 없음): {company.stock_code} - 기존 값 유지"
                )
                return False

            # hts_avls: HTS 시가총액 (억 단위)
            hts_avls = quote.get("hts_avls")
            if not hts_avls:
                logger.warning(
                    f"시가총액 필드(hts_avls) 없음: {company.stock_code} - 기존 값 유지"
                )
                return False

            try:
                # 억 단위 → 원 단위 변환
                market_amount = int(hts_avls.replace(",", "")) * 100_000_000
                company.market_amount = market_amount
                logger.info(
                    f"시가총액 갱신: {company.stock_code} → {market_amount:,}원"
                )
                return True
            except (ValueError, AttributeError) as e:
                # 파싱 오류는 비일시적 오류로 간주
                logger.error(
                    f"시가총액 파싱 실패 ({company.stock_code}): {hts_avls}, {e}"
                )
                return False

        except (requests.RequestException, requests.HTTPError, requests.Timeout) as e:
            # 네트워크 오류, 타임아웃, HTTP 5xx 등 일시적 오류는 재시도 가능하므로 재발생
            logger.warning(
                f"시가총액 갱신 중 일시적 오류 ({company.stock_code}): {e} - 재시도 예정"
            )
            raise
        except Exception as e:
            # 예상치 못한 오류도 재시도 가능하도록 재발생
            logger.error(
                f"시가총액 갱신 중 예상치 못한 오류 ({company.stock_code}): {e}"
            )
            raise

    def _sync_logo_url(self, company: Company) -> bool:
        """
        Logo.dev를 통해 로고 URL을 갱신 (내부 헬퍼)

        Args:
            company: Company 인스턴스

        Returns:
            갱신 성공 여부
        """
        # 이미 logo_url이 있으면 스킵
        if company.logo_url:
            return True

        if not company.homepage_url:
            logger.debug(
                f"로고 URL 갱신 스킵 (homepage_url 없음): {company.stock_code}"
            )
            return False

        try:
            logo_url = get_logo_url(homepage_url=company.homepage_url)
            if logo_url:
                company.logo_url = logo_url
                logger.info(f"로고 URL 갱신: {company.stock_code} → {logo_url}")
                return True
            else:
                logger.warning(f"로고 URL 생성 실패: {company.stock_code}")
                return False
        except Exception as e:
            logger.error(f"로고 URL 갱신 중 오류 ({company.stock_code}): {e}")
            return False

    def sync_market_amount_only(self, company: Company) -> bool:
        """
        시가총액만 단독으로 갱신 (DART 동기화 없이)

        주의: updated_at이나 last_info_synced_at은 업데이트하지 않음
        (시가총액 갱신은 정보 동기화로 간주하지 않음)

        Args:
            company: Company 인스턴스

        Returns:
            갱신 성공 여부
        """
        success = self._sync_market_amount(company)
        if success:
            # market_amount만 업데이트 (updated_at, last_info_synced_at 제외)
            company.save(update_fields=["market_amount"])
        return success

    def get_company_info_dict(self, company: Company) -> Dict[str, Any]:
        """
        Company 모델 데이터를 딕셔너리로 반환

        Args:
            company: Company 인스턴스

        Returns:
            기업 정보 딕셔너리
        """
        return {
            "stock_code": company.stock_code,
            "corp_code": company.corp_code,
            "company_name": company.company_name,
            "market": company.market,
            "description": company.description,
            "logo_url": company.logo_url,
            "market_amount": company.market_amount,
            "ceo_name": company.ceo_name,
            "establishment_date": (
                company.establishment_date.isoformat()
                if company.establishment_date
                else None
            ),
            "homepage_url": company.homepage_url,
            "address": company.address,
        }
