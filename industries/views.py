# industries/views.py
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status, serializers
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer, OpenApiParameter
from django.core.paginator import Paginator
from companies.models import Company
from .models import Industry, IndustryRanking
from companies.serializers import CompanyRankingSerializer
from industries.serializers import IndustryRankingSerializer
from news.models import CompanyNews
from news.serializers import IndustryNewsSerializer


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
                    "data": CompanyRankingSerializer(many=True),  # 리스트 형태임을 명시
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

        # 4. 시리얼라이징 - rank 데이터를 함께 전달
        serializer_data = []
        for company in companies:
            serializer_data.append({
                'rank': rank_dict[company.stock_code],
                'name': company.company_name,
                'stock_code': company.stock_code,
                'amount': company.market_amount,
                'logo': company.logo_url
            })

        # 5. 최종 응답 형식 맞추기
        return Response(
            {
                "status": 200,
                "message": "해당 산업 내 기업 순위 조회를 성공하였습니다.",
                "data": serializer_data,
            },
            status=status.HTTP_200_OK,
        )


#------------산업 순위 조회--------------------------
@extend_schema(
    summary="전체 산업 순위 조회",
    description="최신 기준 날짜의 산업별 성과(시가총액 합계) 순위를 조회합니다.",
    responses={
        200: inline_serializer(
            name="IndustryRankingsResponse",
            fields={
                "status": serializers.IntegerField(),
                "message": serializers.CharField(default="전체 산업 순위 조회를 성공하였습니다."),
                "data": IndustryRankingSerializer(many=True),
            },
        ),
        404: OpenApiResponse(description="industry_rankings Not Found")
    },
    tags=["Ranking"]
)
@api_view(["GET"])
def get_industry_rankings(request):
    # 최신 기준 날짜 가져오기
    latest_date = IndustryRanking.objects.filter(is_deleted=False).order_by('-base_date').values_list('base_date', flat=True).first()
    if not latest_date:
        return Response({"status" : 404,
                         "message": "industry_rankings not found"}, status=status.HTTP_404_NOT_FOUND)
    # 해당 날짜의 산업 순위 데이터 조회 (N + 1 문제 방지를 위해 select_related 사용)
    rankings = IndustryRanking.objects.filter(base_date=latest_date, is_deleted=False).select_related('industry').order_by('rank')
    # 시리얼라이징
    serializer = IndustryRankingSerializer(rankings, many=True)
    # 최종 응답 반환
    return Response({
        "status": 200,
        "message": "전체 산업 순위 조회를 성공하였습니다.",
        "data": serializer.data
    }, status=status.HTTP_200_OK)


# ------------산업 뉴스 조회--------------------------
@extend_schema(
    summary="산업 뉴스 조회",
    description="특정 산업에 속한 기업들의 뉴스를 조회합니다. "
    "Industry → Company → CompanyNews → News 조인을 통해 해당 산업의 모든 관련 뉴스를 반환합니다.",
    parameters=[
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            description="페이지 번호 (기본값: 1)",
            required=False,
        ),
        OpenApiParameter(
            name="page_size",
            type=int,
            location=OpenApiParameter.QUERY,
            description="페이지당 뉴스 수 (기본값: 20, 최대: 100)",
            required=False,
        ),
    ],
    responses={
        200: inline_serializer(
            name="IndustryNewsResponse",
            fields={
                "status": serializers.IntegerField(),
                "message": serializers.CharField(
                    default="산업 뉴스 조회를 성공하였습니다."
                ),
                "data": inline_serializer(
                    name="IndustryNewsData",
                    fields={
                        "industry_id": serializers.IntegerField(),
                        "industry_name": serializers.CharField(),
                        "total_count": serializers.IntegerField(),
                        "total_pages": serializers.IntegerField(),
                        "current_page": serializers.IntegerField(),
                        "page_size": serializers.IntegerField(),
                        "news": IndustryNewsSerializer(many=True),
                    },
                ),
            },
        ),
        404: OpenApiResponse(
            description="산업을 찾을 수 없음",
            response=inline_serializer(
                name="IndustryNewsNotFoundResponse",
                fields={
                    "status": serializers.IntegerField(default=404),
                    "code": serializers.CharField(default="NOT_FOUND"),
                    "message": serializers.CharField(
                        default="해당 산업을 찾을 수 없습니다."
                    ),
                },
            ),
        ),
    },
    tags=["Industry"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_industry_news(request, industry_id):
    """
    산업 뉴스 조회 API

    해당 산업에 속한 기업들의 뉴스를 조회합니다.
    Industry → Company → CompanyNews → News 조인으로 관련 뉴스를 가져옵니다.
    """
    # 1. 산업 존재 여부 확인
    try:
        industry = Industry.objects.get(pk=industry_id, is_deleted=False)
    except Industry.DoesNotExist:
        return Response(
            {
                "status": 404,
                "code": "NOT_FOUND",
                "message": "해당 산업을 찾을 수 없습니다.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 2. 페이지네이션 파라미터
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
    except (ValueError, TypeError):
        return Response(
            {"status": 400, "error": "page와 page_size는 정수여야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if page < 1:
        return Response(
            {"status": 400, "error": "page는 1 이상이어야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    page_size = max(1, min(page_size, 100))

    # 3. 해당 산업의 기업들에 연결된 뉴스 조회
    # Industry → Company → CompanyNews → News
    company_news_qs = (
        CompanyNews.objects.filter(
            company__industry=industry,
            company__is_deleted=False,
            news__is_deleted=False,
        )
        .select_related("news", "company")
        .order_by("-news__published_at")
    )

    # 4. 페이지네이션
    paginator = Paginator(company_news_qs, page_size)
    total_count = paginator.count
    total_pages = paginator.num_pages

    news_page = paginator.get_page(page)

    # 5. Serializer
    serializer = IndustryNewsSerializer(news_page.object_list, many=True)

    return Response(
        {
            "status": 200,
            "message": "산업 뉴스 조회를 성공하였습니다.",
            "data": {
                "industry_id": industry.industry_id,
                "industry_name": industry.name,
                "total_count": total_count,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "news": serializer.data,
            },
        },
        status=status.HTTP_200_OK,
    )
