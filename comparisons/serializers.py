from rest_framework import serializers
from .models import Comparison, ComparisonCompany
from companies.models import Company

# 1. 기업 상세 (목록/상세 조회 시 출력용)
class CompanyDetailSerializer(serializers.ModelSerializer):
    # 명세서대로 숫자로 출력
    stock_code = serializers.CharField()
    companyName = serializers.CharField(source='company_name', read_only=True)
    
    class Meta:
        model = Company
        fields = ['stock_code', 'companyName']

# 2. 매치업 목록용 (id, name)
class ComparisonSimpleSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='comparison_id', read_only=True)
    name = serializers.CharField(source='title')
    
    class Meta:
        model = Comparison
        fields = ['id', 'name']

# 3. 매치업 생성용 (name, companies)
class ComparisonCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='title')
    companies = serializers.ListField(child=serializers.CharField(), write_only=True)

    class Meta:
        model = Comparison
        fields = ['name', 'companies']

    # [핵심] 생성 시 5개 제한 로직
    def validate_companies(self, value):
        if len(value) > 5:
            raise serializers.ValidationError("기업은 최대 5개까지만 담을 수 있습니다.")
        return value

    def create(self, validated_data):
        company_codes = validated_data.pop('companies', [])
        comparison = Comparison.objects.create(**validated_data)

        unique_codes = list(dict.fromkeys(company_codes))
        for code in company_codes:
            try:
                company = Company.objects.get(stock_code=code)
                ComparisonCompany.objects.create(comparison=comparison, company=company)
            except Company.DoesNotExist:
                continue
        return comparison

# 4. 기업 개별 추가용 (POST /api/comparisons/{id}/)
class ComparisonItemAddSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComparisonCompany
        fields = ['company']

    # [핵심] 한 개씩 추가할 때도 5개 제한 체크
    def validate(self, data):
        comparison = self.context.get('comparison')
        company = data.get('company')

        if comparison:
            #  1. 중복 체크
            if ComparisonCompany.objects.filter(comparison=comparison, company=company).exists():
                raise serializers.ValidationError("이미 이 매치업에 등록된 기업입니다.")

            # 2. 5개 제한 체크
            if ComparisonCompany.objects.filter(comparison=comparison).count() >= 5:
                raise serializers.ValidationError("기업은 최대 5개까지만 담을 수 있습니다.")
                
        return data

# 5. Swagger 응답 규격용
class ComparisonDetailDataSerializer(serializers.Serializer):
    count = serializers.IntegerField(required=False)
    comparisons = ComparisonSimpleSerializer(many=True, required=False)
    companyCount = serializers.IntegerField(required=False)
    companies = CompanyDetailSerializer(many=True, required=False)

class ComparisonDetailResponseSerializer(serializers.Serializer):
    status = serializers.IntegerField(default=200)
    message = serializers.CharField(default="기업 비교 조회를 성공하였습니다.")
    data = ComparisonDetailDataSerializer()