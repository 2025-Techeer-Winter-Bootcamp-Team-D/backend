# industries/views.py
import logging

from rest_framework.views import APIView
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework import status, serializers
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    inline_serializer,
    OpenApiParameter,
)
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery

from companies.models import Company
from .models import (
    Industry,
    IndustryRanking,
    IndustryChart1d,
    IndustryChart3d,
    IndustryChart1w,
    IndustryChart2w,
)
from .tasks.index_sync import backfill_industry_charts_task
from companies.serializers import CompanyRankingSerializer
from industries.serializers import (
    IndustryRankingSerializer,
    IndustryIndexSerializer,
    IndustryChartSerializer,
)
from news.serializers import IndustryNewsSerializer
from news.models import CompanyNews
from news.serializers import IndustryNewsSerializer

logger = logging.getLogger(__name__)


class IndustryCompanyRankView(APIView):
    @extend_schema(
        summary="산업 내 기업 순위 조회",
        description="특정 산업 업종코드(induty_code)를 입력받아 해당 산업에 속한 기업들의 순위를 조회합니다.",
        parameters=[
            OpenApiParameter(
                name="induty_code",
                type=str,
                location=OpenApiParameter.PATH,
                description="산업 업종코드 (KIS 코드, 예: 0014)",
            ),
        ],
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
        tags=["Rankings"],
    )
    def get(self, request, induty_code):
        # 1. 산업 존재 여부 확인 (induty_code로 조회)
        try:
            industry = Industry.objects.get(induty_code=induty_code, is_deleted=False)
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

        # 3. 순위 계산 (리스트로 변환하여 순위 계산)
        companies_list = list(companies)
        rank_dict = {}
        current_rank = 1
        prev_amount = None

        for i, company in enumerate(companies_list):
            # 이전 기업과 시가총액이 다를 때만 현재 순위를 갱신
            if prev_amount is not None and company.market_amount < prev_amount:
                current_rank = i + 1
            rank_dict[company.stock_code] = current_rank
            prev_amount = company.market_amount

        # 4. 시리얼라이징 - rank 데이터를 함께 전달
        serializer_data = []
        for company in companies_list:
            serializer_data.append(
                {
                    "rank": rank_dict[company.stock_code],
                    "name": company.company_name,
                    "stock_code": company.stock_code,
                    "amount": company.market_amount,
                    "logo": company.logo_url,
                }
            )

        # 5. 최종 응답 형식 맞추기
        return Response(
            {
                "status": 200,
                "message": "해당 산업 내 기업 순위 조회를 성공하였습니다.",
                "data": serializer_data,
            },
            status=status.HTTP_200_OK,
        )


# ------------산업 순위 조회--------------------------
@extend_schema(
    summary="전체 산업 순위 조회",
    description="최신 기준 날짜의 산업별 성과(시가총액 합계) 순위를 조회합니다.",
    responses={
        200: inline_serializer(
            name="IndustryRankingsResponse",
            fields={
                "status": serializers.IntegerField(),
                "message": serializers.CharField(
                    default="전체 산업 순위 조회를 성공하였습니다."
                ),
                "data": IndustryRankingSerializer(many=True),
            },
        ),
        404: OpenApiResponse(description="industry_rankings Not Found"),
    },
    tags=["Rankings"],
)
@api_view(["GET"])
def get_industry_rankings(request):
    # 최신 기준 날짜 가져오기
    latest_date = (
        IndustryRanking.objects.filter(is_deleted=False)
        .order_by("-base_date")
        .values_list("base_date", flat=True)
        .first()
    )
    if not latest_date:
        # 순위 데이터가 없으면 자동으로 생성
        from django.core.management import call_command

        try:
            call_command("update_industry_rankings")
            # 생성 후 다시 조회
            latest_date = (
                IndustryRanking.objects.filter(is_deleted=False)
                .order_by("-base_date")
                .values_list("base_date", flat=True)
                .first()
            )
        except Exception as e:
            logger.error(f"산업 순위 생성 실패: {e}")
            return Response(
                {
                    "status": 500,
                    "message": f"산업 순위 생성 중 오류가 발생했습니다: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not latest_date:
            return Response(
                {"status": 404, "message": "industry_rankings not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
    # 해당 날짜의 산업 순위 데이터 조회 (N + 1 문제 방지를 위해 select_related 사용)
    # 삭제되지 않은 산업만 조회
    rankings = (
        IndustryRanking.objects.filter(
            base_date=latest_date,
            is_deleted=False,
            industry__is_deleted=False,
        )
        .select_related("industry")
        .order_by("rank")
    )
    # 시리얼라이징
    serializer = IndustryRankingSerializer(rankings, many=True)
    # 최종 응답 반환
    return Response(
        {
            "status": 200,
            "message": "전체 산업 순위 조회를 성공하였습니다.",
            "data": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


# ------------산업 뉴스 조회--------------------------
@extend_schema(
    summary="산업 뉴스 조회",
    description="특정 산업에 속한 기업들의 뉴스를 조회합니다. "
    "Industry → Company → CompanyNews → News 조인을 통해 해당 산업의 모든 관련 뉴스를 반환합니다.",
    parameters=[
        OpenApiParameter(
            name="induty_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="산업 업종코드 (KIS 코드, 예: 0014)",
        ),
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
    tags=["News"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_industry_news(request, induty_code):
    """
    산업 뉴스 조회 API

    해당 산업에 속한 기업들의 뉴스를 조회합니다.
    Industry → Company → CompanyNews → News 조인으로 관련 뉴스를 가져옵니다.
    """
    # 1. 산업 존재 여부 확인 (induty_code로 조회)
    try:
        industry = Industry.objects.get(induty_code=induty_code, is_deleted=False)
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


# ------------산업 지수 목록 조회--------------------------
@extend_schema(
    tags=["Industry"],
    summary="산업 지수 목록 조회 (이름순)",
    description="DB에 저장된 모든 산업의 최신 지수 리스트를 반환합니다. 대시보드 왼쪽 리스트에 사용됩니다.",
)
@api_view(["GET"])
def get_industry_indices(request):
    """
    테이블에 저장된 최신 산업 지수들을 반환합니다.
    """
    # 산업 목록을 이름순(가나다순)으로 정렬하여 반환합니다.
    latest_history = IndustryChart1d.objects.filter(industry=OuterRef("pk")).order_by(
        "-base_date"
    )
    industries = (
        Industry.objects.filter(is_deleted=False)
        .annotate(
            # 최신 index_value 가져오기
            latest_index_value=Subquery(latest_history.values("close")[:1]),
            # 최신 base_date(업데이트 시간 대용) 가져오기
            latest_index_date=Subquery(latest_history.values("base_date")[:1]),
        )
        .filter(
            # 지수 데이터가 존재하는 산업만 필터링
            latest_index_value__isnull=False
        )
        .order_by("name")
    )

    serializer = IndustryIndexSerializer(industries, many=True)
    return Response(
        {
            "status": 200,
            "message": "산업 지수 조회를 성공하였습니다.",
            "data": serializer.data,
        }
    )


# ==================== 차트 데이터 조회 API ====================


class IndustryChartView(APIView):
    """
    산업 지수 차트 통합 조회 API
    """

    @extend_schema(
        tags=["Industry"],
        summary="산업 지수 차트 조회 (통합)",
        description="기간별로 최적화된 차트 데이터를 조회합니다. (1m:일봉, 3m:3일봉, 6m:주봉, 1y:2주봉)",
        parameters=[
            OpenApiParameter(
                name="induty_code",
                type=str,
                location=OpenApiParameter.PATH,
                description="산업 업종코드 (KIS 코드, 예: 0014)",
            ),
            OpenApiParameter(
                name="period",
                type=str,
                location=OpenApiParameter.QUERY,
                description="조회 기간 (1m, 3m, 6m, 1y)",
                default="1m",
                enum=["1m", "3m", "6m", "1y"],
                required=False,
            ),
        ],
        responses={200: IndustryChartSerializer(many=True)},
    )
    def get(self, request, induty_code):
        period = request.query_params.get("period", "1m")

        model_map = {
            "1m": IndustryChart1d,
            "3m": IndustryChart3d,
            "6m": IndustryChart1w,
            "1y": IndustryChart2w,
        }

        target_model = model_map.get(period)
        if not target_model:
            return Response(
                {"status": 400, "message": "유효하지 않은 기간입니다."}, status=400
            )

        try:
            industry = Industry.objects.get(induty_code=induty_code, is_deleted=False)
        except Industry.DoesNotExist:
            return Response(
                {"status": 404, "message": "산업을 찾을 수 없습니다"}, status=404
            )

        # [수정] 차트는 왼쪽(과거)에서 오른쪽(최신)으로 그려지므로 오름차순('base_date') 정렬
        # 최근 1년치 흐름을 보여주기 위해 개수 제한 없이(또는 넉넉히 300개) 가져옵니다.
        charts = target_model.objects.filter(industry=industry).order_by("base_date")

        # 시리얼라이저 적용
        serializer = IndustryChartSerializer(charts, many=True)

        return Response(
            {
                "status": 200,
                "message": f"{industry.name} {period} 차트 데이터 조회 성공",
                "data": serializer.data,
            }
        )


# ================관리자 전용 데이터 적재 API=====================


class IndustryBackfillView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="관리자 전용 산업 지수 데이터 적재 API",
        description="관리자 전용 산업 지수 데이터를 적재합니다.",
        parameters=[
            OpenApiParameter(
                name="induty_code",
                description="특정 산업 업종코드 (KIS 코드, 예: 0014). 비우면 전체 적재",
                required=False,
                type=str,
                location=OpenApiParameter.QUERY,
            )
        ],
        responses={
            202: OpenApiResponse(description="데이터 적재 작업이 시작되었습니다."),
            400: OpenApiResponse(description="잘못된 요청입니다."),
            401: OpenApiResponse(description="관리자 권한이 필요합니다."),
            404: OpenApiResponse(description="산업을 찾을 수 없습니다."),
        },
    )
    def post(self, request):
        # 1. 쿼리 파라미터에서 induty_code 추출 및 검증
        induty_code = request.query_params.get("induty_code")
        industry_id = None

        if induty_code:
            try:
                industry = Industry.objects.get(
                    induty_code=induty_code, is_deleted=False
                )
                industry_id = industry.industry_id
            except Industry.DoesNotExist:
                return Response(
                    {
                        "status": 404,
                        "message": f"업종코드 '{induty_code}'에 해당하는 산업을 찾을 수 없습니다.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 2. 태스크 호출 시 id 전달 (.delay 안에 인자 넣기)
        backfill_industry_charts_task.delay(industry_id=industry_id)

        msg = f"{induty_code} 업종코드 산업" if induty_code else "전체 산업"

        return Response(
            {"message": f"{msg} 데이터 적재 작업이 시작되었습니다."}, status=202
        )


# ------------산업 전망 분석--------------------------
@extend_schema(
    summary="산업 전망 분석",
    description="""
    특정 산업의 뉴스와 관련 기업 보고서를 분석하여 투자 전망을 제공합니다.

    **분석 결과:**
    - 낙관 시나리오: 긍정적 전망 및 성장 동력
    - 중립 시나리오: 현 상황 유지 및 불확실성
    - 비관 시나리오: 부정적 전망 및 하락 리스크

    **캐싱:** 동일 산업 요청 시 1시간 동안 캐시된 결과 반환
    """,
    parameters=[
        OpenApiParameter(
            name="induty_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="산업 업종코드 (KIS 코드, 예: 0014)",
        ),
        OpenApiParameter(
            name="days_back",
            type=int,
            location=OpenApiParameter.QUERY,
            description="검색 기간 (일, 기본값: 30)",
            required=False,
        ),
        OpenApiParameter(
            name="max_news",
            type=int,
            location=OpenApiParameter.QUERY,
            description="최대 뉴스 수 (기본값: 20, 최대: 50)",
            required=False,
        ),
        OpenApiParameter(
            name="max_reports",
            type=int,
            location=OpenApiParameter.QUERY,
            description="최대 보고서 수 (기본값: 10, 최대: 20)",
            required=False,
        ),
        OpenApiParameter(
            name="top_companies",
            type=int,
            location=OpenApiParameter.QUERY,
            description="보고서 수집 대상 상위 기업 수 (기본값: 10, 최대: 20)",
            required=False,
        ),
    ],
    responses={
        200: OpenApiResponse(description="분석 성공"),
        404: OpenApiResponse(description="산업을 찾을 수 없음"),
        503: OpenApiResponse(description="분석 서비스 일시 불가"),
    },
    tags=["Industry - Analysis"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_industry_outlook(request, induty_code):
    """산업 전망 분석 API"""
    from industries.services.outlook import (
        IndustryOutlookService,
        QuotaExceededError,
        LLMServiceError,
    )

    # 산업 조회 (induty_code로 조회)
    try:
        industry = Industry.objects.get(induty_code=induty_code, is_deleted=False)
    except Industry.DoesNotExist:
        return Response(
            {"status": 404, "error": "Industry not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # 파라미터 파싱
    try:
        days_back = min(int(request.query_params.get("days_back", 30)), 90)
        max_news = min(int(request.query_params.get("max_news", 20)), 50)
        max_reports = min(int(request.query_params.get("max_reports", 10)), 20)
        top_companies = min(int(request.query_params.get("top_companies", 10)), 20)
    except (ValueError, TypeError):
        return Response(
            {"status": 400, "error": "파라미터는 정수여야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 분석 수행
    try:
        service = IndustryOutlookService()
        result = service.analyze_outlook(
            industry=industry,
            days_back=days_back,
            max_news=max_news,
            max_reports=max_reports,
            top_companies=top_companies,
        )

        return Response(
            {
                "status": 200,
                "message": "산업 전망 분석 성공",
                "data": result,
            },
            status=status.HTTP_200_OK,
        )

    except QuotaExceededError as e:
        logger.warning(f"산업 전망 분석 쿼터 초과: {induty_code}")
        return Response(
            {
                "status": 429,
                "error": str(e),
                "retry_after": 3600,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    except LLMServiceError as e:
        logger.error(f"산업 전망 분석 LLM 오류: {induty_code}")
        return Response(
            {
                "status": 503,
                "error": str(e),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    except Exception as e:
        logger.exception(f"산업 전망 분석 오류: {induty_code}")
        return Response(
            {
                "status": 500,
                "error": "분석 서비스를 일시적으로 사용할 수 없습니다",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
