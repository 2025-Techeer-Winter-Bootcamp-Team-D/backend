# companies/models.py
from django.db import models

class Company(models.Model):
    ticker_symbol = models.CharField(primary_key=True, max_length=255) # 티커 심볼
    industry = models.ForeignKey('industries.Industry', on_delete=models.CASCADE, related_name='companies', db_column='industry_id') # 산업 아이디
    company_name = models.CharField(max_length=255) # 기업 이름
    description = models.TextField() # 설명
    rank_in_industry = models.IntegerField() # 명세서의 rankInIndustry 산업 내 기업 순위
    created_at = models.DateTimeField(auto_now_add=True) # 생성 일시
    updated_at = models.DateTimeField(auto_now=True) # 수정 일시
    is_deleted = models.BooleanField(default=False) # 삭제 여부

    class Meta:
        db_table = 'company'
        
class StockPrice(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stock_prices', db_column='company_ticker_symbol') # 기업 티커 심볼
    time = models.BigIntegerField(help_text="Unix Timestamp") # 시간 (타임스탬프)
    open_price = models.FloatField() # 시가
    close_price = models.FloatField() # 종가
    high_price = models.FloatField() # 고가
    low_price = models.FloatField() # 저가
    volume = models.BigIntegerField() # 거래량
    trans_amount = models.BigIntegerField() # 거래대금

    class Meta:
        db_table = 'stock_price'
        unique_together = ('company', 'time')