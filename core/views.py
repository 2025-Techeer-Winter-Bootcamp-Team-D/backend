from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
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
                    "error": {
                        "type": "string",
                        "example": "Database connection failed",
                    },
                },
            },
        ),
    },
    tags=["System"],
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
        health_status["error"] = (
            health_status.get("error", "") + f" Cache error: {str(e)}"
        )
        is_healthy = False

    if is_healthy:
        return Response(health_status, status=status.HTTP_200_OK)
    else:
        health_status["status"] = "unhealthy"
        return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# =============================================================================
# 주가 데이터 동기화 API (관리자용)
# =============================================================================


@extend_schema(
    summary="주가 히스토리 동기화 (관리자용)",
    description="""
    yfinance API를 통해 특정 종목의 과거 OHLCV 데이터를 동기화합니다.
    
    **수집 범위:**
    - 1분봉: 최근 1일
    - 15분봉: 최근 5일
    - 1시간봉: 최근 1달
    - 1일봉: 최근 1년
    
    **참고:**
    - 시장 정보(KOSPI/KOSDAQ)는 Company 테이블의 market 필드에서 자동으로 조회됩니다.
    - KOSPI 종목은 `.KS`, KOSDAQ 종목은 `.KQ` suffix가 자동 추가됩니다.
    - `async=true`(기본값)일 경우 Celery 태스크로 비동기 실행됩니다.
    """,
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="종목코드 (6자리, 예: 005930)",
        ),
        OpenApiParameter(
            name="intervals",
            type=str,
            location=OpenApiParameter.QUERY,
            description="동기화할 시간 단위 (콤마 구분: 1m,15m,1h,1d). 기본값: 전체",
            required=False,
        ),
        OpenApiParameter(
            name="async",
            type=bool,
            location=OpenApiParameter.QUERY,
            description="비동기 실행 여부. 기본값: true",
            required=False,
        ),
    ],
    responses={
        200: OpenApiResponse(description="동기화 완료 (동기 실행)"),
        202: OpenApiResponse(description="동기화 작업 시작됨 (비동기 실행)"),
        400: OpenApiResponse(description="잘못된 요청"),
        401: OpenApiResponse(description="인증 필요"),
        403: OpenApiResponse(description="권한 없음"),
        404: OpenApiResponse(description="종목을 찾을 수 없음"),
    },
    tags=["Admin"],
)
@api_view(["POST"])
@permission_classes([IsAdminUser])
def sync_stock_history(request, stock_code: str):
    """
    단일 종목 주가 히스토리 동기화 API
    """
    # 파라미터 파싱
    intervals_param = request.query_params.get("intervals", None)
    if intervals_param:
        intervals = [i.strip() for i in intervals_param.split(",")]
    else:
        intervals = None  # 전체

    use_async = request.query_params.get("async", "true").lower() == "true"

    # 유효성 검사
    valid_intervals = ["1m", "15m", "1h", "1d"]
    if intervals:
        for interval in intervals:
            if interval not in valid_intervals:
                return Response(
                    {
                        "error": f"Invalid interval: {interval}",
                        "valid_intervals": valid_intervals,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

    # 종목 존재 및 market 정보 확인
    from companies.models import Company

    try:
        company = Company.objects.get(stock_code=stock_code)
        if not company.market:
            return Response(
                {
                    "error": f"종목 {stock_code}의 시장 정보(market)가 없습니다.",
                    "hint": "먼저 DART API를 통해 기업 정보를 동기화하세요.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    except Company.DoesNotExist:
        return Response(
            {"error": f"종목 {stock_code}을(를) 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if use_async:
        # Celery 태스크로 비동기 실행
        from core.tasks.yfinance_sync import sync_stock_history_task

        task = sync_stock_history_task.delay(
            stock_code=stock_code,
            intervals=intervals,
        )
        return Response(
            {
                "status": "accepted",
                "message": "동기화 작업이 시작되었습니다.",
                "data": {
                    "task_id": task.id,
                    "stock_code": stock_code,
                    "market": company.market,
                    "intervals": intervals or valid_intervals,
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )
    else:
        # 동기 실행
        from core.services.yfinance_service import YFinanceService

        service = YFinanceService(delay_between_requests=0.5)
        results = service.sync_stock_history(stock_code, intervals, None)

        return Response(
            {
                "status": "completed",
                "message": "동기화가 완료되었습니다.",
                "data": {
                    "stock_code": stock_code,
                    "market": company.market,
                    "results": results,
                },
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="여러 종목 주가 히스토리 동기화 (관리자용)",
    description="""
    yfinance API를 통해 여러 종목의 과거 OHLCV 데이터를 동기화합니다.
    
    **참고:** 시장 정보는 각 종목의 Company.market 필드에서 자동으로 조회됩니다.
    
    **요청 본문:**
    ```json
    {
        "stock_codes": ["005930", "000660", "035720"],
        "intervals": ["1d"]
    }
    ```
    
    **참고:** yfinance 데이터는 실시간 스트리밍에서 빠질 수 있는 정보를 보완하기 위해 항상 기존 데이터를 덮어씁니다.
    """,
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "stock_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "종목코드 목록",
                },
                "intervals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "시간 단위 목록",
                },
            },
            "required": ["stock_codes"],
        }
    },
    responses={
        202: OpenApiResponse(description="동기화 작업 시작됨"),
        400: OpenApiResponse(description="잘못된 요청"),
        401: OpenApiResponse(description="인증 필요"),
    },
    tags=["Admin"],
)
@api_view(["POST"])
@permission_classes([IsAdminUser])
def sync_multiple_stocks_history(request):
    """
    여러 종목 주가 히스토리 동기화 API
    """
    stock_codes = request.data.get("stock_codes", [])
    intervals = request.data.get("intervals", None)

    if not stock_codes:
        return Response(
            {"error": "stock_codes is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(stock_codes) > 100:
        return Response(
            {"error": "Maximum 100 stocks per request"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid_intervals = ["1m", "15m", "1h", "1d"]
    if intervals is not None:
        if not isinstance(intervals, list):
            return Response(
                {
                    "error": "intervals must be a list",
                    "valid_intervals": valid_intervals,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(intervals) == 0:
            intervals = None
        else:
            invalid_intervals = [
                interval for interval in intervals if interval not in valid_intervals
            ]
            if invalid_intervals:
                return Response(
                    {
                        "error": f"Invalid interval: {invalid_intervals[0]}",
                        "invalid_intervals": invalid_intervals,
                        "valid_intervals": valid_intervals,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

    # 각 종목별로 개별 태스크 실행 (병렬 처리)
    # 시장 정보는 Company.market에서 자동으로 조회됩니다
    from core.tasks.yfinance_sync import sync_stock_history_task

    task_ids = []
    for stock_code in stock_codes:
        task = sync_stock_history_task.delay(
            stock_code=stock_code,
            intervals=intervals,
        )
        task_ids.append({"stock_code": stock_code, "task_id": task.id})

    return Response(
        {
            "status": "accepted",
            "message": f"{len(stock_codes)}개 종목의 동기화 작업이 시작되었습니다.",
            "data": {
                "total_stocks": len(stock_codes),
                "intervals": intervals or ["1m", "15m", "1h", "1d"],
                "tasks": task_ids,
            },
        },
        status=status.HTTP_202_ACCEPTED,
    )


@extend_schema(
    summary="Continuous Aggregate 수동 동기화 (관리자용)",
    description="""
    Continuous Aggregate 데이터를 통합 테이블로 즉시 동기화합니다.
    일반적으로 Celery Beat이 자동으로 실행하지만, 수동으로 실행할 때 사용합니다.
    """,
    responses={
        200: OpenApiResponse(description="동기화 완료"),
        401: OpenApiResponse(description="인증 필요"),
    },
    tags=["Admin"],
)
@api_view(["POST"])
@permission_classes([IsAdminUser])
def sync_realtime_prices(request):
    """
    Continuous Aggregate → 통합 테이블 수동 동기화 API
    """
    from core.tasks.price_sync import sync_all_prices

    result = sync_all_prices.apply().get()

    return Response(
        {
            "status": "completed",
            "message": "실시간 데이터 동기화가 완료되었습니다.",
            "data": result,
        },
        status=status.HTTP_200_OK,
    )
