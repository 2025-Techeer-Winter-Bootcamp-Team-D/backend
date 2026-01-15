# industries/models.py
from django.db import models

class Industry(models.Model):
    # ERD상 산업 아이디 (PK)
    industry_id = models.BigAutoField(primary_key=True) 
    # 산업 이름
    name = models.CharField(max_length=255) 
    # 산업 설명
    description = models.TextField(null=True, blank=True) 
    # 생성/수정/삭제 필드 (공통)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'industry' # 실제 DB 테이블명 고정
        
class IndustryRanking(models.Model):
    ranking_id = models.BigIntegerField(primary_key=True) # 순위 아이디
    industry = models.ForeignKey(Industry, on_delete=models.CASCADE, related_name='rankings', db_column='industry_id') # 산업 아이디
    rank = models.IntegerField() # 순위
    amount = models.BigIntegerField() # 시가총액 합계
    base_date = models.DateField() # 기준 날짜
    created_at = models.DateTimeField(auto_now_add=True) # 생성 일시
    updated_at = models.DateTimeField(auto_now=True) # 수정 일시
    is_deleted = models.BooleanField(default=False) # 삭제 여부

    class Meta:
        db_table = 'industry_ranking'
