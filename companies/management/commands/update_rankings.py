from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date
from companies.models import Company, CompanyRanking


class Command(BaseCommand):
    ranking_type = "MARKET_CAP"
    
    help = '시가총액 기준으로 기업 순위를 계산하여 저장합니다.'

    def handle(self, *args, **options):
        self.stdout.write("--- 순위 계산 로직 시작 ---")

        # 1. 시가총액(market_amount) 기준 내림차순 정렬하여 기업 가져오기
        companies = Company.objects.filter(is_deleted=False).order_by('-market_amount')
        
        if not companies.exists():
            self.stdout.write(self.style.ERROR("Company 테이블에 데이터가 없습니다. 먼저 기업 데이터를 넣어주세요."))
            return

        today = date.today()
        ranking_instances = []

        # 2. 순위 생성 로직
        for index, company in enumerate(companies, start=1):
            # 현재 모델 설정이 BigIntegerField PK이므로, 중복되지 않는 ID를 임시로 생성합니다.
            # (만약 모델을 BigAutoField로 바꾸셨다면 ranking_id 필드는 제외해도 됩니다.)
            unique_ranking_id = int(today.strftime('%Y%m%d')) * 10000 + index 
            
            ranking_instances.append(
                CompanyRanking(
                    ranking_id=unique_ranking_id,
                    stock_code=company,  # 실제 필드명 매칭
                    ranking_type="MARKET_CAP",
                    rank=index,
                    base_date=today
                )
            )

        # 3. 데이터베이스 반영
        try:
            with transaction.atomic():
                # 오늘 날짜의 기존 순위가 있다면 삭제 후 새로 생성 (덮어쓰기)
                CompanyRanking.objects.filter(base_date=today, ranking_type=self.ranking_type).delete()
                CompanyRanking.objects.bulk_create(ranking_instances)
                
            self.stdout.write(self.style.SUCCESS(f"성공: {today} 기준 {len(ranking_instances)}개 기업 순위 저장 완료!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"에러 발생: {str(e)}"))