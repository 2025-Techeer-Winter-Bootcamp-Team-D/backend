from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiParameter,
    inline_serializer,
)
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta

from .models import News
from .serializers import NewsSerializer, NewsDetailSerializer
from .services.opensearch import OpenSearchService


@extend_schema(
    summary="뉴스 목록 조회",
    description="저장된 뉴스 목록을 조회합니다. 페이지네이션을 지원합니다.",
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
            description="페이지당 항목 수 (기본값: 20, 최대: 100)",
            required=False,
        ),
    ],
    responses={
        200: NewsSerializer(many=True),
    },
    tags=["News"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def news_list(request):
    """
    뉴스 목록 조회 API

    Query Parameters:
    - page: 페이지 번호 (기본값: 1)
    - page_size: 페이지당 항목 수 (기본값: 20, 최대: 100)
    """
    # 쿼리 파라미터 파싱 및 검증
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
    except (ValueError, TypeError):
        return Response(
            {"error": "page와 page_size는 정수여야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    # 유효 범위 검증
    if page < 1:
        return Response(
            {"error": "page는 1 이상이어야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if page_size < 1 or page_size > 100:
        return Response(
            {"error": "page_size는 1에서 100 사이여야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    
    # page_size 상한 적용
    page_size = min(page_size, 100)

    # 기본 쿼리셋: 삭제되지 않은 뉴스만 조회
    queryset = News.objects.filter(is_deleted=False)

    # 페이지네이션
    paginator = Paginator(queryset, page_size)
    total_count = paginator.count
    total_pages = paginator.num_pages

    try:
        news_page = paginator.page(page)
    except Exception:
        return Response(
            {"error": "Invalid page number"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Serializer로 변환
    serializer = NewsSerializer(news_page.object_list, many=True)

    return Response(
        {
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": page_size,
            "results": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    summary="뉴스 상세 조회",
    description="특정 뉴스의 상세 정보를 조회합니다.",
    parameters=[
        OpenApiParameter(
            name="news_id",
            type=int,
            location=OpenApiParameter.PATH,
            description="조회할 뉴스 ID",
        ),
    ],
    responses={
        200: NewsDetailSerializer,
        404: OpenApiResponse(description="Not Found"),
    },
    tags=["News"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def news_detail(request, news_id):
    """
    뉴스 상세 조회 API

    Path Parameters:
    - news_id: 조회할 뉴스 ID
    """
    try:
        news = News.objects.get(news_id=news_id, is_deleted=False)
    except News.DoesNotExist:
        return Response(
            {"error": "News not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = NewsDetailSerializer(news)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    summary="뉴스 키워드 빈도수 조회",
    description="최근 뉴스에서 자주 등장하는 키워드 빈도수를 조회합니다. "
    "OpenSearch의 키워드 집계 기능을 사용합니다.",
    parameters=[
        OpenApiParameter(
            name="size",
            type=int,
            location=OpenApiParameter.QUERY,
            description="반환할 상위 키워드 개수 (기본값: 15, 최대: 50)",
            required=False,
        ),
        OpenApiParameter(
            name="days",
            type=int,
            location=OpenApiParameter.QUERY,
            description="분석할 기간 (일 단위, 기본값: 7)",
            required=False,
        ),
        OpenApiParameter(
            name="min_doc_count",
            type=int,
            location=OpenApiParameter.QUERY,
            description="최소 문서 등장 수 (기본값: 2)",
            required=False,
        ),
        OpenApiParameter(
            name="exclude",
            type=str,
            location=OpenApiParameter.QUERY,
            description="제외할 키워드 (쉼표로 구분, 예: 주식,투자,시장)",
            required=False,
        ),
    ],
    responses={
        200: inline_serializer(
            name="KeywordFrequencyResponse",
            fields={
                "status": serializers.IntegerField(),
                "message": serializers.CharField(default="키워드 빈도수 조회를 성공하였습니다."),
                "data": inline_serializer(
                    name="KeywordFrequencyData",
                    fields={
                        "period_days": serializers.IntegerField(),
                        "total_keywords": serializers.IntegerField(),
                        "keywords": serializers.ListField(
                            child=inline_serializer(
                                name="KeywordItem",
                                fields={
                                    "keyword": serializers.CharField(),
                                    "count": serializers.IntegerField(),
                                    "doc_count": serializers.IntegerField(),
                                },
                            )
                        ),
                    },
                ),
            },
        ),
        500: OpenApiResponse(description="OpenSearch 오류"),
    },
    tags=["News"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_news_keywords(request):
    """
    뉴스 키워드 빈도수 조회 API

    OpenSearch에서 최근 뉴스 본문의 키워드 빈도수를 집계하여 반환합니다.

    Query Parameters:
    - size: 반환할 상위 키워드 개수 (기본값: 15, 최대: 50)
    - days: 분석할 기간 (일 단위, 기본값: 7)
    - min_doc_count: 최소 문서 등장 수 (기본값: 2)
    - exclude: 제외할 키워드 (쉼표로 구분)
    """
    # 쿼리 파라미터 파싱
    try:
        size = int(request.query_params.get("size", 15))
        days = int(request.query_params.get("days", 7))
        min_doc_count = int(request.query_params.get("min_doc_count", 2))
    except (ValueError, TypeError):
        return Response(
            {"status": 400, "error": "size, days, min_doc_count는 정수여야 합니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 유효 범위 검증
    size = max(1, min(size, 50))
    days = max(1, min(days, 365))
    min_doc_count = max(1, min_doc_count)

    # 제외 키워드 파싱
    exclude_param = request.query_params.get("exclude", "")
    exclude_keywords = None
    if exclude_param:
        exclude_keywords = [k.strip() for k in exclude_param.split(",") if k.strip()]

    # 기간 계산
    published_after = timezone.now() - timedelta(days=days)

    try:
        opensearch = OpenSearchService()
        keywords = opensearch.get_top_keywords(
            size=size,
            published_after=published_after,
            exclude_keywords=exclude_keywords,
            min_doc_count=min_doc_count,
        )

        return Response(
            {
                "status": 200,
                "message": "키워드 빈도수 조회를 성공하였습니다.",
                "data": {
                    "period_days": days,
                    "total_keywords": len(keywords),
                    "keywords": keywords,
                },
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {
                "status": 500,
                "error": f"OpenSearch 오류: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
