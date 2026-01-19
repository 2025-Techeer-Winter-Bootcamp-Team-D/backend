# industries/serializers.py
from rest_framework import serializers
from .models import IndustryRanking, Industry


class IndustrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Industry
        fields = ["industry_id", "name", "induty_code"]


class IndustryRankingSerializer(serializers.ModelSerializer):
    # 명세서의 industryId는 Industry 모델의 industry_id값을 가져옵니다.
    industryId = serializers.CharField(source="industry.induty_code")

    # 명세서의 name은 Industry 모델의 name값을 가져옵니다.
    name = serializers.CharField(source="industry.name")
    amount = serializers.IntegerField()

    class Meta:
        model = IndustryRanking
        # 명세서에서 요구한 필드 순서대로 구성합니다.
        fields = ["rank", "industryId", "name", "amount"]


class IndustryIndexSerializer(serializers.ModelSerializer):
    # 모델에 없는 필드이므로 직접 정의
    index_value = serializers.FloatField(source="latest_index_value")
    index_updated_at = serializers.DateField(source="latest_index_date")

    class Meta:
        model = Industry
        fields = [
            "industry_id",
            "name",
            "induty_code",
            "index_value",
            "index_updated_at",
        ]


class IndustryChartSerializer(serializers.Serializer):
    """산업 지수 차트 데이터를 위한 공통 시리얼라이저

    IndustryChart1d, IndustryChart3d, IndustryChart1w, IndustryChart2w 모델 모두에 사용됩니다.
    """

    date = serializers.DateField()
    open = serializers.FloatField()
    high = serializers.FloatField()
    low = serializers.FloatField()
    close = serializers.FloatField()
    change_value = serializers.FloatField(allow_null=True)
    change_rate = serializers.FloatField(allow_null=True)

    def to_representation(self, instance):
        """모델 인스턴스를 시리얼라이저 형식으로 변환"""
        return {
            "date": instance.base_date,
            "open": instance.open,
            "high": instance.high,
            "low": instance.low,
            "close": instance.close,
            "change_value": instance.change_value,
            "change_rate": instance.change_rate,
        }
