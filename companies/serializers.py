# companies/serializers.py ->  모델 데이터를 JSON 형식으로 변환해주는 도구

from rest_framework import serializers
from .models import Company, CompanyRanking

class CompanySerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()
    class Meta:
        model = Company
        fields = ['ticker_symbol', 'company_name', 'description', 'rank']
        
 
    def get_rank(self, obj):
        return self.context.get('rank_dict', {}).get(obj.ticker_symbol, None)
    
class CompanyRankingSerializer(serializers.ModelSerializer):
    # ticker_symbol(FK)을 통해 Company 모델의 필드에 접근합니다.
    companyId = serializers.CharField(source='ticker_symbol.ticker_symbol')
    name = serializers.CharField(source='ticker_symbol.company_name')
    logo = serializers.URLField(source='ticker_symbol.logo')
    amount = serializers.IntegerField(source='ticker_symbol.market_amount')

    class Meta:
        model = CompanyRanking
        fields = ['rank', 'companyId', 'name', 'logo', 'amount']