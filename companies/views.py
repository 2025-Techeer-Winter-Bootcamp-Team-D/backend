# companies/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiResponse
from .models import Company
from .serializers import CompanyDetailSerializer

class CompanyDetailAPIView(APIView):
    @extend_schema(
        summary="기업 기본 정보 조회",
        responses={
            200: CompanyDetailSerializer,
            404: OpenApiResponse(description="기업을 찾을 수 없습니다.")
        },
        tags=["Company"]
    )
    def get(self, request, company_id):
        # 1. DB에서 데이터 조회
        company = Company.objects.filter(company_id=company_id).first()

        # 2. 데이터가 없는 경우 명세서에 따른 404 반환
        if not company:
            return Response({
                "status": 404,
                "message": "기업을 찾을 수 없습니다."
            }, status=status.HTTP_404_NOT_FOUND)

        # 3. 데이터가 있는 경우 200 반환
        serializer = CompanyDetailSerializer(company)
        return Response({
            "status": 200,
            "data": serializer.data
        }, status=status.HTTP_200_OK)