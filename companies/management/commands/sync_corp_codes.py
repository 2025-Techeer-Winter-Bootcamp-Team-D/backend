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
from django.db import transaction
from companies.models import Company
from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.services.corp_code_parser import CorpCodeParser
from industries.models import KsicCategory
import logging

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

            if skip_industry_mapping:
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

            # 각 기업을 개별 트랜잭션으로 처리하여 한 기업의 에러가 다른 기업에 영향을 주지 않도록 함
            for company_data in companies_data:
                stock_code = company_data["stock_code"]
                corp_code = company_data["corp_code"]
                corp_name = company_data["corp_name"]

                try:
                    # 각 기업을 개별 트랜잭션으로 처리
                    with transaction.atomic():
                        # 업종코드 조회 (옵션)
                        industry_code = None
                        if not skip_industry_mapping:
                            try:
                                company_info = dart_client.get_company_info(corp_code)
                                raw_ksic = str(company_info.get("induty_code", "")).strip()
                            
                                if len(raw_ksic) >= 3:
                                    ksic_3digit = raw_ksic[:3] # KSIC 3자리 추출 (예: 261)
                                
                                    # 2. [핵심] DB에서 이 KSIC가 어떤 KIS 지수와 매핑되어 있는지 조회
                                    ksic_obj = KsicCategory.objects.filter(ksic_code=ksic_3digit).first()
                                
                                    if ksic_obj and ksic_obj.representative_kis_id:
                                        # 매핑된 KIS 코드(예: 0013)를 최종 저장용으로 확정
                                        target_kis_code = ksic_obj.representative_kis_id
                                        self.stdout.write(f"  🔍 매핑 찾음: {corp_name}({ksic_3digit}) -> KIS:{target_kis_code}")
                                    else:
                                        # 매핑이 없다면 일단 원본 KSIC라도 저장 (선택 사항)
                                        target_kis_code = ksic_3digit
                                        self.stdout.write(f"  ⚠️ 매핑 없음: {corp_name}({ksic_3digit}) 원본 유지")
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f"  ! {corp_name} 업종 조회 실패: {e}")) 

                        # 기존 기업 확인
                        company, created = Company.objects.get_or_create(
                            stock_code=stock_code,
                            defaults={
                                "corp_code": corp_code,
                                "company_name": corp_name,
                                "induty_code": target_kis_code,
                                "description": "",
                            },
                        )

                        if created:
                            created_count += 1
                            if not dry_run:
                                industry_info = (
                                    f", 업종코드: {industry_code}"
                                    if industry_code
                                    else ""
                                )
                                self.stdout.write(
                                    f"  생성: {stock_code} - {corp_name} (corp_code: {corp_code}{industry_info})"
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

                            # 업종코드 업데이트
                            if not skip_industry_mapping and industry_code:
                                if company.induty_code != industry_code:
                                    if not dry_run:
                                        company.induty_code = industry_code
                                    needs_update = True
                                    update_messages.append(f"업종코드: {industry_code}")

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
