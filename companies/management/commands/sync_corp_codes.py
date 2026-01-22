"""
DART 고유번호 목록 동기화 Management Command

상장기업(stock_code가 있는 기업)만 동기화합니다.

사용법:
    # 시가총액 상위 100개 기업만 동기화 (FinanceDataReader 사용)
    python manage.py sync_corp_codes --top-companies

    # 상위 N개 기업만 동기화
    python manage.py sync_corp_codes --limit 100 --skip-industry-mapping

    # 전체 동기화 (업종코드 조회 건너뛰기 - 빠른 동기화)
    python manage.py sync_corp_codes --skip-industry-mapping

    # 업종코드 포함 동기화 (느리지만 완전한 데이터)
    python manage.py sync_corp_codes

    # 기존 기업 업데이트
    python manage.py sync_corp_codes --update-existing --skip-industry-mapping
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from companies.models import Company
from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.services.corp_code_parser import CorpCodeParser
from industries.models import KsicCategory, Industry, KisIndustry
import logging
import requests
import zipfile
import io
import FinanceDataReader as fdr

logger = logging.getLogger(__name__)

# 시가총액 상위 50개 기업 종목코드 (2024년 기준)
# 개발/테스트 환경에서 의미있는 데이터로 작업하기 위한 대표 기업 목록


class Command(BaseCommand):
    help = (
        "DART API에서 상장기업 고유번호 목록을 다운로드하여 Company 테이블을 채웁니다. "
        "비상장기업은 자동으로 제외됩니다. "
        "기본적으로 --skip-industry-mapping 옵션 사용을 권장합니다 (빠른 동기화)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="기존 기업의 corp_code를 업데이트합니다 (기본값: False)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제로 DB에 저장하지 않고 결과만 출력합니다",
        )
        parser.add_argument(
            "--skip-industry-mapping",
            action="store_true",
            help="업종코드 조회를 건너뜁니다 (API 호출 절약, 빠른 동기화). 권장 옵션입니다.",
        )
        parser.add_argument(
            "--top-companies",
            action="store_true",
            help="시가총액 상위 100개 기업만 동기화합니다 (FinanceDataReader 기반)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="동기화할 최대 기업 수 (0=무제한, 기본값: 0)",
        )

    def _load_kis_master_and_mapping(self, dry_run=False):
        """
        KIS 마스터 및 종목-업종 매핑을 메모리 딕셔너리로 로드
        IndustryMapping 테이블 없이 메모리에서 직접 계산
        """
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 50))
        self.stdout.write("KIS 마스터 및 종목-업종 매핑 로드 중...")
        self.stdout.write("=" * 50)

        base_url = "https://new.real.download.dws.co.kr/common/master/"

        # STEP 1: KisIndustry 테이블 채우기
        self.stdout.write("STEP 1: KIS 업종 마스터 적재 중...")
        if not dry_run:
            try:
                res_idx = requests.get(base_url + "idxcode.mst.zip", timeout=10)
            except requests.exceptions.Timeout:
                self.stdout.write(
                    self.style.ERROR("KIS 업종 마스터 다운로드 타임아웃 (10초 초과)")
                )
                raise
            except requests.exceptions.RequestException as e:
                self.stdout.write(
                    self.style.ERROR(f"KIS 업종 마스터 다운로드 실패: {e}")
                )
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
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {kis_count}개 KIS 업종 코드 적재 완료")
                )
        else:
            self.stdout.write("  [DRY RUN] KIS 업종 마스터 적재 스킵")

        # STEP 2: 종목-업종 매핑을 메모리 딕셔너리로 생성 (테이블 사용 안 함)
        self.stdout.write("STEP 2: 종목-업종 매핑 메모리 적재 중...")
        # ticker -> kis_code 매핑 딕셔너리
        ticker_to_kis = {}

        if not dry_run:
            mapping_count = 0
            for target in [
                {"name": "KOSPI", "file": "kospi_code.mst.zip"},
                {"name": "KOSDAQ", "file": "kosdaq_code.mst.zip"},
            ]:
                try:
                    res_stk = requests.get(base_url + target["file"], timeout=10)
                except requests.exceptions.Timeout:
                    self.stdout.write(
                        self.style.ERROR(
                            f"{target['name']} 종목 마스터 다운로드 타임아웃 (10초 초과)"
                        )
                    )
                    raise
                except requests.exceptions.RequestException as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"{target['name']} 종목 마스터 다운로드 실패: {e}"
                        )
                    )
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
                        large_code = (
                            line[64:68].decode("cp949", errors="ignore").strip()
                        )

                        kis_code = mid_code if mid_code != "0000" else large_code

                        if kis_code and kis_code != "0000":
                            # KisIndustry에 존재하는지 확인
                            if KisIndustry.objects.filter(kis_code=kis_code).exists():
                                ticker_to_kis[ticker] = kis_code
                                mapping_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {target['name']} 종목-업종 매핑 적재 완료")
                )
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ 총 {mapping_count}개 종목-업종 매핑 (메모리)")
            )
        else:
            self.stdout.write("  [DRY RUN] 종목-업종 매핑 적재 스킵")

        self.stdout.write(self.style.SUCCESS("=" * 50 + "\n"))
        return ticker_to_kis

    def _create_ksic_mapping(self, ticker_to_kis, dry_run=False):
        """
        Company 테이블 기반으로 KSIC → KIS 매핑 생성
        IndustryMapping 테이블 없이 메모리 딕셔너리 사용
        """
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("KSIC → KIS 매핑 생성 중...")
        self.stdout.write("=" * 50)

        # STEP 3: Company 테이블에서 KSIC 코드 수집 및 KsicCategory 생성
        self.stdout.write("STEP 3: KSIC 카테고리 생성 중...")
        if not dry_run:
            unique_ksic_codes = (
                Company.objects.filter(induty_code__isnull=False)
                .values_list("induty_code", flat=True)
                .distinct()
            )
            ksic_count = 0
            for code in unique_ksic_codes:
                KsicCategory.objects.get_or_create(ksic_code=code)
                ksic_count += 1
            self.stdout.write(
                self.style.SUCCESS(f"  ✓ {ksic_count}개 KSIC 카테고리 생성 완료")
            )
        else:
            self.stdout.write("  [DRY RUN] KSIC 카테고리 생성 스킵")

        # STEP 4: KSIC → KIS 매핑 생성 (메모리 딕셔너리 사용)
        self.stdout.write("STEP 4: KSIC → KIS 매핑 생성 중...")
        if not dry_run:
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

            self.stdout.write(
                self.style.SUCCESS(f"  ✓ {mapping_created}개 KSIC → KIS 매핑 생성 완료")
            )
        else:
            self.stdout.write("  [DRY RUN] KSIC → KIS 매핑 생성 스킵")

        self.stdout.write(self.style.SUCCESS("=" * 50 + "\n"))

        self.stdout.write(self.style.SUCCESS("=" * 50 + "\n"))

    def _get_top_market_cap_tickers(self, limit=100):
        """
        FinanceDataReader를 사용하여 시가총액 상위 기업의 종목코드를 가져옵니다.
        """
        try:
            # KRX 전체 종목 리스트 가져오기 (Marcap으로 정렬됨)
            df = fdr.StockListing("KRX")

            # Marcap 기준 내림차순 정렬
            df = df.sort_values(by="Marcap", ascending=False)

            # 상위 limit개 선택
            top_df = df.head(limit)

            # 종목코드 리스트 반환 (Code 컬럼)
            return set(top_df["Code"].tolist())
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"FinanceDataReader 조회 실패: {e}"))
            return set()

    def handle(self, *args, **options):
        update_existing = options["update_existing"]
        dry_run = options["dry_run"]
        skip_industry_mapping = options["skip_industry_mapping"]
        top_companies = options["top_companies"]
        limit = options["limit"]

        # --top-companies 옵션 사용 시 업종코드 매핑은 필수
        if top_companies and skip_industry_mapping:
            self.stdout.write(
                self.style.WARNING(
                    "--top-companies 옵션 사용 시 업종코드 매핑이 필요합니다. "
                    "--skip-industry-mapping 옵션을 무시하고 업종코드 조회를 수행합니다."
                )
            )
            skip_industry_mapping = False

        self.stdout.write(
            self.style.SUCCESS("DART 상장기업 고유번호 목록 동기화 시작...")
        )
        self.stdout.write(
            self.style.WARNING(
                "참고: 상장기업(stock_code가 있는 기업)만 처리합니다. "
                "비상장기업은 자동으로 제외됩니다."
            )
        )

        if top_companies:
            self.stdout.write(
                self.style.WARNING(
                    "시가총액 상위 100개 기업만 동기화합니다 (FinanceDataReader 기준)."
                )
            )
        elif limit > 0:
            self.stdout.write(
                self.style.WARNING(f"최대 {limit}개 기업만 동기화합니다.")
            )

        try:
            # DART API 클라이언트 초기화
            dart_client = DartAPIClient()

            # 고유번호 목록 다운로드
            self.stdout.write("DART API에서 고유번호 목록 다운로드 중...")
            zip_data = dart_client.get_corp_code_list()
            self.stdout.write(self.style.SUCCESS("다운로드 완료"))

            # ZIP에서 XML 추출
            self.stdout.write("ZIP 파일에서 XML 추출 중...")
            xml_content = dart_client.extract_corp_code_xml(zip_data)
            self.stdout.write(self.style.SUCCESS("XML 추출 완료"))

            # XML 파싱 (코스피/코스닥 필터링)
            self.stdout.write(
                "XML 파싱 중 (코스피/코스닥 필터링: 종목코드 000001~005999, 010000~099999)..."
            )
            parser = CorpCodeParser()
            companies_data = parser.parse_corp_code_xml(xml_content)
            self.stdout.write(
                self.style.SUCCESS(
                    f"파싱 완료: {len(companies_data)}개 기업 (코스피/코스닥, 종목코드 000001~005999, 010000~099999)"
                )
            )

            # 기업 필터링 (--top-companies 또는 --limit 옵션)
            before_count = len(companies_data)
            if top_companies:
                self.stdout.write(
                    "FinanceDataReader를 통해 시가총액 상위 100개 기업 조회 중..."
                )
                top_tickers = self._get_top_market_cap_tickers(100)

                # 상위 100개 기업만 필터링
                companies_data = [
                    c for c in companies_data if c["stock_code"] in top_tickers
                ]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"필터링 완료: {before_count}개 → {len(companies_data)}개 기업 "
                        f"(시가총액 상위 100개 중 DART에 존재하는 기업)"
                    )
                )
            elif limit > 0:
                # 상위 N개만 선택
                companies_data = companies_data[:limit]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"필터링 완료: {before_count}개 → {len(companies_data)}개 기업 (상위 {limit}개 제한)"
                    )
                )

            # Company 생성/업데이트
            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN 모드: 실제로 저장하지 않습니다.")
                )

            # STEP 1: Company 생성/업데이트 (원본 KSIC 코드만 저장, 매핑은 나중에)
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("STEP 1: Company 생성/업데이트 (원본 KSIC 코드 저장)")
            self.stdout.write("=" * 50)

            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN 모드: 실제로 저장하지 않습니다.")
                )

            # 각 기업을 개별 트랜잭션으로 처리하여 한 기업의 에러가 다른 기업에 영향을 주지 않도록 함
            for company_data in companies_data:
                stock_code = company_data["stock_code"]
                corp_code = company_data["corp_code"]
                corp_name = company_data["corp_name"]

                try:
                    # 각 기업을 개별 트랜잭션으로 처리
                    with transaction.atomic():
                        # 업종코드 및 시장 구분 조회 (원본 KSIC 코드만 저장, 매핑은 나중에)
                        raw_ksic_code = None
                        market = None

                        # 종목코드 범위로 시장 구분 판단 (fallback)
                        # 000001~005999: KOSPI, 010000~099999: KOSDAQ
                        try:
                            stock_code_int = int(stock_code)
                            if 1 <= stock_code_int <= 5999:
                                market = "KOSPI"
                            elif 10000 <= stock_code_int <= 99999:
                                market = "KOSDAQ"
                        except (ValueError, TypeError):
                            pass  # 종목코드가 숫자가 아닌 경우 무시

                        if not skip_industry_mapping:
                            try:
                                company_info = dart_client.get_company_info(corp_code)
                                raw_ksic = str(
                                    company_info.get("induty_code", "")
                                ).strip()

                                if len(raw_ksic) >= 3:
                                    # KSIC 코드를 3자리로 정규화하여 저장
                                    raw_ksic_code = raw_ksic[:3]
                                    self.stdout.write(
                                        f"  📋 {corp_name}: KSIC 코드 {raw_ksic_code} 조회 완료"
                                    )

                                # 시장 구분 매핑 (corp_cls → market)
                                # DART API corp_cls: Y(유가증권/KOSPI), K(코스닥/KOSDAQ)
                                corp_cls = company_info.get("corp_cls")
                                if corp_cls:
                                    market_mapping = {
                                        "Y": "KOSPI",
                                        "K": "KOSDAQ",
                                    }
                                    market = market_mapping.get(corp_cls)
                                    if market:
                                        self.stdout.write(
                                            f"  📊 {corp_name}: 시장 구분 {corp_cls} → {market}"
                                        )
                                    else:
                                        logger.warning(
                                            f"지원하지 않는 시장 구분: {corp_name} ({stock_code}) → corp_cls={corp_cls}"
                                        )
                            except Exception as e:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"  ! {corp_name} 업종 조회 실패: {e}"
                                    )
                                )
                                logger.warning(
                                    f"업종 조회 실패: {corp_name} ({corp_code}) - {e}"
                                )

                        # 기존 기업 확인
                        company, created = Company.objects.get_or_create(
                            stock_code=stock_code,
                            defaults={
                                "corp_code": corp_code,
                                "company_name": corp_name,
                                "induty_code": raw_ksic_code,  # 원본 KSIC 코드만 저장
                                "market": market,  # 시장 구분 (KOSPI/KOSDAQ)
                                "industry": None,  # 매핑은 나중에
                                "description": "",
                            },
                        )

                        if created:
                            created_count += 1
                            if not dry_run:
                                ksic_info = (
                                    f", KSIC: {raw_ksic_code}" if raw_ksic_code else ""
                                )
                                self.stdout.write(
                                    f"  생성: {stock_code} - {corp_name} (corp_code: {corp_code}{ksic_info})"
                                )
                        else:
                            # 기존 기업 업데이트
                            needs_update = False
                            update_messages = []

                            # corp_code 업데이트 (update_existing 옵션이 있을 때만)
                            if update_existing and company.corp_code != corp_code:
                                if not dry_run:
                                    company.corp_code = corp_code
                                needs_update = True
                                update_messages.append(f"corp_code: {corp_code}")

                            # 업종코드 업데이트 (원본 KSIC 코드만, 매핑은 나중에)
                            if not skip_industry_mapping and raw_ksic_code:
                                if company.induty_code != raw_ksic_code:
                                    if not dry_run:
                                        company.induty_code = raw_ksic_code
                                    needs_update = True
                                    update_messages.append(f"KSIC: {raw_ksic_code}")

                            # 시장 구분 업데이트
                            if market and company.market != market:
                                if not dry_run:
                                    company.market = market
                                needs_update = True
                                update_messages.append(f"시장: {market}")

                            # company_name 업데이트
                            if company.company_name != corp_name:
                                if not dry_run:
                                    company.company_name = corp_name
                                needs_update = True
                                update_messages.append(f"이름: {corp_name}")

                            if needs_update:
                                if not dry_run:
                                    company.save()
                                updated_count += 1
                                update_info = ", ".join(update_messages)
                                self.stdout.write(
                                    f"  업데이트: {stock_code} - {corp_name} ({update_info})"
                                )
                            else:
                                skipped_count += 1

                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"기업 처리 실패: {stock_code} - {corp_name} - {e}"
                        )
                    )
                    logger.error(f"기업 처리 실패: {stock_code} - {e}", exc_info=True)

            # STEP 2: KSIC → KIS 매핑 생성 및 Company 업데이트
            # 항상 실행하되, 이미 매핑된 기업은 건너뜀
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("STEP 2: KSIC → KIS 매핑 생성 및 Company 업데이트")
            self.stdout.write("=" * 50)

            # STEP 3-1: KIS 마스터 및 종목-업종 매핑 로드 (메모리)
            needs_mapping = (
                not KsicCategory.objects.filter(
                    representative_kis__isnull=False
                ).exists()
                or not KisIndustry.objects.exists()
            )

            if skip_industry_mapping:
                self.stdout.write(
                    self.style.WARNING(
                        "업종 매핑을 건너뜁니다 (--skip-industry-mapping 옵션)."
                    )
                )
                ticker_to_kis = {}
            elif needs_mapping:
                self.stdout.write(
                    self.style.WARNING(
                        "업종 매핑 데이터가 없습니다. 매핑 데이터를 로드합니다..."
                    )
                )
                ticker_to_kis = self._load_kis_master_and_mapping(dry_run=dry_run)
            else:
                self.stdout.write(
                    self.style.SUCCESS("업종 매핑 데이터가 이미 준비되어 있습니다.")
                )
                # 기존 매핑이 있어도 ticker_to_kis는 필요하므로 로드
                # 특히 --top-companies 옵션 사용 시 새로 추가된 기업들의 매핑을 위해 필요
                ticker_to_kis = self._load_kis_master_and_mapping(dry_run=dry_run)

            # STEP 3-2: KSIC → KIS 매핑 생성
            if ticker_to_kis:
                self._create_ksic_mapping(ticker_to_kis, dry_run=dry_run)

            # STEP 2-3: Company의 induty_code를 KIS 코드로 업데이트
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("STEP 2-3: Company 업종코드 KIS 변환 및 Industry 연결")
            self.stdout.write("=" * 50)

            updated_companies = 0
            companies_to_update = Company.objects.filter(
                induty_code__isnull=False
            ).exclude(induty_code="")

            total_companies = companies_to_update.count()
            self.stdout.write(f"총 {total_companies}개 기업의 업종코드를 변환합니다...")

            for idx, company in enumerate(companies_to_update, 1):
                try:
                    # Company의 induty_code가 KSIC 코드인지 확인
                    induty_code = company.induty_code.strip()

                    # 이미 KIS 코드인지 확인 (KisIndustry 테이블에 존재하는지 확인)
                    if KisIndustry.objects.filter(kis_code=induty_code).exists():
                        # 이미 KIS 코드로 매핑된 경우, Industry만 연결하고 건너뜀
                        industry = Industry.objects.filter(
                            induty_code=induty_code,
                            is_deleted=False,
                        ).first()

                        # KisIndustry는 있지만 Industry가 없는 경우 생성
                        if industry is None:
                            kis_industry = KisIndustry.objects.get(kis_code=induty_code)
                            if not dry_run:
                                industry = Industry.objects.create(
                                    induty_code=induty_code,
                                    name=kis_industry.name,
                                    is_deleted=False,
                                )
                                logger.info(
                                    f"Industry 생성: {induty_code} - {kis_industry.name}"
                                )
                            else:
                                self.stdout.write(
                                    f"  [DRY RUN] Industry 생성 예정: {induty_code} - {kis_industry.name}"
                                )
                                # dry_run이어도 updated_companies를 증가시키지 않음
                                continue

                        if industry and company.industry != industry:
                            if not dry_run:
                                company.industry = industry
                                company.save()
                            updated_companies += 1
                        # 이미 매핑 완료된 기업이므로 건너뜀
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
                            if not dry_run:
                                industry = Industry.objects.create(
                                    name=ksic_obj.name or kis_industry.name,
                                    induty_code=target_kis_code,
                                    description=f"KIS 지수 코드: {target_kis_code} (KSIC:{induty_code} 매핑)",
                                )
                            else:
                                self.stdout.write(
                                    f"  [{idx}/{total_companies}] Industry 생성 예정: "
                                    f"{ksic_obj.name or kis_industry.name} (KIS:{target_kis_code})"
                                )
                                continue

                        # Company 업데이트 (induty_code와 industry 모두 업데이트)
                        needs_update = False
                        if company.induty_code != target_kis_code:
                            needs_update = True
                        if company.industry != industry:
                            needs_update = True

                        if needs_update:
                            if not dry_run:
                                company.induty_code = target_kis_code
                                company.industry = industry
                                company.save()

                            updated_companies += 1
                            if idx % 10 == 0 or idx == total_companies:
                                self.stdout.write(
                                    f"  진행 중: {idx}/{total_companies} ({updated_companies}개 업데이트)"
                                )
                    else:
                        # 매핑이 없는 경우 로그만 출력 (스킵)
                        if idx % 100 == 0:
                            self.stdout.write(
                                f"  진행 중: {idx}/{total_companies} (매핑 없음: {company.company_name})"
                            )
                except Exception as e:
                    logger.warning(
                        f"Company 업종코드 변환 실패: {company.stock_code} - {e}"
                    )
                    continue

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ {updated_companies}개 기업의 업종코드를 KIS 코드로 변환 완료"
                )
            )

            # 결과 출력
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 50))
            self.stdout.write(self.style.SUCCESS("동기화 완료"))
            self.stdout.write(f"  생성: {created_count}개")
            if update_existing:
                self.stdout.write(f"  업데이트: {updated_count}개")
            self.stdout.write(f"  건너뜀: {skipped_count}개")
            if error_count > 0:
                self.stdout.write(self.style.ERROR(f"  실패: {error_count}개"))
            self.stdout.write(f"  전체: {len(companies_data)}개")
            self.stdout.write(self.style.SUCCESS("=" * 50))

        except DartAPIError as e:
            self.stdout.write(self.style.ERROR(f"DART API 오류: {e}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"오류 발생: {e}"))
            logger.exception("고유번호 목록 동기화 중 오류 발생")
            raise
