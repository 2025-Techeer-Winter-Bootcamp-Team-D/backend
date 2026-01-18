# companies/serializers.py ->  모델 데이터를 JSON 형식으로 변환해주는 도구

from rest_framework import serializers
from .models import (
    Company,
    FinancialStatement,
    RevenueComposition,
    Report,
    CompanyRanking,
)
from .services.logo import get_logo_url
from industries.models import Industry
from industries.serializers import IndustrySerializer


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

    def get_logo_url(self, obj):
        """DB에 저장된 logo_url이 없으면 Logo.dev에서 동적 생성"""
        if obj.logo_url:
            return obj.logo_url
        if obj.homepage_url:
            return get_logo_url(homepage_url=obj.homepage_url)
        return None

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
            "metrics_calculated_at",
        ]

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

    class Meta:
        model = RevenueComposition
        fields = ["segment_name", "revenue", "ratio"]


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
            "created_at",
        ]

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

    def get_logo(self, obj):
        """DB에 저장된 logo_url이 없으면 Logo.dev에서 동적 생성"""
        company = obj.stock_code
        if company.logo_url:
            return company.logo_url
        if company.homepage_url:
            return get_logo_url(homepage_url=company.homepage_url)
        return None
