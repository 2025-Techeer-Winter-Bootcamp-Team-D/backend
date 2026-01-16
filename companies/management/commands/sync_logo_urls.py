# companies/management/commands/sync_logo_urls.py
"""
기업 로고 URL 일괄 동기화 명령어
Logo.dev API를 활용하여 모든 기업의 logo_url 필드를 업데이트
"""
from django.core.management.base import BaseCommand
from companies.models import Company
from companies.services.logo import get_logo_url


class Command(BaseCommand):
    help = "Logo.dev를 사용하여 모든 기업의 logo_url을 동기화합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="기존 logo_url이 있어도 덮어씁니다.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 저장 없이 변경될 내용만 출력합니다.",
        )

    def handle(self, *args, **options):
        overwrite = options["overwrite"]
        dry_run = options["dry_run"]

        # homepage_url이 있는 기업만 조회
        queryset = Company.objects.filter(
            homepage_url__isnull=False,
            is_deleted=False,
        ).exclude(homepage_url="")

        if not overwrite:
            # logo_url이 비어있는 기업만 대상
            queryset = queryset.filter(logo_url__isnull=True) | queryset.filter(
                logo_url=""
            )

        total = queryset.count()
        self.stdout.write(f"대상 기업 수: {total}개")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("업데이트할 기업이 없습니다."))
            return

        updated = 0
        failed = 0

        for company in queryset.iterator():
            logo_url = get_logo_url(homepage_url=company.homepage_url)

            if logo_url:
                if dry_run:
                    self.stdout.write(
                        f"[DRY-RUN] {company.stock_code} ({company.company_name}): "
                        f"{logo_url}"
                    )
                else:
                    company.logo_url = logo_url
                    company.save(update_fields=["logo_url", "updated_at"])
                updated += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"로고 URL 생성 실패: {company.stock_code} "
                        f"({company.company_name}) - homepage: {company.homepage_url}"
                    )
                )
                failed += 1

        action = "변경 예정" if dry_run else "업데이트 완료"
        self.stdout.write(
            self.style.SUCCESS(f"\n{action}: {updated}개, 실패: {failed}개")
        )
