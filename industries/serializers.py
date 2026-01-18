# industries/serializers.py
from rest_framework import serializers
from .models import IndustryRanking, Industry


class IndustrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Industry
        fields = ["industry_id", "name", "induty_code"]


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


class IndustryIndexSerializer(serializers.ModelSerializer):
    # 모델에 없는 필드이므로 직접 정의
    index_value = serializers.FloatField(source='latest_index_value')
    index_updated_at = serializers.DateField(source='latest_index_date')
    class Meta:
        model = Industry
        fields = ['industry_id', 'name', 'induty_code', 'index_value', 'index_updated_at']

class IndustryChartSerializer(serializers.ModelSerializer):
    """산업 지수 차트 데이터를 위한 공통 시리얼라이저"""
    date = serializers.DateField(source='base_date')
    
    class Meta:
        # 특정 모델을 고정하지 않고 fields만 정의합니다.
        fields = ['date', 'open', 'high', 'low', 'close', 'change_value', 'change_rate']

    def __init__(self, *args, **kwargs):
        # 호출 시점에 동적으로 모델을 할당합니다.
        if args and len(args) > 0:
            item = args[0][0] if hasattr(args[0], '__iter__') and len(args[0]) > 0 else args[0]
            if item:
                self.Meta.model = item.__class__
        super().__init__(*args, **kwargs)