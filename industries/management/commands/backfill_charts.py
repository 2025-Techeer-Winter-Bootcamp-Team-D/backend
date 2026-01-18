from industries.models import Industry
from industries.services.kis_index_service import KISIndexService
from django.core.management.base import BaseCommand


# industries/management/commands/backfill_charts.py
class Command(BaseCommand):
    
    def add_arguments(self, parser):
        parser.add_argument('--id', type=int, help='특정 산업 ID 지정')
    
    def handle(self, *args, **options):
        industry_id = options.get('id')
        service = KISIndexService()
        
        if industry_id:
            industries = Industry.objects.filter(pk=industry_id)
        else:
            industries = Industry.objects.filter(is_deleted=False)

        for industry in industries:
            self.stdout.write(f"🚀 {industry.name} 데이터 수집 시작...")
            raw_data = service.fetch_1y_history_raw(industry.induty_code)
            charts = service.get_industry_charts_1y(raw_data)
            service.save_charts_to_db(industry, charts)
            self.stdout.write(f"✅ {industry.name} 완료")