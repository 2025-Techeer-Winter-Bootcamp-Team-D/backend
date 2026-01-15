# companies/serializers.py
from rest_framework import serializers
from .models import IndustryRanking

class IndustryRankingSerializer(serializers.ModelSerializer):
    # 명세서의 industryId는 Industry 모델의 industry_id값을 가져옵니다.
    industryId = serializers.IntegerField(source='industry.industry_id')
    
    # 명세서의 name은 Industry 모델의 name값을 가져옵니다.
    name = serializers.CharField(source='industry.name')
    amount = serializers.IntegerField()
    class Meta:
        model = IndustryRanking
        # 명세서에서 요구한 필드 순서대로 구성합니다.
        fields = ['rank', 'industryId', 'name', 'amount']