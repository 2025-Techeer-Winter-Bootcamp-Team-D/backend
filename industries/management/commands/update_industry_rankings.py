from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db import models
from django.db import transaction
from datetime import date
from collections import defaultdict
from industries.models import Industry
from industries.models import IndustryRanking


class Command(BaseCommand):
    help = "산업별 시가총액 합계를 계산하여 순위를 저장합니다. (KOSPI/KOSDAQ 통합)"

    def handle(self, *args, **options):
        self.stdout.write("--- 산업 순위 계산 시작 (KOSPI/KOSDAQ 통합) ---")

        # 1. 모든 산업의 시가총액 계산
        industry_data = Industry.objects.filter(is_deleted=False).annotate(
            total_amount=Sum(
                "companies__market_amount",
                filter=models.Q(companies__is_deleted=False),
            )
        )

        if not industry_data.exists():
            self.stdout.write(self.style.WARNING("계산할 산업 데이터가 없습니다."))
            return

        # 2. 이름별로 그룹화하여 시가총액 합산 + 대표 산업 선택
        # 대표 산업: KOSPI(0xxx) 우선, 없으면 가장 작은 코드
        name_to_data = defaultdict(lambda: {"total": 0, "industries": []})

        for ind in industry_data:
            if ind.total_amount and ind.total_amount > 0:
                name_to_data[ind.name]["total"] += ind.total_amount
                name_to_data[ind.name]["industries"].append(ind)

        if not name_to_data:
            self.stdout.write(self.style.WARNING("시가총액이 있는 산업이 없습니다."))
            return

        # 3. 각 이름 그룹에서 대표 산업 선택 (KOSPI 우선)
        aggregated_data = []
        for name, data in name_to_data.items():
            industries = data["industries"]
            # KOSPI(0xxx) 우선, 그 다음 코드 순
            industries.sort(key=lambda x: (not x.induty_code.startswith("0"), x.induty_code))
            representative = industries[0]

            aggregated_data.append(
                {
                    "industry": representative,
                    "total_amount": data["total"],
                    "name": name,
                    "merged_codes": [i.induty_code for i in industries],
                }
            )

        # 4. 시가총액 내림차순 정렬
        aggregated_data.sort(key=lambda x: x["total_amount"], reverse=True)

        today = date.today()
        ranking_instances = []

        # 5. 순위 객체 생성
        for index, item in enumerate(aggregated_data, start=1):
            ranking_id = int(today.strftime("%Y%m%d")) * 10000 + index

            # 통합된 경우 로그 출력
            if len(item["merged_codes"]) > 1:
                self.stdout.write(
                    f"  통합: {item['name']} ({', '.join(item['merged_codes'])}) -> {item['industry'].induty_code}"
                )

            ranking_instances.append(
                IndustryRanking(
                    ranking_id=ranking_id,
                    industry=item["industry"],
                    rank=index,
                    amount=item["total_amount"],
                    base_date=today,
                )
            )

        # 6. 데이터베이스 반영 (원자성 보장)
        try:
            with transaction.atomic():
                # 같은 날짜의 기존 데이터 삭제 후 새로 삽입
                IndustryRanking.objects.filter(base_date=today).delete()
                IndustryRanking.objects.bulk_create(ranking_instances)

            self.stdout.write(
                self.style.SUCCESS(
                    f"{today} 기준 {len(ranking_instances)}개 산업 순위 저장 완료! "
                    f"(원본 {len(list(industry_data))}개 → 통합 {len(ranking_instances)}개)"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"에러 발생: {str(e)}"))
