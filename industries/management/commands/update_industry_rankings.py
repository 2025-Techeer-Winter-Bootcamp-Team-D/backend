from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db import transaction
from datetime import date
from industries.models import Industry
from industries.models import IndustryRanking

class Command(BaseCommand):
    help = '산업별 시가총액 합계를 계산하여 순위를 저장합니다.'

    def handle(self, *args, **options):
        self.stdout.write("--- 산업 순위 계산 시작 ---")

        # 1. 산업별 시가총액 합계 계산
        # related_name='companies'를 활용해 역참조 집계
        industry_data = Industry.objects.annotate(
            total_amount=Sum('companies__market_amount')
        ).filter(total_amount__gt=0).order_by('-total_amount')

        if not industry_data.exists():
            self.stdout.write(self.style.WARNING("계산할 산업 데이터가 없습니다."))
            return

        today = date.today()
        ranking_instances = []

        # 2. 순위 객체 생성
        for index, ind in enumerate(industry_data, start=1):
            ranking_id = int(today.strftime('%Y%m%d')) * 10000 + index
            ranking_instances.append(
                IndustryRanking(
                    ranking_id=ranking_id,
                    industry=ind,
                    rank=index,
                    amount=ind.total_amount,
                    base_date=today
                )
            )

        # 3. 데이터베이스 반영 (원자성 보장)
        try:
            with transaction.atomic():
                # 같은 날짜의 기존 데이터 삭제 후 새로 삽입
                IndustryRanking.objects.filter(base_date=today).delete()
                IndustryRanking.objects.bulk_create(ranking_instances)
            
            self.stdout.write(self.style.SUCCESS(f"{today} 기준 {len(ranking_instances)}개 산업 순위 저장 완료!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"에러 발생: {str(e)}"))