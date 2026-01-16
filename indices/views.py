from rest_framework.views import APIView
from rest_framework.response import Response
from .models import MarketIndex
from datetime import datetime, timedelta

class IndexListView(APIView):
    def get(self, request, market_type):
        """
        market_type: kospi 또는 kosdaq
        """
        # 최근 1년(365일) 데이터 조회
        one_year_ago = datetime.now().date() - timedelta(days=365)
        
        queryset = MarketIndex.objects.filter(
            market_type=market_type.upper(),
            idx_date__gte=one_year_ago
        ).order_by('idx_date') # 그래프를 그리려면 날짜 오름차순 정렬이 필요함
        
        
       
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
            "market": market_type.upper(),
            "count": len(data),
            "data": data
        })