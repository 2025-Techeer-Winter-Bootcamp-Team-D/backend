# companies/services/company_info.py
"""
기업 기본 정보 서비스
DART API를 통해 기업 기본 정보를 조회하고 Company 모델에 저장하는 서비스
"""
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from companies.models import Company
from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.services.industry_mapper import IndustryMapper

logger = logging.getLogger(__name__)


class CompanyInfoService:
    """기업 기본 정보 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    def sync_company_info(self, company: Company) -> Company:
        """
        DART API에서 기업 기본 정보를 조회하여 Company 모델 업데이트

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

            # 업종코드 저장 및 Industry 매핑
            # DART API 응답 필드: induty_code
            industry_code = data.get("induty_code")
            if industry_code:
                company.induty_code = industry_code

                # 업종코드로 Industry 매핑
                industry = IndustryMapper.get_industry_by_code(industry_code)
                if industry:
                    logger.info(
                        f"업종코드 매핑 성공: {company.stock_code} → {industry_code} → {industry.name}"
                    )
                else:
                    logger.warning(
                        f"업종코드 매핑 실패: {company.stock_code} → {industry_code} "
                        f"(Industry를 찾을 수 없습니다. 업종코드는 저장되었습니다.)"
                    )

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
