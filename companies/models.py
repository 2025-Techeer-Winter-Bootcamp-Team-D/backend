# companies/models.py

from django.db import models



class Company(models.Model):
    stock_code = models.CharField(primary_key=True, max_length=10)  # 종목코드 (6자리)
    corp_code = models.CharField(max_length=8, unique=True, null=True)  # DART 고유번호 (8자리) - 신규
    industry = models.ForeignKey('industries.Industry', on_delete=models.CASCADE, related_name='companies', db_column='industry_id')
    company_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    logo_url = models.URLField(max_length=500, blank=True, null=True)  # 신규
    market_amount = models.BigIntegerField(default=0)  # 시가총액
    # DART 기업개황 추가 필드
    ceo_name = models.CharField(max_length=100, blank=True, null=True)  # 대표자명
    establishment_date = models.DateField(null=True)  # 설립일
    homepage_url = models.URLField(max_length=500, blank=True, null=True)  # 홈페이지
    address = models.TextField(blank=True, null=True)  # 본사 주소
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'company'

        

class CompanyRanking(models.Model):
    ranking_id = models.BigIntegerField(primary_key=True) # 순위 아이디
    stock_code = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='rankings', db_column='stock_code') # 종목코드
    rank = models.IntegerField() # 순위
    base_date = models.DateField() # 기준 날짜
    created_at = models.DateTimeField(auto_now_add=True) # 생성 일시
    updated_at = models.DateTimeField(auto_now=True) # 수정 일시
    is_deleted = models.BooleanField(default=False) # 삭제 여부

    class Meta:
        db_table = 'company_ranking'

        

        