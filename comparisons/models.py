from django.db import models
from django.conf import settings
from companies.models import Company

#매치업 
class Comparison(models.Model):
    comparison_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comparisons')
    # 2. 사용자가 직접 지정할 리스트 이름 (예: "반도체 대장주 비교")
    title = models.CharField(max_length=100) 
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_comparison'

#매치업 안에 담길 기업 리스트
class ComparisonCompany(models.Model):
    comparison_company_id = models.AutoField(primary_key=True)
    comparison = models.ForeignKey(Comparison, on_delete=models.CASCADE, related_name='comparison_items')
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'comparison_company'
        unique_together = ('comparison', 'company') # 중복 담기 방지