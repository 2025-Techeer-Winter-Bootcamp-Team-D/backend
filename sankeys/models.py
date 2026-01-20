from django.db import models

class SankeyData(models.Model):
    # 'on_orm_delete' -> 'on_delete'로 수정 완료
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='sankey_data')
    fiscal_year = models.IntegerField()
    
    nodes = models.JSONField(default=list)  # [{name: "매출액"}, ...]
    links = models.JSONField(default=list)  # [{source: "가전", target: "매출액", value: 100}, ...]
    
    is_loss = models.BooleanField(default=False) # 적자 여부 (True/False)
    
    raw_values = models.JSONField(default=dict) # 실제 DB 수치 보관
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'fiscal_year')

    def __str__(self):
        return f"{self.company.company_name} ({self.fiscal_year}) - Sankey"