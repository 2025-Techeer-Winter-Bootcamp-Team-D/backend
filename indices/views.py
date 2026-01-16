from rest_framework.views import APIView
from rest_framework.response import Response
from .models import MarketIndex
from datetime import datetime, timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

class IndexListView(APIView):
    @extend_schema(
        summary="시장 지수 조회",
        description="KOSPI 또는 KOSDAQ의 최근 1년치 지수 데이터를 조회합니다.",
        parameters=[
            OpenApiParameter(
                name='market_type',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description='시장 타입 (kospi 또는 kosdaq)',
                enum=['kospi', 'kosdaq']
            )
        ]
    )
    def get(self, request, market_type):
        """
        market_type: kospi 또는 kosdaq
        """
        # 최근 1년(365일) 데이터 조회
        one_year_ago = datetime.now().date() - timedelta(days=365)
        
        queryset = MarketIndex.objects.filter(
            market_type=market_type.upper(),
            idx_date__gte=one_year_ago
        ).order_by('idx_date')
        
        
       
        data = [
            {
                "date": obj.idx_date.strftime('%Y-%m-%d'),
                "value": float(obj.value),
                "volume": obj.volume,
                "amount": obj.amount
            }
            for obj in queryset
        ]
        
        return Response({
            "status": 200,
            "message": "시장 지수 조회를 성공하였습니다.",
            "data": {
                "market": market_type.upper(),
                "count": len(data),
                "indices": data # 형님 응답 규격에 맞게 살짝 맞춤
            }
        })