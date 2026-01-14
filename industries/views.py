# industries/views.py 혹은 별도 위치
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from companies.models import Company
from .models import Industry
from companies.serializers import CompanySerializer


class IndustryCompanyRankView(APIView):
    @extend_schema(
        summary="산업 내 기업 순위 조회",
        description="특정 산업 ID를 입력받아 해당 산업에 속한 기업들의 순위를 조회합니다.",
        responses={
            200: inline_serializer(
                name="IndustryRankResponse",
                fields={
                    "status": serializers.IntegerField(),
                    "message": serializers.CharField(
                        default="해당 산업 내 기업 순위 조회를 성공하였습니다."
                    ),
                    "data": CompanySerializer(many=True),  # 리스트 형태임을 명시
                },
            ),
            404: OpenApiResponse(
                description="항목을 찾을 수 없음",
                response=inline_serializer(
                    name="NotFoundResponse",
                    fields={
                        "status": serializers.IntegerField(default=404),
                        "code": serializers.CharField(default="NOT_FOUND"),
                        "message": serializers.CharField(
                            default="항목을 찾을 수 없습니다."
                        ),
                    },
                ),
            ),
        },
        tags=["Industry"],
    )
    def get(self, request, industry_id):
        # 1. 산업 존재 여부 확인 (없으면 404 에러 코드 형식에 맞춰 반환)
        try:
            industry = Industry.objects.get(pk=industry_id)
        except Industry.DoesNotExist:
            return Response(
                {
                    "status": 404,
                    "code": "NOT_FOUND",
                    "message": "항목을 찾을 수 없습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. 해당 산업의 기업들을 시가총액 내림차순으로 조회
        companies = Company.objects.filter(
            industry=industry, is_deleted=False
        ).order_by("-market_amount")

        if not companies.exists():
            return Response(
                {
                    "status": 404,
                    "code": "NOT_FOUND",
                    "message": "해당 산업에 등록된 기업이 없습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. 순위 계산 (리스트 인덱스 활용)
        rank_dict = {}
        current_rank = 1

        for i, company in enumerate(companies):
            # 이전 기업과 시가총액이 다를 때만 현재 순위를 갱신
            if i > 0 and company.market_amount < companies[i - 1].market_amount:
                current_rank = i + 1
            rank_dict[company.stock_code] = current_rank

        # 4. 시리얼라이징
        serializer = CompanySerializer(
            companies, many=True, context={"rank_dict": rank_dict}
        )

        # 5. 최종 응답 형식 맞추기
        return Response(
            {
                "status": 200,
                "message": "해당 산업 내 기업 순위 조회를 성공하였습니다.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
