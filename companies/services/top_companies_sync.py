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
from industries.models import KsicCategory, Industry, KisIndustry

logger = logging.getLogger(__name__)


class TopCompaniesSyncService:
    """시가총액 상위 기업 동기화 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()
        self.ticker_to_kis = {}  # 종목코드 → KIS 코드 매핑 캐시

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
                            and company.induty_code != raw_ksic_code
                        ):
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

    def _load_kis_master_and_mapping(self) -> Dict[str, str]:
        """
        KIS 마스터 및 종목-업종 매핑을 메모리 딕셔너리로 로드

        Returns:
            ticker_to_kis: 종목코드 → KIS 코드 매핑 딕셔너리
        """
        logger.info("KIS 마스터 및 종목-업종 매핑 로드 시작")

        base_url = "https://new.real.download.dws.co.kr/common/master/"

        # STEP 1: KisIndustry 테이블 채우기
        logger.info("STEP 1: KIS 업종 마스터 적재 중...")
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

        # STEP 2: 종목-업종 매핑을 메모리 딕셔너리로 생성
        logger.info("STEP 2: 종목-업종 매핑 메모리 적재 중...")
        ticker_to_kis = {}
        mapping_count = 0

        for target in [
            {"name": "KOSPI", "file": "kospi_code.mst.zip"},
            {"name": "KOSDAQ", "file": "kosdaq_code.mst.zip"},
        ]:
            try:
                res_stk = requests.get(base_url + target["file"], timeout=10)
                res_stk.raise_for_status()
            except requests.exceptions.Timeout:
                logger.error(f"{target['name']} 종목 마스터 다운로드 타임아웃 (10초 초과)")
                raise
            except requests.exceptions.RequestException as e:
                logger.error(f"{target['name']} 종목 마스터 다운로드 실패: {e}")
                raise

            with zipfile.ZipFile(io.BytesIO(res_stk.content)) as z:
                content = z.read(z.namelist()[0])
                for line in content.splitlines():
                    if len(line) < 100 or line[61:63] != b"ST":
                        continue
                    ticker = (
                        line[1:7].decode("cp949", errors="ignore").strip().zfill(6)
                    )

                    # 중분류(68:72)가 없으면 대분류(64:68)를 사용
                    mid_code = line[68:72].decode("cp949", errors="ignore").strip()
                    large_code = line[64:68].decode("cp949", errors="ignore").strip()

                    kis_code = mid_code if mid_code != "0000" else large_code

                    if kis_code and kis_code != "0000":
                        # KisIndustry에 존재하는지 확인
                        if KisIndustry.objects.filter(kis_code=kis_code).exists():
                            ticker_to_kis[ticker] = kis_code
                            mapping_count += 1
            logger.info(f"✓ {target['name']} 종목-업종 매핑 적재 완료")

        logger.info(f"✓ 총 {mapping_count}개 종목-업종 매핑 (메모리)")
        return ticker_to_kis

    def _create_ksic_mapping(self, ticker_to_kis: Dict[str, str]):
        """
        Company 테이블 기반으로 KSIC → KIS 매핑 생성

        Args:
            ticker_to_kis: 종목코드 → KIS 코드 매핑 딕셔너리
        """
        logger.info("KSIC → KIS 매핑 생성 시작")

        # STEP 3: Company 테이블에서 KSIC 코드 수집 및 KsicCategory 생성
        logger.info("STEP 3: KSIC 카테고리 생성 중...")
        unique_ksic_codes = (
            Company.objects.filter(induty_code__isnull=False)
            .values_list("induty_code", flat=True)
            .distinct()
        )
        ksic_count = 0
        for code in unique_ksic_codes:
            KsicCategory.objects.get_or_create(ksic_code=code)
            ksic_count += 1
        logger.info(f"✓ {ksic_count}개 KSIC 카테고리 생성 완료")

        # STEP 4: KSIC → KIS 매핑 생성 (메모리 딕셔너리 사용)
        logger.info("STEP 4: KSIC → KIS 매핑 생성 중...")
        mapping_created = 0
        for cat in KsicCategory.objects.all():
            # 해당 KSIC 코드를 가진 기업들의 종목코드 수집
            tickers = list(
                Company.objects.filter(induty_code=cat.ksic_code).values_list(
                    "stock_code", flat=True
                )
            )
            if not tickers:
                continue

            # 메모리 딕셔너리에서 통계 계산
            kis_counts = {}
            for ticker in tickers:
                kis_code = ticker_to_kis.get(ticker)
                if kis_code and kis_code != "0001":  # 종합지수 제외
                    kis_counts[kis_code] = kis_counts.get(kis_code, 0) + 1

            if kis_counts:
                # 가장 많이 나타나는 KIS 코드 찾기
                best_kis_code = max(kis_counts.items(), key=lambda x: x[1])[0]
                kis_obj = KisIndustry.objects.filter(kis_code=best_kis_code).first()

                if kis_obj:
                    cat.representative_kis_id = kis_obj.kis_code
                    cat.name = kis_obj.name
                    cat.save()
                    mapping_created += 1

        logger.info(f"✓ {mapping_created}개 KSIC → KIS 매핑 생성 완료")

    def _convert_ksic_to_kis_and_link_industry(self):
        """
        Company의 induty_code를 KIS 코드로 변환하고 Industry 연결
        """
        logger.info("Company 업종코드 KIS 변환 및 Industry 연결 시작")

        updated_companies = 0
        companies_to_update = Company.objects.filter(
            induty_code__isnull=False
        ).exclude(induty_code="")

        total_companies = companies_to_update.count()
        logger.info(f"총 {total_companies}개 기업의 업종코드를 변환합니다...")

        for idx, company in enumerate(companies_to_update, 1):
            try:
                induty_code = company.induty_code.strip()

                # 이미 KIS 코드인지 확인
                if KisIndustry.objects.filter(kis_code=induty_code).exists():
                    # Industry만 연결
                    industry = Industry.objects.filter(
                        induty_code=induty_code,
                        is_deleted=False,
                    ).first()

                    # KisIndustry는 있지만 Industry가 없는 경우 생성
                    if industry is None:
                        kis_industry = KisIndustry.objects.get(kis_code=induty_code)
                        industry = Industry.objects.create(
                            induty_code=induty_code,
                            name=kis_industry.name,
                            is_deleted=False,
                        )
                        logger.info(f"Industry 생성: {induty_code} - {kis_industry.name}")

                    if industry and company.industry != industry:
                        company.industry = industry
                        company.save()
                        updated_companies += 1
                    continue

                # KSIC 코드를 KIS 코드로 변환
                ksic_obj = KsicCategory.objects.filter(
                    ksic_code=induty_code
                ).first()

                if ksic_obj and ksic_obj.representative_kis:
                    target_kis_code = ksic_obj.representative_kis.kis_code

                    # KIS 코드로 Industry 찾기
                    industry = Industry.objects.filter(
                        induty_code=target_kis_code,
                        is_deleted=False,
                    ).first()

                    if not industry:
                        # Industry가 없으면 생성
                        kis_industry = ksic_obj.representative_kis
                        industry = Industry.objects.create(
                            name=ksic_obj.name or kis_industry.name,
                            induty_code=target_kis_code,
                            description=f"KIS 지수 코드: {target_kis_code} (KSIC:{induty_code} 매핑)",
                        )

                    # Company 업데이트
                    needs_update = False
                    if company.induty_code != target_kis_code:
                        needs_update = True
                    if company.industry != industry:
                        needs_update = True

                    if needs_update:
                        company.induty_code = target_kis_code
                        company.industry = industry
                        company.save()
                        updated_companies += 1

                        if idx % 10 == 0 or idx == total_companies:
                            logger.info(
                                f"진행 중: {idx}/{total_companies} ({updated_companies}개 업데이트)"
                            )
                else:
                    # 매핑이 없는 경우 스킵
                    if idx % 100 == 0:
                        logger.info(
                            f"진행 중: {idx}/{total_companies} (매핑 없음: {company.company_name})"
                        )
            except Exception as e:
                logger.warning(
                    f"Company 업종코드 변환 실패: {company.stock_code} - {e}"
                )
                continue

        logger.info(f"✓ {updated_companies}개 기업의 업종코드를 KIS 코드로 변환 완료")

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

        # 업종 매핑이 필요한지 확인
        needs_mapping = (
            not KsicCategory.objects.filter(
                representative_kis__isnull=False
            ).exists()
            or not KisIndustry.objects.exists()
        )

        if needs_mapping or not self.ticker_to_kis:
            logger.info("업종 매핑 데이터 로드 및 매핑 생성")
            # KIS 마스터 및 종목-업종 매핑 로드
            self.ticker_to_kis = self._load_kis_master_and_mapping()
            # KSIC → KIS 매핑 생성
            self._create_ksic_mapping(self.ticker_to_kis)
        else:
            logger.info("업종 매핑 데이터가 이미 준비되어 있습니다")

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
