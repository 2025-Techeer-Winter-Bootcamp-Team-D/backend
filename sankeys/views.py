from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from .models import FinancialFlow
from .serializers import FinancialFlowSerializer
from .services import FinancialFlowService
from companies.models import Company

class FinancialSankeyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="기업별 재무 Sankey 데이터 조회")
    def get(self, request, stock_code):
        try:
            # 1. 기업 조회 (필터로 안전하게)
            company = Company.objects.filter(stock_code=stock_code).first()
            if not company:
                return Response({"error": "존재하지 않는 종목코드입니다."}, status=404)

            # 2. 데이터 조회 (최신 연도 우선)
            flow = FinancialFlow.objects.filter(company=company).order_by('-year').first()
            
            # 3. 데이터가 없을 경우 404 응답
            if not flow:
                return Response({
                    "company_name": company.company_name,
                    "error": "해당 기업의 재무 데이터가 준비되지 않았습니다."
                }, status=404)

            serializer = FinancialFlowSerializer(flow)
            return Response(serializer.data)

        except Exception as e:
            print(f"🔥 GET Error: {str(e)}")
            return Response({"error": f"서버 내부 오류: {str(e)}"}, status=500)

class AdminSankeyUpdateView(APIView):
    permission_classes = [IsAdminUser]

    # [형님 필독] 여기서 year 입력창을 다시 살렸습니다!
    @extend_schema(
        summary="전 종목 재무 데이터 수집 및 보정",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer", 
                        "description": "수집할 연도", 
                        "example": 2024
                    }
                },
                "required": ["year"]
            }
        },
        responses={200: "성공적으로 업데이트되었습니다."}
    )
    def post(self, request):
        year = request.data.get('year')
        if not year:
            return Response({"error": "JSON 바디에 'year'가 필요합니다."}, status=400)

        # 기존 데이터 삭제
        #FinancialFlow.objects.filter(year=year).delete()

        service = FinancialFlowService()
        companies = Company.objects.all()
        success_count = 0

        for company in companies:
            try:
                # 보정 로직이 포함된 서비스 호출
                if service.fetch_and_save_financials(company, year):
                    success_count += 1
            except Exception as e:
                print(f"❌ {company.stock_code} 수집 에러: {e}")
                continue
        
        return Response({
            "status": "success", 
            "message": f"{year}년 데이터 업데이트 완료 ({success_count}개 성공)"
        })