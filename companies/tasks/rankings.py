from celery import shared_task
from django.core.management import call_command

@shared_task
def update_all_rankings_task():
    """
    회사 및 산업 랭킹을 순차적으로 업데이트하는 백그라운드 작업
    """
    call_command('update_company_rankings')
    call_command('update_industry_rankings')
    return "Rankings updated successfully"