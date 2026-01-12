# companies/models.py
from django.db import models

class Industry(models.Model):
    industry_id = models.IntegerField(primary_key=True) # 산업 아이디
    name = models.CharField(max_length=100) # 산업 이름
    description = models.TextField() # 설명

    def __str__(self):
        return self.name

class Company(models.Model):
    company_id = models.IntegerField(primary_key=True) # 기업 아이디
    industry_id = models.ForeignKey(Industry, on_delete=models.CASCADE, related_name='companies') # 산업 아이디
    company_name = models.CharField(max_length=100) # 기업 이름
    ticker_symbol = models.CharField(max_length=20) # 티커 심볼
    description = models.TextField() # 설명
    rank_in_industry = models.IntegerField() # 명세서의 rankInIndustry 산업 내 기업 순위

    def __str__(self):
        return self.company_name