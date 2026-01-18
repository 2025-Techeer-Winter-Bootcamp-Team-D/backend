from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiTypes,
    inline_serializer,
)

from .models import Comparison, ComparisonCompany
from .serializers import (
    ComparisonSimpleSerializer,
    ComparisonCreateSerializer,
    CompanyDetailSerializer,
    ComparisonItemAddSerializer,
    ComparisonDetailResponseSerializer,
    ComparisonNameUpdateSerializer,
)


class ComparisonBaseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="기업 비교 목록 조회",
        responses={200: ComparisonDetailResponseSerializer},
        tags=["Comparison"],
    )
    def get(self, request):
        queryset = Comparison.objects.filter(user=request.user, is_deleted=False)
        return Response(
            {
                "status": 200,
                "message": "기업 비교 조회를 성공하였습니다.",
                "data": {
                    "count": queryset.count(),
                    "comparisons": ComparisonSimpleSerializer(queryset, many=True).data,
                },
            }
        )

    @extend_schema(
        summary="기업 비교 매치업 생성",
        request=ComparisonCreateSerializer,
        tags=["Comparison"],
    )
    def post(self, request):
        serializer = ComparisonCreateSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid(raise_exception=True):
            serializer.save(user=request.user)
            return Response({"status": 201, "message": "생성 성공"}, status=201)


# [클래스 1] 기존 주소용: GET(상세), POST(추가), DELETE(방전체삭제)
class ComparisonDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="기업 비교 상세 조회",
        responses={200: ComparisonDetailResponseSerializer},
        tags=["Comparison"],
    )
    def get(self, request, comparison_id):  # stock_code 인자 제거
        comparison = get_object_or_404(
            Comparison, comparison_id=comparison_id, user=request.user
        )
        items = ComparisonCompany.objects.filter(comparison=comparison)
        companies = [item.company for item in items]
        return Response(
            {
                "status": 200,
                "message": "기업 비교 조회를 성공하였습니다.",
                "data": {
                    "companyCount": len(companies),
                    "companies": CompanyDetailSerializer(companies, many=True).data,
                },
            }
        )

    @extend_schema(
        summary="비교할 기업 추가",
        request=ComparisonItemAddSerializer,
        tags=["Comparison"],
    )
    def post(self, request, comparison_id):  # stock_code 인자 제거
        comparison = get_object_or_404(
            Comparison, comparison_id=comparison_id, user=request.user
        )
        serializer = ComparisonItemAddSerializer(
            data=request.data, context={"comparison": comparison}
        )
        if serializer.is_valid(raise_exception=True):
            serializer.save(comparison=comparison)
            return Response({"status": 201, "message": "기업 추가 성공"}, status=201)

    @extend_schema(
        summary="매치업 전체 삭제",
        tags=["Comparison"],
    )
    def delete(self, request, comparison_id):  # stock_code 인자 제거
        comparison = get_object_or_404(
            Comparison, comparison_id=comparison_id, user=request.user
        )
        comparison.delete()
        return Response({"status": 200, "message": "매치업 삭제 완료"})

    @extend_schema(
        summary="기업 비교 매치업 이름 변경",
        request=ComparisonNameUpdateSerializer,
        tags=["Comparison"],
    )
    def patch(self, request, comparison_id):
        # 1. 내 매치업인지 확인
        comparison = get_object_or_404(
            Comparison, comparison_id=comparison_id, user=request.user
        )

        # 2. partial=True를 주어 이름만 수정 가능하게 함
        serializer = ComparisonNameUpdateSerializer(
            comparison, data=request.data, partial=True
        )

        if serializer.is_valid(raise_exception=True):
            serializer.save()
            # 3. 형님이 원하셨던 응답 포맷
            return Response(
                {
                    "status": 200,
                    "message": "기업 비교 매치업 이름 변경을 성공하였습니다.",
                    "data": {
                        "comparisons": [
                            {
                                "id": comparison.comparison_id,
                                "name": comparison.title,  # 업데이트된 title(name) 출력
                            }
                        ]
                    },
                },
                status=status.HTTP_200_OK,
            )


# [클래스 2] 새 주소용: DELETE(특정 기업 삭제)
class ComparisonCompanyDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="특정 기업만 삭제",
        tags=["Comparison"],
    )
    def delete(self, request, comparison_id, stock_code):
        comparison = get_object_or_404(
            Comparison, comparison_id=comparison_id, user=request.user
        )
        item = ComparisonCompany.objects.filter(
            comparison=comparison, company__stock_code=stock_code
        ).first()

        if item:
            item.delete()
            return Response({"status": 200, "message": f"기업({stock_code}) 삭제 완료"})
        return Response(
            {"status": 404, "message": "해당 기업을 찾을 수 없습니다."}, status=404
        )
