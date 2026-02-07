# utils/responses.py
"""
API 응답 표준화 유틸리티
"""

from typing import Any, Optional, Dict
from rest_framework.response import Response
from rest_framework import status


def success_response(
    data: Any = None,
    message: str = "성공",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    """
    성공 응답 생성

    Args:
        data: 응답 데이터
        message: 응답 메시지
        status_code: HTTP 상태 코드

    Returns:
        Response 객체
    """
    return Response(
        {
            "status": status_code,
            "message": message,
            "data": data,
        },
        status=status_code,
    )


def error_response(
    message: str = "오류가 발생했습니다",
    status_code: int = status.HTTP_400_BAD_REQUEST,
    errors: Optional[Dict[str, Any]] = None,
) -> Response:
    """
    오류 응답 생성

    Args:
        message: 오류 메시지
        status_code: HTTP 상태 코드
        errors: 상세 오류 정보

    Returns:
        Response 객체
    """
    response_data = {
        "status": status_code,
        "error": message,
    }
    if errors:
        response_data["details"] = errors

    return Response(response_data, status=status_code)


def paginated_response(
    data: Dict[str, Any],
    message: str = "조회 성공",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    """
    페이지네이션된 응답 생성

    Args:
        data: paginate_queryset의 결과
        message: 응답 메시지
        status_code: HTTP 상태 코드

    Returns:
        Response 객체
    """
    return Response(
        {
            "status": status_code,
            "message": message,
            **data,
        },
        status=status_code,
    )
