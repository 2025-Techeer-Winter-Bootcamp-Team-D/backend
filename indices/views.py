from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from .models import MarketIndex
from datetime import datetime, timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from indices.tasks import initialize_indices_1year


class IndexListView(APIView):
    @extend_schema(
        summary="시장 지수 조회",
        description="KOSPI 또는 KOSDAQ의 최근 1년치 지수 데이터를 조회합니다.",
        parameters=[
            OpenApiParameter(
                name="market_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="시장 타입 (kospi 또는 kosdaq)",
                enum=["kospi", "kosdaq"],
            )
        ],
        tags=["Indices"],
    )
    def get(self, request, market_type):
        """
        market_type: kospi 또는 kosdaq
        """
        # 최근 1년(365일) 데이터 조회
        one_year_ago = datetime.now().date() - timedelta(days=365)

        queryset = MarketIndex.objects.filter(
            market_type=market_type.upper(), idx_date__gte=one_year_ago
        ).order_by("idx_date")

        data = [
            {
                "date": obj.idx_date.strftime("%Y-%m-%d"),
                "value": float(obj.value),
                "volume": obj.volume,
                "amount": obj.amount,
            }
            for obj in queryset
        ]

        return Response(
            {
                "status": 200,
                "message": "시장 지수 조회를 성공하였습니다.",
                "data": {
                    "market": market_type.upper(),
                    "count": len(data),
                    "indices": data,  # 응답 규격에 맞게 살짝 맞춤
                },
            }
        )


class AdminIndexInitializeView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="(관리자용)시장 지수 1년치 데이터 저장(처음 한번만,시간 조금 걸림)",
        description="한국투자증권(KIS) API를 통해 최근 1년치 KOSPI, KOSDAQ 데이터를 수집하여 DB에 저장.",
        tags=["Indices"],
        responses={
            200: OpenApiResponse(description="성공적으로 데이터 수집 태스크가 시작됨"),
            401: OpenApiResponse(description="인증되지 않은 사용자"),
            403: OpenApiResponse(description="관리자 권한 없음"),
            500: OpenApiResponse(description="서버 내부 오류 또는 API 호출 실패")
        }
    )
    def post(self, request):
        try:
            # 1년치 데이터 수집 실행
            initialize_indices_1year()
            return Response(
                {"status": "success", "message": "1년치 데이터 초기화가 성공적으로 완료되었습니다."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": f"초기화 실패: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )