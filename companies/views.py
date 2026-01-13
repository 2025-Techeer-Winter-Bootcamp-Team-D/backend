from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from .models import Company, CompanyRanking
from .serializers import CompanySerializer, CompanyRankingSerializer

#------------------------ 기업 기본 정보 조회--------------------------
@extend_schema(
    summary="기업 기본 정보 조회",
    description="티커 심볼(PK)을 통해 해당 기업의 정보를 가져옵니다.",
    parameters=[
        OpenApiParameter(
            name='stock_code',
            type=str,
            location=OpenApiParameter.PATH,
            description='조회할 기업의 티커 심볼 (예: 005930)'
        ),
    ],
    responses={200: CompanySerializer, 404: OpenApiResponse(description="Not Found")},
    tags=["Company"]
)
@api_view(["GET"])
def get_company_info(request, stock_code):
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)
        serializer = CompanySerializer(company)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Company.DoesNotExist:
        return Response({"status": 404,
                         "message": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

#------------------------ 기업 순위----------------------------------  
@extend_schema(
    summary="전체 기업 순위 조회",
    description="최신 기준 날짜의 기업 순위 리스트를 가져옵니다.",
    responses={
        200: CompanyRankingSerializer(many=True),
        404: OpenApiResponse(description="company_rankings Not Found")
    },
    tags=["Ranking"]
)
@api_view(["GET"])
def get_company_rankings(request):
    # 가장 최신 기준 날짜 조회
    latest_date = CompanyRanking.objects.filter(is_deleted=False).order_by('-base_date').values_list('base_date', flat=True).first()
    if not latest_date:
        return Response({"status" : 404,
                         "message": "company_rankings not found"}, status=status.HTTP_404_NOT_FOUND)
    # 데이터 조회
    rankings = CompanyRanking.objects.filter(base_date=latest_date, is_deleted=False).select_related('stock_code').order_by('rank')
    # 데이터 직렬화
    serializer = CompanyRankingSerializer(rankings, many=True)
    # 명세서 규격에 맞춘 최종 응답 반환
    return Response({
        "status": 200,
        "message": "전체 기업 순위 조회를 성공하였습니다.",
        "data": serializer.data
    }, status=status.HTTP_200_OK)