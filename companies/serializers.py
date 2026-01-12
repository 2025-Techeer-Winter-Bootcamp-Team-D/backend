# companies/serializers.py
from rest_framework import serializers
from .models import Company

class CompanyDetailSerializer(serializers.ModelSerializer):
    # 명세서의 필드명에 맞게 매핑
    companyId = serializers.IntegerField(source='company_id')
    industryId = serializers.IntegerField(source='industry.industry_id')
    name = serializers.CharField(source='company_name')
    symbol = serializers.CharField(source='ticker_symbol')
    rankInIndustry = serializers.IntegerField(source='rank_in_industry')

    class Meta:
        model = Company
        fields = ['companyId', 'industryId', 'name', 'symbol', 'description', 'rankInIndustry']