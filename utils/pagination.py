# utils/pagination.py
"""
공통 페이지네이션 유틸리티
"""

from typing import Tuple, Optional, Dict, Any, Type
from django.core.paginator import Paginator
from rest_framework.request import Request
from rest_framework.serializers import Serializer


def paginate_queryset(
    request: Request,
    queryset,
    serializer_class: Type[Serializer],
    default_page_size: int = 20,
    max_page_size: int = 100,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """
    공통 페이지네이션 처리

    Args:
        request: DRF Request 객체
        queryset: 페이지네이션할 QuerySet
        serializer_class: 직렬화에 사용할 Serializer 클래스
        default_page_size: 기본 페이지 크기
        max_page_size: 최대 페이지 크기

    Returns:
        (result_data, error): 성공 시 (데이터, None), 실패 시 (None, 에러)
    """
    # 파라미터 파싱
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", default_page_size))
    except (ValueError, TypeError):
        return None, {"error": "page와 page_size는 정수여야 합니다."}

    # 유효성 검사
    if page < 1:
        return None, {"error": "page는 1 이상이어야 합니다."}

    if page_size < 1:
        return None, {"error": "page_size는 1 이상이어야 합니다."}

    # 페이지 크기 제한
    page_size = min(page_size, max_page_size)

    # 페이지네이션 수행
    paginator = Paginator(queryset, page_size)

    # 페이지 범위 확인
    if page > paginator.num_pages and paginator.num_pages > 0:
        return None, {"error": f"page는 {paginator.num_pages} 이하여야 합니다."}

    page_obj = paginator.get_page(page)

    # 결과 구성
    return {
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page,
        "page_size": page_size,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "results": serializer_class(page_obj, many=True).data,
    }, None
