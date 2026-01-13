# companies/models.py
from django.db import models

class Company(models.Model):
    ticker_symbol = models.CharField(primary_key=True, max_length=255) # 티커 심볼
    industry = models.ForeignKey('industries.Industry', on_delete=models.CASCADE, related_name='companies', db_column='industry_id') # 산업 아이디
    company_name = models.CharField(max_length=255) # 기업 이름
    description = models.TextField() # 설명
    market_amount = models.BigIntegerField(default=0) # 시가총액
    created_at = models.DateTimeField(auto_now_add=True) # 생성 일시
    updated_at = models.DateTimeField(auto_now=True) # 수정 일시
    is_deleted = models.BooleanField(default=False) # 삭제 여부

    class Meta:
        db_table = 'company'
        
class CompanyRanking(models.Model):
    ranking_id = models.BigIntegerField(primary_key=True) # 순위 아이디
    ticker_symbol = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='rankings', db_column='ticker_symbol') # 티커 심볼
    ranking_type = models.CharField(max_length=50) # 순위 유형
    rank = models.IntegerField() # 순위
    base_date = models.DateField() # 기준 날짜
    created_at = models.DateTimeField(auto_now_add=True) # 생성 일시
    updated_at = models.DateTimeField(auto_now=True) # 수정 일시
    is_deleted = models.BooleanField(default=False) # 삭제 여부
    
    class Meta:
        db_table = 'company_ranking'