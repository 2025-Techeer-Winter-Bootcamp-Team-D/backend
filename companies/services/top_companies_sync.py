"""
상위 시가총액 기업 동기화 서비스

FinanceDataReader를 사용하여 시가총액 상위 기업을 가져오고,
DART API와 연동하여 Company 테이블에 저장합니다.
"""

import logging
from typing import Dict, List, Set
from django.db import transaction
import FinanceDataReader as fdr
import requests
import zipfile
import io

from companies.models import Company
from companies.services.dart_api import DartAPIClient
from companies.services.corp_code_parser import CorpCodeParser
from companies.services.industry_mapping_rules import get_industry_kis_code
from industries.models import Industry, KisIndustry

logger = logging.getLogger(__name__)


class TopCompaniesSyncService:
    """시가총액 상위 기업 동기화 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    def get_top_market_cap_tickers(self, target_count: int = 100) -> Set[str]:
        """
        FinanceDataReader를 사용하여 시가총액 상위 기업의 종목코드를 가져옵니다.
        목표 개수를 채우기 위해 필요한 만큼 더 가져옵니다.

        Args:
            target_count: 최종적으로 필요한 기업 수

        Returns:
            종목코드 Set
        """
        try:
            # KRX 전체 종목 리스트 가져오기 (시가총액 순으로 정렬됨)
            df = fdr.StockListing("KRX")

            # Marcap 기준 내림차순 정렬
            df = df.sort_values(by="Marcap", ascending=False)

            # DART와의 교집합을 고려하여 여유있게 가져오기 (2배)
            # 상위 100개 요청 시 약 62~70개가 DART에 존재하므로 2배 buffer 필요
            buffer_count = int(target_count * 2)
            top_df = df.head(buffer_count)

            # 종목코드 리스트 반환
            return set(top_df["Code"].tolist())
        except Exception as e:
            logger.error(f"FinanceDataReader 조회 실패: {e}")
            raise

    def get_dart_companies_data(self) -> List[Dict]:
        """
        DART API에서 상장기업 목록을 가져옵니다.

        Returns:
            기업 데이터 리스트
        """
        # 고유번호 목록 다운로드
        zip_data = self.dart_client.get_corp_code_list()

        # ZIP에서 XML 추출
        xml_content = self.dart_client.extract_corp_code_xml(zip_data)

        # XML 파싱 (코스피/코스닥 필터링)
        parser = CorpCodeParser()
        companies_data = parser.parse_corp_code_xml(xml_content)

        return companies_data

    def filter_top_companies(
        self, companies_data: List[Dict], target_count: int = 100
    ) -> List[Dict]:
        """
        시가총액 기준으로 상위 기업을 필터링합니다.
        정확히 target_count 개수만큼 반환합니다.

        Args:
            companies_data: DART 기업 데이터 리스트
            target_count: 필요한 기업 수

        Returns:
            필터링된 기업 데이터 리스트
        """
        # FinanceDataReader에서 시가총액 상위 종목 가져오기
        top_tickers = self.get_top_market_cap_tickers(target_count)

        # DART 데이터와 교집합
        filtered_companies = [
            c for c in companies_data if c["stock_code"] in top_tickers
        ]

        # 시가총액 순서를 유지하기 위해 top_tickers 순서대로 정렬
        # FinanceDataReader에서 다시 가져와서 순서 유지
        try:
            df = fdr.StockListing("KRX")
            df = df.sort_values(by="Marcap", ascending=False)

            # 종목코드를 순서가 있는 리스트로 변환
            ticker_order = df["Code"].tolist()

            # filtered_companies를 ticker_order 순서대로 정렬
            ticker_to_company = {c["stock_code"]: c for c in filtered_companies}
            sorted_companies = []
            for ticker in ticker_order:
                if ticker in ticker_to_company:
                    sorted_companies.append(ticker_to_company[ticker])
                    if len(sorted_companies) >= target_count:
                        break

            return sorted_companies[:target_count]
        except Exception as e:
            logger.warning(f"시가총액 순서 정렬 실패, 원본 순서 사용: {e}")
            return filtered_companies[:target_count]

    def sync_companies(
        self,
        companies_data: List[Dict],
        update_existing: bool = False,
        include_industry_mapping: bool = False,
    ) -> Dict[str, int]:
        """
        기업 데이터를 Company 테이블에 동기화합니다.

        Args:
            companies_data: 동기화할 기업 데이터 리스트
            update_existing: 기존 기업 업데이트 여부
            include_industry_mapping: 업종 매핑 포함 여부

        Returns:
            통계 정보 (created, updated, skipped, error)
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "error": 0}

        for company_data in companies_data:
            stock_code = company_data["stock_code"]
            corp_code = company_data["corp_code"]
            corp_name = company_data["corp_name"]

            try:
                with transaction.atomic():
                    # 업종코드 및 시장 구분 조회
                    raw_ksic_code = None
                    market = None

                    # 종목코드 범위로 시장 구분 판단
                    try:
                        stock_code_int = int(stock_code)
                        if 1 <= stock_code_int <= 5999:
                            market = "KOSPI"
                        elif 10000 <= stock_code_int <= 99999:
                            market = "KOSDAQ"
                    except (ValueError, TypeError):
                        pass

                    # 업종 매핑 포함 시 DART API 호출
                    if include_industry_mapping:
                        try:
                            company_info = self.dart_client.get_company_info(corp_code)
                            raw_ksic = str(company_info.get("induty_code", "")).strip()

                            if len(raw_ksic) >= 3:
                                raw_ksic_code = raw_ksic[:3]

                            # 시장 구분 매핑
                            corp_cls = company_info.get("corp_cls")
                            if corp_cls:
                                market_mapping = {"Y": "KOSPI", "K": "KOSDAQ"}
                                market = market_mapping.get(corp_cls)
                        except Exception as e:
                            logger.warning(f"업종 조회 실패: {corp_name} - {e}")

                    # 기업 생성 또는 업데이트
                    company, created = Company.objects.get_or_create(
                        stock_code=stock_code,
                        defaults={
                            "corp_code": corp_code,
                            "company_name": corp_name,
                            "induty_code": raw_ksic_code,
                            "original_ksic_code": raw_ksic_code,  # 원본 KSIC 코드 저장
                            "market": market,
                            "industry": None,
                            "description": "",
                        },
                    )

                    if created:
                        stats["created"] += 1
                        logger.info(f"생성: {stock_code} - {corp_name}")
                    else:
                        # 기존 기업 업데이트
                        needs_update = False

                        if update_existing and company.corp_code != corp_code:
                            company.corp_code = corp_code
                            needs_update = True

                        if (
                            include_industry_mapping
                            and raw_ksic_code
                            and company.original_ksic_code != raw_ksic_code
                        ):
                            company.original_ksic_code = raw_ksic_code
                            company.induty_code = raw_ksic_code
                            needs_update = True

                        if market and company.market != market:
                            company.market = market
                            needs_update = True

                        if company.company_name != corp_name:
                            company.company_name = corp_name
                            needs_update = True

                        if needs_update:
                            company.save()
                            stats["updated"] += 1
                            logger.info(f"업데이트: {stock_code} - {corp_name}")
                        else:
                            stats["skipped"] += 1

            except Exception as e:
                stats["error"] += 1
                logger.error(f"기업 처리 실패: {stock_code} - {e}", exc_info=True)

        return stats

    def _load_kis_master(self):
        """
        KIS 업종 마스터 데이터를 KisIndustry 테이블에 로드
        """
        logger.info("KIS 업종 마스터 로드 시작")

        base_url = "https://new.real.download.dws.co.kr/common/master/"

        try:
            res_idx = requests.get(base_url + "idxcode.mst.zip", timeout=10)
            res_idx.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error("KIS 업종 마스터 다운로드 타임아웃 (10초 초과)")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"KIS 업종 마스터 다운로드 실패: {e}")
            raise

        with zipfile.ZipFile(io.BytesIO(res_idx.content)) as z:
            content = z.read(z.namelist()[0])
            kis_count = 0
            for line in content.splitlines():
                if len(line) < 45:
                    continue
                kis_code = line[1:5].decode("cp949", errors="ignore").strip()
                name = line[5:45].decode("cp949", errors="ignore").strip()
                if kis_code:
                    KisIndustry.objects.update_or_create(
                        kis_code=kis_code, defaults={"name": name}
                    )
                    kis_count += 1
            logger.info(f"✓ {kis_count}개 KIS 업종 코드 적재 완료")

    def _convert_ksic_to_kis_and_link_industry(self):
        """
        규칙 기반으로 Company의 KSIC 코드를 KIS 코드로 변환하고 Industry 연결
        """
        logger.info("Company 업종코드 KIS 변환 및 Industry 연결 시작 (규칙 기반)")

        updated_companies = 0
        unmapped_companies = 0

        # original_ksic_code가 있는 기업 우선 처리
        companies_to_update = Company.objects.filter(
            original_ksic_code__isnull=False
        ).exclude(original_ksic_code="")

        # original_ksic_code가 없으면 induty_code 사용
        if not companies_to_update.exists():
            companies_to_update = Company.objects.filter(
                induty_code__isnull=False
            ).exclude(induty_code="")

        total_companies = companies_to_update.count()
        logger.info(f"총 {total_companies}개 기업의 업종코드를 변환합니다...")

        for idx, company in enumerate(companies_to_update, 1):
            try:
                # KSIC 코드 결정 (original_ksic_code 우선)
                ksic_code = (
                    company.original_ksic_code
                    if company.original_ksic_code
                    else company.induty_code
                )
                if not ksic_code:
                    continue

                ksic_code = ksic_code.strip()

                # 규칙 기반 매핑으로 KIS 코드 결정
                target_kis_code = get_industry_kis_code(company.stock_code, ksic_code)

                if not target_kis_code:
                    unmapped_companies += 1
                    if idx % 100 == 0:
                        logger.info(
                            f"진행 중: {idx}/{total_companies} "
                            f"(매핑 없음: {company.company_name}, KSIC: {ksic_code})"
                        )
                    continue

                # kis_code로 Industry 찾기
                industry = Industry.objects.filter(
                    kis_code=target_kis_code,
                    is_deleted=False,
                ).first()

                # Industry가 없으면 생성
                if not industry:
                    kis_industry = KisIndustry.objects.filter(
                        kis_code=target_kis_code
                    ).first()
                    if kis_industry:
                        industry = Industry.objects.create(
                            kis_code=target_kis_code,
                            induty_code=target_kis_code,  # 호환성 유지
                            name=kis_industry.name,
                            is_deleted=False,
                        )
                        logger.info(f"Industry 생성: {target_kis_code} - {kis_industry.name}")
                    else:
                        continue

                # Company 업데이트 필요 여부 확인
                needs_update = False
                if company.industry != industry:
                    needs_update = True
                if company.induty_code != target_kis_code:
                    needs_update = True

                if needs_update:
                    company.industry = industry
                    company.induty_code = target_kis_code
                    company.save()
                    updated_companies += 1

                    if idx % 50 == 0 or idx == total_companies:
                        logger.info(
                            f"진행 중: {idx}/{total_companies} ({updated_companies}개 업데이트)"
                        )
            except Exception as e:
                logger.warning(
                    f"Company 업종코드 변환 실패: {company.stock_code} - {e}"
                )
                continue

        logger.info(f"✓ {updated_companies}개 기업 Industry 연결 완료")
        if unmapped_companies > 0:
            logger.warning(f"⚠️ {unmapped_companies}개 기업은 매핑 규칙 없음 (확인 필요)")

    def sync_top_companies(
        self, limit: int = 100, update_existing: bool = False
    ) -> Dict:
        """
        시가총액 상위 기업을 동기화합니다.

        Args:
            limit: 동기화할 기업 수
            update_existing: 기존 기업 업데이트 여부

        Returns:
            결과 딕셔너리 (stats, companies)
        """
        # DART 기업 데이터 가져오기
        companies_data = self.get_dart_companies_data()
        logger.info(f"DART에서 {len(companies_data)}개 기업 데이터 로드 완료")

        # 상위 기업 필터링
        filtered_companies = self.filter_top_companies(companies_data, limit)
        logger.info(
            f"시가총액 상위 {len(filtered_companies)}개 기업 필터링 완료 (목표: {limit}개)"
        )

        # 동기화 실행 (업종 매핑 포함)
        stats = self.sync_companies(
            filtered_companies,
            update_existing=update_existing,
            include_industry_mapping=True,  # 업종 매핑 포함
        )

        # KIS 업종 마스터 로드 (필요시)
        if not KisIndustry.objects.exists():
            logger.info("KIS 업종 마스터 로드 중...")
            self._load_kis_master()

        # Company의 induty_code를 KIS 코드로 변환하고 Industry 연결
        self._convert_ksic_to_kis_and_link_industry()

        # 동기화된 기업 정보 조회
        stock_codes = [c["stock_code"] for c in filtered_companies]
        companies = Company.objects.filter(stock_code__in=stock_codes).values(
            "stock_code",
            "company_name",
            "corp_code",
            "market",
            "induty_code",
            "market_amount",
        )

        return {
            "stats": stats,
            "companies": list(companies),
            "total_count": len(filtered_companies),
        }
