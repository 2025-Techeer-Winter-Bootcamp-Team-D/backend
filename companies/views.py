from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from .models import Company
from .serializers import CompanySerializer

@extend_schema(
    summary="기업 기본 정보 조회",
    description="티커 심볼(PK)을 통해 해당 기업의 정보를 가져옵니다.",
    parameters=[
        OpenApiParameter(
            name='ticker_symbol',
            type=str,
            location=OpenApiParameter.PATH,
            description='조회할 기업의 티커 심볼 (예: 005930)'
        ),
    ],
    responses={200: CompanySerializer, 404: OpenApiResponse(description="Not Found")},
    tags=["Company"]
)
@api_view(["GET"])
def get_company_info(request, ticker_symbol):
    try:
        company = Company.objects.get(pk=ticker_symbol, is_deleted=False)
        serializer = CompanySerializer(company)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Company.DoesNotExist:
        return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)