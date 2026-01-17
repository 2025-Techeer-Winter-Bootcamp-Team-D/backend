from django.db import models

class FinancialFlow(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE)
    year = models.IntegerField()
    total_revenue = models.DecimalField(max_digits=20, decimal_places=0)

    # 왼쪽 (Sources)
    source_rev_val = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    source_fin_val = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    source_oth_val = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    source_etc_val = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    net_loss_val = models.DecimalField(max_digits=20, decimal_places=0, default=0)

    # 오른쪽 (Targets)
    cost_of_sales = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sg_and_a = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    finance_costs = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    tax_costs = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    net_income_val = models.DecimalField(max_digits=20, decimal_places=0, default=0)

    class Meta:
        unique_together = ('company', 'year')