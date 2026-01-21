# companies/serializers.py ->  모델 데이터를 JSON 형식으로 변환해주는 도구

from rest_framework import serializers
from .models import (
    Company,
    FinancialStatement,
    RevenueComposition,
    Report,
    CompanyRanking,
    SankeyData,
)
from .services.logo import get_logo_url
from industries.models import Industry
from industries.serializers import IndustrySerializer
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes


class CompanyDetailSerializer(serializers.ModelSerializer):
    industry = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "stock_code",
            "corp_code",
            "company_name",
            "market",
            "induty_code",
            "industry",
            "description",
            "logo_url",
            "market_amount",
            "ceo_name",
            "establishment_date",
            "homepage_url",
            "address",
        ]

    @extend_schema_field(OpenApiTypes.URI)
    def get_logo_url(self, obj):
        """DB에 저장된 logo_url이 없으면 Logo.dev에서 동적 생성"""
        if obj.logo_url:
            return obj.logo_url
        if obj.homepage_url:
            return get_logo_url(homepage_url=obj.homepage_url)
        return None

    @extend_schema_field(IndustrySerializer)
    def get_industry(self, obj):
        """업종코드로 Industry 조회"""
        if not obj.induty_code:
            return None

        try:
            # 업종코드로 직접 조회
            industry = Industry.objects.filter(
                induty_code=obj.induty_code, is_deleted=False
            ).first()

            # 상위 분류 코드로 조회 시도
            if not industry:
                for code_length in range(len(obj.induty_code) - 1, 0, -1):
                    parent_code = obj.induty_code[:code_length]
                    industry = Industry.objects.filter(
                        induty_code=parent_code, is_deleted=False
                    ).first()
                    if industry:
                        break

            if industry:
                return IndustrySerializer(industry).data
        except Industry.DoesNotExist:
            return None
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Industry 조회 실패 (induty_code: {obj.induty_code}): {e}")

        return None


class FinancialStatementSerializer(serializers.ModelSerializer):
    """재무제표 Serializer"""

    report_type = serializers.SerializerMethodField()

    # Decimal 필드를 숫자로 직렬화 (문자열이 아닌)
    roe = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    debt_ratio = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    per = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    pbr = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    dividend_yield = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    eps = serializers.DecimalField(
        max_digits=15, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    operating_profit_margin = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    yoy_revenue = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    yoy_operating_profit = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )
    yoy_net_income = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, allow_null=True
    )

    class Meta:
        model = FinancialStatement
        fields = [
            "fiscal_year",
            "report_type",
            "revenue",
            "operating_profit",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
            # 계산된 재무 지표
            "roe",
            "debt_ratio",
            "per",
            "pbr",
            "dividend_yield",
            "eps",
            "operating_profit_margin",
            "yoy_revenue",
            "yoy_operating_profit",
            "yoy_net_income",
            "metrics_calculated_at",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_report_type(self, obj):
        """보고서 코드를 보고서명으로 변환"""
        report_types = {
            "11011": "사업보고서",
            "11012": "반기보고서",
            "11013": "1분기보고서",
            "11014": "3분기보고서",
        }
        return report_types.get(obj.report_code, "기타")


class RevenueCompositionSerializer(serializers.ModelSerializer):
    """매출 구성 Serializer"""

    ratio = serializers.SerializerMethodField()

    class Meta:
        model = RevenueComposition
        fields = ["segment_name", "revenue", "ratio"]

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_ratio(self, obj):
        """ratio를 소수점 형태(0.58)로 반환 (백분율 58%를 0.58로 변환)"""
        if obj.ratio is not None:
            # DB에 저장된 ratio는 백분율(%)이므로 소수점으로 변환
            return float(obj.ratio) / 100.0
        return None


class CompanyFinancialsSerializer(serializers.Serializer):
    """기업 재무 지표 응답 Serializer"""

    stock_code = serializers.CharField()
    company_name = serializers.CharField()
    market_amount = serializers.IntegerField(max_value=2**63 - 1)
    financial_statements = FinancialStatementSerializer(many=True)
    revenue_composition = RevenueCompositionSerializer(many=True)


class ReportSerializer(serializers.ModelSerializer):
    """보고서 Serializer"""

    report_type = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "rcept_no",
            "report_name",
            "report_type",
            "submitted_at",
            "report_url",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_report_type(self, obj):
        """공시유형 표시명 반환"""
        return obj.get_report_type_display()


class ReportDetailSerializer(serializers.ModelSerializer):
    """보고서 상세 Serializer (분석 결과 포함)"""

    report_type = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "rcept_no",
            "report_name",
            "report_type",
            "submitted_at",
            "report_url",
            "extracted_info",
            "primary_keyword",
            "created_at",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_report_type(self, obj):
        """공시유형 표시명 반환"""
        return obj.get_report_type_display()


class ReportListSerializer(serializers.Serializer):
    """보고서 목록 응답 Serializer"""

    total_count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    reports = ReportSerializer(many=True)

    def to_representation(self, instance):
        """직접 딕셔너리를 반환하도록 오버라이드"""
        return instance


class CompanyRankingSerializer(serializers.ModelSerializer):
    # stock_code(FK)을 통해 Company 모델의 필드에 접근합니다.
    stock_code = serializers.CharField(source="stock_code.stock_code")
    name = serializers.CharField(source="stock_code.company_name")
    logo = serializers.SerializerMethodField()
    amount = serializers.IntegerField(source="stock_code.market_amount")
    rank = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = CompanyRanking
        fields = ["rank", "name", "stock_code", "amount", "logo"]

    @extend_schema_field(OpenApiTypes.URI)
    def get_logo(self, obj):
        """DB에 저장된 logo_url이 없으면 Logo.dev에서 동적 생성"""
        company = obj.stock_code
        if company.logo_url:
            return company.logo_url
        if company.homepage_url:
            return get_logo_url(homepage_url=company.homepage_url)
        return None


#sankey seiralizers
class SankeySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    total_revenue = serializers.SerializerMethodField()
    segments = serializers.SerializerMethodField()
    expenses = serializers.SerializerMethodField()
    fiscal_year = serializers.CharField()

    class Meta:
        model = SankeyData
        fields = ['company_name', 'fiscal_year', 'total_revenue', 'is_loss', 'segments', 'expenses']

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_revenue(self, obj):
        """총 매출액 추출"""
        return obj.raw_values.get('total_revenue', 0)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_segments(self, obj):
        """왼쪽 노드: 중앙 매출액 노드로 들어오는 모든 source 값(사업부별 매출) 추출"""
        if not obj.nodes:
            return []
        # 중앙 노드(매출액/영업수익)의 이름을 가져옴
        target_name = obj.nodes[0]['name']
        return [{"name": l['source'], "value": l['value']} for l in obj.links if l['target'] == target_name]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_expenses(self, obj):
        """오른쪽 노드: raw_values에 보관된 비용/이익 데이터를 딕셔너리로 반환"""
        rv = obj.raw_values
        return {
            "원가비용": rv.get('cogs', 0),
            "판관비": rv.get('sg_a', 0),
            "순수익": 0 if obj.is_loss else rv.get('net_income', 0),
            "기타비용": rv.get('other_expense', 0)
        }

