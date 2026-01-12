from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.db import connection
from django.core.cache import cache


@extend_schema(
    summary="헬스 체크",
    description="서버 상태 및 연결된 서비스(DB, Redis)의 상태를 확인합니다.",
    responses={
        200: OpenApiResponse(
            description="모든 서비스가 정상 작동 중",
            response={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "healthy"},
                    "database": {"type": "string", "example": "connected"},
                    "cache": {"type": "string", "example": "connected"},
                },
            },
        ),
        503: OpenApiResponse(
            description="일부 서비스가 비정상 상태",
            response={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "unhealthy"},
                    "database": {"type": "string", "example": "disconnected"},
                    "cache": {"type": "string", "example": "disconnected"},
                    "error": {"type": "string", "example": "Database connection failed"},
                },
            },
        ),
    },
    tags=["Health Check"],
)
@api_view(["GET"])
def health_check(request):
    """
    헬스 체크 엔드포인트

    서버와 연결된 서비스들의 상태를 확인합니다:
    - Database (PostgreSQL/TimescaleDB)
    - Cache (Redis)
    """
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "cache": "unknown",
    }

    is_healthy = True

    # 데이터베이스 연결 확인
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = "disconnected"
        health_status["error"] = f"Database error: {str(e)}"
        is_healthy = False

    # Redis 캐시 연결 확인
    try:
        cache.set("health_check", "ok", 10)
        result = cache.get("health_check")
        if result == "ok":
            health_status["cache"] = "connected"
        else:
            health_status["cache"] = "disconnected"
            is_healthy = False
    except Exception as e:
        health_status["cache"] = "disconnected"
        health_status["error"] = health_status.get("error", "") + f" Cache error: {str(e)}"
        is_healthy = False

    if is_healthy:
        return Response(health_status, status=status.HTTP_200_OK)
    else:
        health_status["status"] = "unhealthy"
        return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)
