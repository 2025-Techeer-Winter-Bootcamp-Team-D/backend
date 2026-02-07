from django.db import models

class MarketIndex(models.Model):
    # 인덱스 아이디 (BigInt, PK)
    index_id = models.BigAutoField(primary_key=True)
    
    # 마켓 종류 (KOSPI, KOSDAQ 등)
    market_type = models.CharField(max_length=10)
    
    # 인덱스 날짜 (TimescaleDB 하이퍼테이블 기준 필드)
    idx_date = models.DateField()
    
    # 지수값 (종가)
    value = models.DecimalField(max_digits=20, decimal_places=6)
    
    # 추가: 거래량 및 거래대금
    volume = models.BigIntegerField(help_text="거래량 (주)")
    amount = models.BigIntegerField(help_text="거래대금 (원)")
    
    # 관리용 필드
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    #is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'market_index'
        unique_together = ('idx_date', 'market_type') # 날짜와 타입 중복 방지
        ordering = ['-idx_date']