"""
중복 Industry 병합

같은 이름의 KOSPI/KOSDAQ Industry를 하나로 통합합니다.
KOSPI(0xxx)를 기준으로 병합하고, KOSDAQ(1xxx) Industry를 soft delete 처리합니다.

사용법:
    python manage.py merge_duplicate_industries
    python manage.py merge_duplicate_industries --dry-run  # 실제 변경 없이 확인만
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from collections import defaultdict

from industries.models import Industry
from companies.models import Company


class Command(BaseCommand):
    help = "같은 이름의 KOSPI/KOSDAQ Industry를 병합합니다"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 변경 없이 병합 대상만 확인합니다",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN 모드 (실제 변경 없음) ===\n"))

        # 1. 이름별로 Industry 그룹화
        industries = Industry.objects.filter(is_deleted=False).order_by("name", "induty_code")
        name_to_industries = defaultdict(list)

        for ind in industries:
            name_to_industries[ind.name].append(ind)

        # 2. 중복 이름 찾기
        duplicates = {name: inds for name, inds in name_to_industries.items() if len(inds) > 1}

        if not duplicates:
            self.stdout.write(self.style.SUCCESS("중복된 Industry가 없습니다."))
            return

        self.stdout.write(f"중복된 Industry 이름: {len(duplicates)}개\n")

        merged_count = 0
        company_updated_count = 0

        for name, industries_list in duplicates.items():
            self.stdout.write(f"\n--- {name} ---")

            # KOSPI(0xxx) 우선 정렬
            industries_list.sort(key=lambda x: (
                not (x.induty_code or "").startswith("0"),  # KOSPI 우선
                x.induty_code or "",
            ))

            # 대표 Industry (KOSPI 우선)
            primary = industries_list[0]
            to_merge = industries_list[1:]

            self.stdout.write(f"  기준: {primary.induty_code} (id={primary.id})")

            for secondary in to_merge:
                self.stdout.write(f"  병합 대상: {secondary.induty_code} (id={secondary.id})")

                # 해당 Industry를 참조하는 Company 수 확인
                company_count = Company.objects.filter(industry=secondary).count()
                self.stdout.write(f"    → 연결된 Company: {company_count}개")

                if not dry_run:
                    with transaction.atomic():
                        # Company의 industry FK 업데이트
                        updated = Company.objects.filter(industry=secondary).update(
                            industry=primary
                        )
                        company_updated_count += updated

                        # KOSDAQ Industry soft delete
                        secondary.is_deleted = True
                        secondary.save()

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"    ✓ {updated}개 Company를 {primary.induty_code}로 이동, "
                                f"{secondary.induty_code} 삭제 처리"
                            )
                        )

                merged_count += 1

        self.stdout.write(f"\n{'='*50}")
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] 병합 예정: {merged_count}개 Industry\n"
                    f"실제 병합하려면 --dry-run 옵션 없이 실행하세요."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"병합 완료: {merged_count}개 Industry 삭제, "
                    f"{company_updated_count}개 Company FK 업데이트"
                )
            )
