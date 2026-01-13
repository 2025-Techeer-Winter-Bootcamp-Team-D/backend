"""
DART 고유번호 목록 동기화 Management Command

상장기업(stock_code가 있는 기업)만 동기화합니다.

사용법:
    # 기본 실행 (업종코드 조회 건너뛰기 - 빠른 동기화)
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
import logging

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        update_existing = options["update_existing"]
        dry_run = options["dry_run"]
        skip_industry_mapping = options["skip_industry_mapping"]

        self.stdout.write(
            self.style.SUCCESS("DART 상장기업 고유번호 목록 동기화 시작...")
        )
        self.stdout.write(
            self.style.WARNING(
                "참고: 상장기업(stock_code가 있는 기업)만 처리합니다. "
                "비상장기업은 자동으로 제외됩니다."
            )
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

            # XML 파싱 (상장기업만 필터링)
            self.stdout.write("XML 파싱 중 (상장기업만 필터링)...")
            parser = CorpCodeParser()
            companies_data = parser.parse_corp_code_xml(xml_content)
            self.stdout.write(
                self.style.SUCCESS(
                    f"파싱 완료: {len(companies_data)}개 상장기업 (비상장기업 제외)"
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

            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN 모드: 실제로 저장하지 않습니다.")
                )

            with transaction.atomic():
                for company_data in companies_data:
                    stock_code = company_data["stock_code"]
                    corp_code = company_data["corp_code"]
                    corp_name = company_data["corp_name"]

                    try:
                        # 업종코드 조회 (옵션)
                        industry_code = None
                        if not skip_industry_mapping:
                            try:
                                # DART API에서 기업개황 조회하여 업종코드 가져오기
                                company_info = dart_client.get_company_info(corp_code)
                                # 업종코드 추출
                                industry_code = company_info.get("induty_code")
                                if industry_code and not dry_run:
                                    self.stdout.write(
                                        f"  업종코드 조회: {stock_code} → {industry_code}"
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"기업개황 조회 실패 ({stock_code}): {e}. 업종코드 없이 진행."
                                )

                        # 기존 기업 확인
                        company, created = Company.objects.get_or_create(
                            stock_code=stock_code,
                            defaults={
                                "corp_code": corp_code,
                                "company_name": corp_name,
                                "induty_code": (
                                    industry_code if not skip_industry_mapping else None
                                ),
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
                        self.stdout.write(
                            self.style.ERROR(
                                f"기업 처리 실패: {stock_code} - {corp_name} - {e}"
                            )
                        )
                        logger.error(f"기업 처리 실패: {stock_code} - {e}")

            # 결과 출력
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 50))
            self.stdout.write(self.style.SUCCESS("동기화 완료"))
            self.stdout.write(f"  생성: {created_count}개")
            if update_existing:
                self.stdout.write(f"  업데이트: {updated_count}개")
            self.stdout.write(f"  건너뜀: {skipped_count}개")
            self.stdout.write(f"  전체: {len(companies_data)}개")
            self.stdout.write(self.style.SUCCESS("=" * 50))

        except DartAPIError as e:
            self.stdout.write(self.style.ERROR(f"DART API 오류: {e}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"오류 발생: {e}"))
            logger.exception("고유번호 목록 동기화 중 오류 발생")
            raise
