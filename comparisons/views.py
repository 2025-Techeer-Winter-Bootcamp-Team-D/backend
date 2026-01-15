from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes, inline_serializer

from .models import Comparison, ComparisonCompany
from .serializers import (
    ComparisonSimpleSerializer, 
    ComparisonCreateSerializer, 
    CompanyDetailSerializer, 
    ComparisonItemAddSerializer,
    ComparisonDetailResponseSerializer
)

class ComparisonBaseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="기업 비교 목록 조회", responses={200: ComparisonDetailResponseSerializer})
    def get(self, request):
        queryset = Comparison.objects.filter(user=request.user, is_deleted=False)
        return Response({
            "status": 200, "message": "기업 비교 조회를 성공하였습니다.",
            "data": {
                "count": queryset.count(),
                "comparisons": ComparisonSimpleSerializer(queryset, many=True).data
            }
        })

    @extend_schema(summary="기업 비교 매치업 생성", request=ComparisonCreateSerializer)
    def post(self, request):
        serializer = ComparisonCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid(raise_exception=True):
            serializer.save(user=request.user)
            return Response({"status": 201, "message": "생성 성공"}, status=201)

# [클래스 1] 기존 주소용: GET(상세), POST(추가), DELETE(방전체삭제)
class ComparisonDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="기업 비교 상세 조회", responses={200: ComparisonDetailResponseSerializer})
    def get(self, request, comparison_id): # stock_code 인자 제거
        comparison = get_object_or_404(Comparison, comparison_id=comparison_id, user=request.user)
        items = ComparisonCompany.objects.filter(comparison=comparison)
        companies = [item.company for item in items]
        return Response({
            "status": 200, "message": "기업 비교 조회를 성공하였습니다.",
            "data": {
                "companyCount": len(companies),
                "companies": CompanyDetailSerializer(companies, many=True).data
            }
        })

    @extend_schema(summary="비교할 기업 추가", request=ComparisonItemAddSerializer)
    def post(self, request, comparison_id): # stock_code 인자 제거
        comparison = get_object_or_404(Comparison, comparison_id=comparison_id, user=request.user)
        serializer = ComparisonItemAddSerializer(data=request.data, context={'comparison': comparison})
        if serializer.is_valid(raise_exception=True):
            serializer.save(comparison=comparison)
            return Response({"status": 201, "message": "기업 추가 성공"}, status=201)

    @extend_schema(summary="매치업 전체 삭제")
    def delete(self, request, comparison_id): # stock_code 인자 제거
        comparison = get_object_or_404(Comparison, comparison_id=comparison_id, user=request.user)
        comparison.delete()
        return Response({"status": 200, "message": "매치업 삭제 완료"})

# [클래스 2] 새 주소용: DELETE(특정 기업 삭제) 딱 하나만!
class ComparisonCompanyDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="특정 기업만 삭제")
    def delete(self, request, comparison_id, stock_code):
        comparison = get_object_or_404(Comparison, comparison_id=comparison_id, user=request.user)
        item = ComparisonCompany.objects.filter(
            comparison=comparison, 
            company__stock_code=stock_code
        ).first()
        
        if item:
            item.delete()
            return Response({"status": 200, "message": f"기업({stock_code}) 삭제 완료"})
        return Response({"status": 404, "message": "해당 기업을 찾을 수 없습니다."}, status=404)