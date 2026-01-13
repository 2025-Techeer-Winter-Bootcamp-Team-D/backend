# companies/serializers.py ->  모델 데이터를 JSON 형식으로 변환해주는 도구

from rest_framework import serializers
from .models import Company

class CompanySerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()
    class Meta:
        model = Company
        fields = ['ticker_symbol', 'company_name', 'description', 'rank']
        
 
    def get_rank(self, obj):
        return self.context.get('rank_dict', {}).get(obj.ticker_symbol, None)