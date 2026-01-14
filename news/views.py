from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiParameter,
)
from django.core.paginator import Paginator

from .models import News
from .serializers import NewsSerializer, NewsDetailSerializer


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
    # 쿼리 파라미터 파싱
    page = int(request.query_params.get("page", 1))
    page_size = min(int(request.query_params.get("page_size", 20)), 100)

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
