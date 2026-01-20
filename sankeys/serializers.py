from rest_framework import serializers
from .models import SankeyData
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

class SankeySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    total_revenue = serializers.SerializerMethodField()
    segments = serializers.SerializerMethodField()
    expenses = serializers.SerializerMethodField()

    class Meta:
        model = SankeyData
        fields = ['company_name', 'fiscal_year', 'total_revenue', 'is_loss', 'segments', 'expenses']

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_revenue(self, obj):
        return obj.raw_values.get('total_revenue', 0)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_segments(self, obj):
        """왼쪽 노드: [ {name: '반도체', value: 100}, ... ]"""
        if not obj.nodes:
            return []
        # 중앙 매출액 노드로 들어오는 모든 source 값만 추출
        target_name = obj.nodes[0]['name']
        return [{"name": l['source'], "value": l['value']} for l in obj.links if l['target'] == target_name]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_expenses(self, obj):
        """오른쪽 노드: 값만 깔끔하게 딕셔너리로"""
        rv = obj.raw_values
        return {
            "원가비용": rv.get('cogs', 0),
            "판관비": rv.get('sg_a', 0),
            "순수익": 0 if obj.is_loss else rv.get('net_income', 0),
            "기타비용": rv.get('other_expense', 0)
        }