from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions # 권한 추가
from rest_framework_simplejwt.authentication import JWTAuthentication # JWT 인증 추가
from drf_spectacular.utils import extend_schema, OpenApiTypes
from .models import SankeyData
from .serializers import SankeySerializer
from .services import SankeyDataService

class SankeyAdminBulkSyncView(APIView):
    # 관리자 전용 설정 (JWT 인증 + Staff 권한 확인)
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        summary="전체 기업 일괄 업데이트 (Admin 전용)",
        request={"application/json": {"type": "object", "properties": {"year": {"type": "integer", "example": 2024}}}},
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        year = request.data.get('year', 2024)
        results = SankeyDataService().sync_all_companies(year)
        return Response(results, status=status.HTTP_200_OK)

class SankeyDataDetailView(APIView):
    """조회 API는 누구나 접근 가능"""
    serializer_class = SankeySerializer
    def get(self, request, stock_code):
        data = SankeyData.objects.filter(company__stock_code=stock_code).order_by('-fiscal_year').first()
        if not data:
            return Response({"error": "데이터가 없습니다."}, status=404)
        return Response(SankeySerializer(data).data)