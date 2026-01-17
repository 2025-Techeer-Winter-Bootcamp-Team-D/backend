from rest_framework import serializers
from .models import FinancialFlow

class FinancialFlowSerializer(serializers.ModelSerializer):
    company_name = serializers.ReadOnlyField(source='company.company_name')
    stock_code = serializers.ReadOnlyField(source='company.stock_code')

    class Meta:
        model = FinancialFlow
        fields = [
            'company_name', 'stock_code', 'year', 'total_revenue',
            'source_rev_val', 'source_fin_val', 'source_oth_val', 'source_etc_val',
            'net_loss_val', 'cost_of_sales', 'sg_and_a', 'finance_costs',
            'tax_costs', 'net_income_val'
        ]