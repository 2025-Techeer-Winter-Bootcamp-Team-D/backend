"""
DART 고유번호 목록 동기화 Management Command

상장기업(stock_code가 있는 기업)만 동기화합니다.

사용법:
    # 시가총액 상위 50개 기업만 동기화 (개발/테스트용, 권장)
    python manage.py sync_corp_codes --top-companies --skip-industry-mapping

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
from django.db import transaction, connection
from django.db.models import Count
from companies.models import Company
from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.services.corp_code_parser import CorpCodeParser
from companies.services.industry_mapper import IndustryMapper
from industries.models import KsicCategory, Industry, KisIndustry
import logging
import requests
import zipfile
import io

logger = logging.getLogger(__name__)

# 시가총액 상위 50개 기업 종목코드 (2024년 기준)
# 개발/테스트 환경에서 의미있는 데이터로 작업하기 위한 대표 기업 목록
TOP_50_STOCK_CODES = {
    # 코스피 시가총액 상위
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "373220",  # LG에너지솔루션
    "207940",  # 삼성바이오로직스
    "005380",  # 현대차
    "000270",  # 기아
    "068270",  # 셀트리온
    "035420",  # NAVER
    "005490",  # POSCO홀딩스
    "051910",  # LG화학
    "006400",  # 삼성SDI
    "035720",  # 카카오
    "028260",  # 삼성물산
    "105560",  # KB금융
    "055550",  # 신한지주
    "012330",  # 현대모비스
    "003670",  # 포스코퓨처엠
    "066570",  # LG전자
    "086790",  # 하나금융지주
    "096770",  # SK이노베이션
    "034730",  # SK
    "003550",  # LG
    "015760",  # 한국전력
    "032830",  # 삼성생명
    "009150",  # 삼성전기
    "018260",  # 삼성에스디에스
    "010130",  # 고려아연
    "033780",  # KT&G
    "000810",  # 삼성화재
    "030200",  # KT
    "011200",  # HMM
    "017670",  # SK텔레콤
    "316140",  # 우리금융지주
    "010950",  # S-Oil
    "024110",  # 기업은행
    "000100",  # 유한양행
    "009540",  # 한국조선해양
    "003490",  # 대한항공
    "011170",  # 롯데케미칼
    "034020",  # 두산에너빌리티
    # 코스닥 시가총액 상위
    "247540",  # 에코프로비엠
    "086520",  # 에코프로
    "091990",  # 셀트리온헬스케어
    "028300",  # HLB
    "041510",  # 에스엠
    "263750",  # 펄어비스
    "145020",  # 휴젤
    "293490",  # 카카오게임즈
    "112040",  # 위메이드
    "039030",  # 이오테크닉스
}


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
            help="시가총액 상위 50개 기업만 동기화합니다 (개발/테스트용 권장)",
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
            res_idx = requests.get(base_url + "idxcode.mst.zip")
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
                res_stk = requests.get(base_url + target["file"])
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

    def _seed_kis_industries(self, dry_run=False):
        """
        Industry 테이블에 KIS 코드 기반 Industry 생성
        seed_kis_codes.py의 핵심 로직을 통합
        """
        self.stdout.write("Industry 테이블에 KIS 코드 기반 Industry 생성 중...")

        # KIS 기반 산업 분류 데이터
        industries_data = [
            # --- A. 농업, 임업 및 어업 (통합 지수 사용) ---
            {
                "name": "농업/어업",
                "induty_code": "0027",
                "description": "KOSPI 농림수산업 통합 지수",
            },
            # --- C. 제조업 (KOSPI/KOSDAQ 주요 지수) ---
            {
                "name": "제조업",
                "induty_code": "1015",
                "description": "코스닥 제조 지수",
            },
            {
                "name": "음식료품",
                "induty_code": "0006",
                "description": "KOSPI 음식료품 업종 지수",
            },
            {
                "name": "화학/정유",
                "induty_code": "0009",
                "description": "KOSPI 화학 및 석유정제 통합 지수",
            },
            {
                "name": "의약품",
                "induty_code": "0010",
                "description": "KOSPI 의약품 업종 지수 (바이오 포함)",
            },
            {
                "name": "전기전자",
                "induty_code": "0014",
                "description": "KOSPI 전기전자 지수 (반도체/IT 핵심)",
            },
            {
                "name": "운수장비",
                "induty_code": "0015",
                "description": "KOSPI 운수장비 지수 (자동차/조선)",
            },
            {
                "name": "반도체(코스닥)",
                "induty_code": "1047",
                "description": "KOSDAQ 반도체 업종 지수",
            },
            {
                "name": "IT(코스닥)",
                "induty_code": "1012",
                "description": "KOSDAQ IT 업종지수",
            },
            # --- F. 건설업 ---
            {
                "name": "건설업",
                "induty_code": "0018",
                "description": "KOSPI 건설업 업종 지수",
            },
            # --- G. 도매 및 소매업 ---
            {
                "name": "유통업",
                "induty_code": "0016",
                "description": "KOSPI 유통업 및 소매 지수",
            },
            # --- H. 운수 및 창고업 ---
            {
                "name": "운수창고",
                "induty_code": "0019",
                "description": "KOSPI 육상/해상/항공 운송 통합 지수",
            },
            # --- J. 정보통신업 ---
            {
                "name": "통신업",
                "induty_code": "0020",
                "description": "KOSPI 통신업 업종 지수",
            },
            {
                "name": "소프트웨어",
                "induty_code": "1042",
                "description": "KOSDAQ 소프트웨어 지수",
            },
            # --- K. 금융 및 보험업 ---
            {
                "name": "금융업",
                "induty_code": "0021",
                "description": "KOSPI 금융업 통합 지수",
            },
            {
                "name": "보험",
                "induty_code": "0025",
                "description": "KOSPI 보험 업종 지수",
            },
            # --- M. 전문, 과학 및 기술 서비스업 ---
            {
                "name": "서비스업",
                "induty_code": "0026",
                "description": "KOSPI 서비스업 및 연구개발 통합 지수",
            },
            # --- 대표 시장 지수 (추가 권장) ---
            {"name": "코스피", "induty_code": "0001", "description": "KOSPI 종합 지수"},
            {
                "name": "코스닥",
                "induty_code": "1001",
                "description": "KOSDAQ 종합 지수",
            },
            {
                "name": "KRX 300",
                "induty_code": "2001",
                "description": "코스피/코스닥 통합 우량 300 지수",
            },
        ]

        created_count = 0
        skipped_count = 0

        for industry_data in industries_data:
            induty_code = industry_data.get("induty_code")
            name = industry_data["name"]
            description = industry_data["description"]

            # KIS 코드로 이미 존재하는 Industry가 있는지 확인
            if induty_code:
                existing = Industry.objects.filter(
                    induty_code=induty_code, is_deleted=False
                ).first()
                if existing:
                    skipped_count += 1
                    continue

                # 새로운 Industry 생성 (KIS 코드 사용)
                if not dry_run:
                    Industry.objects.create(
                        name=name,
                        induty_code=induty_code,
                        description=description,
                    )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ {created_count}개 Industry 생성 완료"
                + (f" ({skipped_count}개 건너뜀)" if skipped_count > 0 else "")
            )
        )

    def handle(self, *args, **options):
        update_existing = options["update_existing"]
        dry_run = options["dry_run"]
        skip_industry_mapping = options["skip_industry_mapping"]
        top_companies = options["top_companies"]
        limit = options["limit"]

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
                    f"시가총액 상위 {len(TOP_50_STOCK_CODES)}개 기업만 동기화합니다."
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
                # 시가총액 상위 50개 기업만 필터링
                companies_data = [
                    c for c in companies_data if c["stock_code"] in TOP_50_STOCK_CODES
                ]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"필터링 완료: {before_count}개 → {len(companies_data)}개 기업 "
                        f"(시가총액 상위 50개 중 DART에 존재하는 기업)"
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

            # STEP 1: Industry 테이블에 KIS 코드 기반 Industry 생성
            if not skip_industry_mapping:
                self.stdout.write("\n" + "=" * 50)
                self.stdout.write("STEP 1: Industry 테이블 KIS 코드 기반 Industry 생성")
                self.stdout.write("=" * 50)
                self._seed_kis_industries(dry_run=dry_run)
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "업종코드 조회를 건너뜁니다. 빠른 동기화를 위해 권장됩니다. "
                        "업종코드는 나중에 sync_company_info로 개별 업데이트할 수 있습니다."
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

            # STEP 2: Company 생성/업데이트 (원본 KSIC 코드만 저장, 매핑은 나중에)
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("STEP 2: Company 생성/업데이트 (원본 KSIC 코드 저장)")
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
                        # 업종코드 조회 (원본 KSIC 코드만 저장, 매핑은 나중에)
                        raw_ksic_code = None

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

            # STEP 3: KSIC → KIS 매핑 생성 및 Company 업데이트 (skip_industry_mapping이 False일 때만)
            if not skip_industry_mapping:
                self.stdout.write("\n" + "=" * 50)
                self.stdout.write("STEP 3: KSIC → KIS 매핑 생성 및 Company 업데이트")
                self.stdout.write("=" * 50)

                # STEP 3-1: KIS 마스터 및 종목-업종 매핑 로드 (메모리)
                needs_mapping = (
                    not KsicCategory.objects.filter(
                        representative_kis__isnull=False
                    ).exists()
                    or not KisIndustry.objects.exists()
                )

                if needs_mapping:
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
                    ticker_to_kis = self._load_kis_master_and_mapping(dry_run=dry_run)

                # STEP 3-2: KSIC → KIS 매핑 생성
                if ticker_to_kis:
                    self._create_ksic_mapping(ticker_to_kis, dry_run=dry_run)

                # STEP 3-3: Company의 induty_code를 KIS 코드로 업데이트
                self.stdout.write("\n" + "=" * 50)
                self.stdout.write(
                    "STEP 3-3: Company 업종코드 KIS 변환 및 Industry 연결"
                )
                self.stdout.write("=" * 50)

                updated_companies = 0
                companies_to_update = Company.objects.filter(
                    induty_code__isnull=False
                ).exclude(induty_code="")

                total_companies = companies_to_update.count()
                self.stdout.write(
                    f"총 {total_companies}개 기업의 업종코드를 변환합니다..."
                )

                for idx, company in enumerate(companies_to_update, 1):
                    try:
                        # Company의 induty_code가 KSIC 코드인지 확인
                        induty_code = company.induty_code.strip()

                        # 이미 KIS 코드인지 확인 (KisIndustry 테이블에 존재하는지 확인)
                        if KisIndustry.objects.filter(kis_code=induty_code).exists():
                            # 이미 KIS 코드인 경우, Industry만 연결
                            industry = Industry.objects.filter(
                                induty_code=induty_code,
                                is_deleted=False,
                            ).first()

                            if industry and company.industry != industry:
                                if not dry_run:
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
                                if not dry_run:
                                    industry = Industry.objects.create(
                                        name=ksic_obj.name or kis_industry.name,
                                        induty_code=target_kis_code,
                                        description=f"KIS 지수 코드: {target_kis_code} (KSIC:{induty_code} 매핑)",
                                    )
                                else:
                                    self.stdout.write(
                                        f"  [{idx}/{total_companies}] Industry 생성 예정: {ksic_obj.name or kis_industry.name} (KIS:{target_kis_code})"
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
