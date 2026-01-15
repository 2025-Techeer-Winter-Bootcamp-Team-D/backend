# companies/serializers.py ->  모델 데이터를 JSON 형식으로 변환해주는 도구

from rest_framework import serializers
from .models import Company, CompanyRanking

class CompanySerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()
    class Meta:
        model = Company
        fields = ['stock_code', 'company_name', 'description', 'rank']
        
 
    def get_rank(self, obj):
        return self.context.get('rank_dict', {}).get(obj.stock_code, None)
    
class CompanyRankingSerializer(serializers.ModelSerializer):
    # stock_code(FK)을 통해 Company 모델의 필드에 접근합니다.
    companyId = serializers.CharField(source='stock_code.stock_code')
    name = serializers.CharField(source='stock_code.company_name')
    logo = serializers.URLField(source='stock_code.logo_url')
    amount = serializers.IntegerField(source='stock_code.market_amount')

    class Meta:
        model = CompanyRanking
        fields = ['rank', 'companyId', 'name', 'logo', 'amount']