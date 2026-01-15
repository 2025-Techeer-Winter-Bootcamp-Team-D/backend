from datetime import datetime, timedelta
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .models import Company, CompanyRanking
from core.models import StockPrice1m, StockPrice15m, StockPrice1h, StockPrice1d
from .serializers import (
    CompanyDetailSerializer,
    CompanyFinancialsSerializer,
    FinancialStatementSerializer,
    RevenueCompositionSerializer,
    ReportListSerializer,
    ReportSerializer,
    CompanyRankingSerializer,
)
from .services.financial import FinancialService
from .services.reports import ReportsService
from .services.company_info import CompanyInfoService
from .services.dart_api import DartAPIError
from .tasks.dart_sync import (
    sync_company_info_from_dart,
    sync_financial_statements,
    sync_company_reports,
)
from .tasks.report_processing import process_company_reports


# ------------------------ 기업 기본 정보 조회--------------------------
@extend_schema(
    summary="기업 기본 정보 조회",
    description="종목코드(PK)를 통해 해당 기업의 정보를 가져옵니다.",
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="조회할 기업의 종목코드 (예: 005930)",
        ),
    ],
    responses={
        200: CompanyDetailSerializer,
        404: OpenApiResponse(description="Not Found"),
    },
    tags=["Company"],
)
@api_view(["GET"])
def get_company_info(request, stock_code):
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)
        serializer = CompanyDetailSerializer(company)
        return Response(
            {
                "status": 200,
                "message": "기업 정보 조회 성공",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@extend_schema(
    summary="기업 재무 지표 조회",
    description="종목코드를 통해 해당 기업의 재무 지표를 조회합니다.",
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="조회할 기업의 종목코드 (예: 005930)",
        ),
        OpenApiParameter(
            name="year",
            type=int,
            location=OpenApiParameter.QUERY,
            description="조회할 연도 (기본값: 최근 3년)",
            required=False,
        ),
    ],
    responses={
        200: CompanyFinancialsSerializer,
        404: OpenApiResponse(description="Not Found"),
    },
    tags=["Company"],
)
@api_view(["GET"])
def get_company_financials(request, stock_code):
    """기업 재무 지표 조회 API"""
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        # FinancialService를 사용하여 재무제표 조회
        financial_service = FinancialService()

        # 연도 파라미터 처리
        year_param = request.query_params.get("year")
        years = None
        if year_param:
            try:
                years = [int(year_param)]
            except ValueError:
                return Response(
                    {"status": 400, "error": "year 파라미터는 정수여야 합니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 재무제표 조회 (최근 3년 또는 지정 연도)
        financial_statements = financial_service.get_financial_statements(
            company, years
        )

        # 매출 구성 조회 (최신 연도)
        latest_year = (
            financial_statements[0].fiscal_year if financial_statements else None
        )
        revenue_composition = (
            financial_service.get_revenue_composition(company, latest_year)
            if latest_year
            else []
        )

        # Serializer로 변환
        financial_statements_data = FinancialStatementSerializer(
            financial_statements, many=True
        ).data
        revenue_composition_data = RevenueCompositionSerializer(
            revenue_composition, many=True
        ).data

        data = {
            "stock_code": company.stock_code,
            "company_name": company.company_name,
            "market_amount": company.market_amount,
            "financial_statements": financial_statements_data,
            "revenue_composition": revenue_composition_data,
        }

        return Response(
            {
                "status": 200,
                "message": "재무 지표 조회 성공",
                "data": data,
            },
            status=status.HTTP_200_OK,
        )

    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@extend_schema(
    summary="기업 보고서 목록 조회",
    description="종목코드를 통해 해당 기업의 공시 보고서 목록을 조회합니다.",
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="조회할 기업의 종목코드 (예: 005930)",
        ),
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            description="페이지 번호 (기본값: 1)",
            required=False,
        ),
        OpenApiParameter(
            name="size",
            type=int,
            location=OpenApiParameter.QUERY,
            description="페이지 크기 (기본값: 20, 최대: 100)",
            required=False,
        ),
    ],
    responses={
        200: ReportListSerializer,
        404: OpenApiResponse(description="Not Found"),
    },
    tags=["Company"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_company_reports(request, stock_code):
    """기업 보고서 목록 조회 API"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"보고서 조회 API 호출: stock_code={stock_code}")
        company = Company.objects.get(pk=stock_code, is_deleted=False)
        logger.info(f"Company 조회 성공: {company.stock_code}, {company.company_name}")

        # ReportsService를 사용하여 보고서 조회
        reports_service = ReportsService()

        # 쿼리 파라미터 처리
        report_type = request.query_params.get("type")
        try:
            page = int(request.query_params.get("page", 1))
            size = min(int(request.query_params.get("size", 20)), 100)
        except ValueError:
            return Response(
                {"status": 400, "error": "Invalid page or size parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info(
            f"쿼리 파라미터: report_type={report_type}, page={page}, size={size}"
        )

        # 보고서 조회
        result = reports_service.get_reports(company, report_type, page, size)
        logger.info(
            f"ReportsService 결과: total_count={result['total_count']}, reports 개수={len(result['reports'])}"
        )

        # Serializer로 변환
        reports_data = ReportSerializer(result["reports"], many=True).data
        logger.info(f"Serializer 변환 완료: {len(reports_data)}개")

        data = {
            "total_count": result["total_count"],
            "page": result["page"],
            "page_size": result["page_size"],
            "reports": reports_data,
        }

        return Response(
            {
                "status": 200,
                "message": "보고서 목록 조회 성공",
                "data": data,
            },
            status=status.HTTP_200_OK,
        )

    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@extend_schema(
    summary="DART 데이터 동기화 (관리자용)",
    description="DART API에서 기업 정보, 재무제표, 보고서를 DB에 동기화합니다. 인증이 필요합니다.",
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="동기화할 기업의 종목코드 (예: 005930)",
        ),
        OpenApiParameter(
            name="sync_info",
            type=bool,
            location=OpenApiParameter.QUERY,
            description="기업 기본 정보 동기화 여부 (기본값: true)",
            required=False,
        ),
        OpenApiParameter(
            name="sync_financials",
            type=bool,
            location=OpenApiParameter.QUERY,
            description="재무제표 동기화 여부 (기본값: false)",
            required=False,
        ),
        OpenApiParameter(
            name="sync_reports",
            type=bool,
            location=OpenApiParameter.QUERY,
            description="보고서 목록 동기화 여부 (기본값: false)",
            required=False,
        ),
        OpenApiParameter(
            name="year",
            type=int,
            location=OpenApiParameter.QUERY,
            description="재무제표 동기화 시 조회할 연도 (기본값: 현재 연도)",
            required=False,
        ),
        OpenApiParameter(
            name="days",
            type=int,
            location=OpenApiParameter.QUERY,
            description="보고서 동기화 시 조회할 기간 (일 단위, 기본값: 365)",
            required=False,
        ),
        OpenApiParameter(
            name="async",
            type=bool,
            location=OpenApiParameter.QUERY,
            description="비동기 실행 여부 (Celery 작업으로 실행, 기본값: false)",
            required=False,
        ),
    ],
    responses={
        200: OpenApiResponse(description="동기화 성공"),
        400: OpenApiResponse(description="Bad Request"),
        401: OpenApiResponse(description="Unauthorized"),
        404: OpenApiResponse(description="Company not found"),
    },
    tags=["Company"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_company_from_dart(request, stock_code):
    """
    DART 데이터 동기화 API (관리자용)
    """
    try:
        try:
            company = Company.objects.get(pk=stock_code, is_deleted=False)
        except Company.DoesNotExist:
            return Response(
                {
                    "status": 404,
                    "error": f"Company with stock_code '{stock_code}' not found in database.",
                    "message": "동기화하려면 먼저 기업 데이터를 생성해야 합니다. 종목코드로 기업을 생성하거나, DART 고유번호(corp_code)를 설정해야 합니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not company.corp_code:
            return Response(
                {
                    "status": 400,
                    "error": f"Company {stock_code}에 corp_code가 설정되지 않았습니다.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 쿼리 파라미터 처리
        sync_info = request.query_params.get("sync_info", "true").lower() == "true"
        sync_financials = (
            request.query_params.get("sync_financials", "false").lower() == "true"
        )
        sync_reports = (
            request.query_params.get("sync_reports", "false").lower() == "true"
        )
        use_async = request.query_params.get("async", "false").lower() == "true"

        # 최소 하나는 동기화해야 함
        if not (sync_info or sync_financials or sync_reports):
            return Response(
                {
                    "status": 400,
                    "error": "최소 하나의 동기화 옵션을 선택해야 합니다.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = {}
        errors = []

        # 파라미터 사전 파싱
        try:
            year = int(request.query_params.get("year", datetime.now().year))
            days = int(request.query_params.get("days", 365))
        except ValueError:
            return Response(
                {"status": 400, "error": "year와 days는 정수여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 비동기 실행
        if use_async:
            if sync_info:
                sync_company_info_from_dart.delay(stock_code)
                results["info"] = "동기화 작업이 큐에 등록되었습니다."
            if sync_financials:
                sync_financial_statements.delay(stock_code, year)
                results["financials"] = (
                    f"{year}년 재무제표 동기화 작업이 큐에 등록되었습니다."
                )
            if sync_reports:
                sync_company_reports.delay(stock_code, days)
                results["reports"] = (
                    f"최근 {days}일 보고서 동기화 작업이 큐에 등록되었습니다."
                )

            return Response(
                {
                    "status": 200,
                    "message": "동기화 작업이 비동기로 등록되었습니다.",
                    "data": {
                        "stock_code": stock_code,
                        "sync_info": sync_info,
                        "sync_financials": sync_financials,
                        "sync_reports": sync_reports,
                        "results": results,
                    },
                },
                status=status.HTTP_200_OK,
            )

        # 동기 실행
        if sync_info:
            try:
                service = CompanyInfoService()
                service.sync_company_info(company)
                results["info"] = "기업 정보 동기화 완료"
            except Exception as e:
                error_msg = f"기업 정보 동기화 실패: {str(e)}"
                errors.append(error_msg)
                results["info"] = error_msg

        if sync_financials:
            try:
                year = int(request.query_params.get("year", datetime.now().year))
                sync_all = (
                    request.query_params.get("sync_all_reports", "false").lower()
                    == "true"
                )
                service = FinancialService()
                statements = service.sync_financial_statements(
                    company, year, sync_all_reports=sync_all
                )
                results["financials"] = (
                    f"{year}년 재무제표 동기화 완료 ({len(statements)}개 보고서)"
                )
            except Exception as e:
                error_msg = f"재무제표 동기화 실패: {str(e)}"
                errors.append(error_msg)
                results["financials"] = error_msg

        if sync_reports:
            try:
                days = int(request.query_params.get("days", 365))
                incremental = (
                    request.query_params.get("incremental", "true").lower() == "true"
                )
                service = ReportsService()
                # 증분 동기화 + 주요 공시만 (정기공시 + 주요사항보고)
                reports = service.sync_reports(
                    company, days=days, incremental=incremental, report_types=["A", "B"]
                )
                results["reports"] = (
                    f"보고서 {len(reports)}건 동기화 완료 (증분: {incremental})"
                )
            except Exception as e:
                error_msg = f"보고서 동기화 실패: {str(e)}"
                errors.append(error_msg)
                results["reports"] = error_msg

        # 응답 생성
        response_data = {
            "status": 200 if not errors else 207,  # 207: Multi-Status
            "message": ("동기화 완료" if not errors else "일부 동기화 실패"),
            "data": {
                "stock_code": stock_code,
                "sync_info": sync_info,
                "sync_financials": sync_financials,
                "sync_reports": sync_reports,
                "results": results,
            },
        }

        if errors:
            response_data["errors"] = errors

        return Response(
            response_data,
            status=status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS,
        )

    except ValueError as e:
        return Response(
            {"status": 400, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        return Response(
            {"status": 500, "error": f"동기화 중 오류 발생: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------ 기업 순위----------------------------------
@extend_schema(
    summary="전체 기업 순위 조회",
    description="최신 기준 날짜의 기업 순위 리스트를 가져옵니다.",
    responses={
        200: CompanyRankingSerializer(many=True),
        404: OpenApiResponse(description="company_rankings Not Found"),
    },
    tags=["Ranking"],
)
@api_view(["GET"])
def get_company_rankings(request):
    # 가장 최신 기준 날짜 조회
    latest_date = (
        CompanyRanking.objects.filter(is_deleted=False)
        .order_by("-base_date")
        .values_list("base_date", flat=True)
        .first()
    )
    if not latest_date:
        return Response(
            {"status": 404, "message": "company_rankings not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    # 데이터 조회
    rankings = (
        CompanyRanking.objects.filter(base_date=latest_date, is_deleted=False)
        .select_related("stock_code")
        .order_by("rank")
    )
    # 데이터 직렬화
    serializer = CompanyRankingSerializer(rankings, many=True)
    # 명세서 규격에 맞춘 최종 응답 반환
    return Response(
        {
            "status": 200,
            "message": "전체 기업 순위 조회를 성공하였습니다.",
            "data": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


# ------------------------ 보고서 처리 ----------------------------------
@extend_schema(
    summary="보고서 처리 시작 (관리자용)",
    description="기업의 미처리 보고서를 일괄 처리합니다 (본문 추출, 정제, 구조화된 정보 추출, OpenSearch 적재).",
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="처리할 기업의 종목코드 (예: 005930)",
        ),
        OpenApiParameter(
            name="limit",
            type=int,
            location=OpenApiParameter.QUERY,
            description="처리할 보고서 수 (기본값: 20, 최대: 100)",
            required=False,
        ),
    ],
    responses={
        202: OpenApiResponse(description="처리 시작됨"),
        404: OpenApiResponse(description="Company not found"),
    },
    tags=["Reports"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def process_company_reports_view(request, stock_code):
    """보고서 처리 API (관리자용)"""
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        # limit 파라미터 처리
        try:
            limit = int(request.query_params.get("limit", 20))
            if limit <= 0:
                return Response(
                    {
                        "status": 400,
                        "error": "limit 파라미터는 1 이상의 정수여야 합니다.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            limit = min(limit, 100)
        except ValueError:
            return Response(
                {"status": 400, "error": "limit 파라미터는 정수여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 미처리 보고서 수 확인
        from .models import Report

        pending_count = Report.objects.filter(
            company_id=stock_code,
            processing_status="pending",
        ).count()

        if pending_count == 0:
            return Response(
                {
                    "status": 200,
                    "message": "처리할 보고서가 없습니다.",
                    "data": {
                        "stock_code": stock_code,
                        "pending_count": 0,
                    },
                },
                status=status.HTTP_200_OK,
            )

        # Celery 태스크 실행
        task = process_company_reports.delay(stock_code, limit)

        return Response(
            {
                "status": 202,
                "message": "보고서 처리가 시작되었습니다.",
                "data": {
                    "stock_code": stock_code,
                    "company_name": company.company_name,
                    "task_id": task.id,
                    "limit": limit,
                    "pending_count": pending_count,
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )
    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


# ------------------------ 기업 주가 데이터 조회--------------------------
@extend_schema(
    summary="기업 주가 데이터 조회",
    description="""
    특정 종목의 OHLCV 주가 데이터를 조회합니다.
    
    **지원하는 시간 단위 및 조회 기간:**
    - `1m`: 1분봉 - 최근 1일치 데이터
    - `15m`: 15분봉 - 최근 5일치(일주일) 데이터
    - `1h`: 1시간봉 - 최근 1달치 데이터
    - `1d`: 1일봉 - 최근 1년치 데이터
    
    **쿼리 파라미터:**
    - `interval`: 조회할 시간 단위 (1m, 15m, 1h, 1d). 없으면 모든 interval 반환
    
    **참고:**
    - DB에 저장된 모든 데이터를 최신순으로 반환합니다.
    """,
    parameters=[
        OpenApiParameter(
            name="stock_code",
            type=str,
            location=OpenApiParameter.PATH,
            description="종목코드 (6자리, 예: 005930)",
        ),
        OpenApiParameter(
            name="interval",
            type=str,
            location=OpenApiParameter.QUERY,
            description="시간 단위 (1m, 15m, 1h, 1d). 없으면 모든 interval 반환",
            required=False,
        ),
    ],
    responses={
        200: OpenApiResponse(description="주가 데이터 조회 성공"),
        400: OpenApiResponse(description="잘못된 요청"),
        404: OpenApiResponse(description="종목을 찾을 수 없음"),
    },
    tags=["Company"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def get_company_prices(request, stock_code: str):
    """
    기업 주가 데이터 조회 API

    특정 종목의 OHLCV 데이터를 조회합니다.
    DB에 저장된 모든 데이터를 최신순으로 반환합니다.
    """
    # 종목 존재 확인
    try:
        company = Company.objects.get(stock_code=stock_code, is_deleted=False)
    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": f"종목 {stock_code}을(를) 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # 쿼리 파라미터 파싱
    interval = request.query_params.get("interval", None)

    # interval 유효성 검사
    valid_intervals = ["1m", "15m", "1h", "1d"]
    if interval and interval not in valid_intervals:
        return Response(
            {
                "status": 400,
                "error": f"Invalid interval: {interval}",
                "valid_intervals": valid_intervals,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 조회할 interval 목록 결정
    intervals_to_query = [interval] if interval else valid_intervals

    # 모델 매핑
    model_map = {
        "1m": StockPrice1m,
        "15m": StockPrice15m,
        "1h": StockPrice1h,
        "1d": StockPrice1d,
    }

    # 결과 저장
    results = {}

    for interval_key in intervals_to_query:
        model = model_map[interval_key]

        # values()를 사용하여 필요한 필드만 선택 (id 필드 제외)
        queryset = (
            model.objects.filter(stock_code=stock_code)
            .values(
                "bucket",
                "stock_code",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "trade_count",
                "source",
            )
            .order_by("-bucket")
        )

        # 데이터 변환
        data = []
        for item in queryset:
            data.append(
                {
                    "bucket": item["bucket"],
                    "stock_code": item["stock_code"],
                    "open": float(item["open"]) if item["open"] else None,
                    "high": float(item["high"]) if item["high"] else None,
                    "low": float(item["low"]) if item["low"] else None,
                    "close": float(item["close"]) if item["close"] else None,
                    "volume": int(item["volume"]) if item["volume"] else 0,
                    "amount": float(item["amount"]) if item["amount"] else None,
                    "trade_count": (
                        int(item["trade_count"]) if item["trade_count"] else None
                    ),
                    "source": item["source"],
                }
            )

        # 전체 개수
        total_count = len(data)

        results[interval_key] = {
            "stock_code": stock_code,
            "interval": interval_key,
            "total_count": total_count,
            "data": data,
        }

    # 응답 생성
    if interval:
        # 단일 interval 응답
        return Response(
            {
                "status": 200,
                "message": "주가 데이터 조회 성공",
                "data": results[interval],
            },
            status=status.HTTP_200_OK,
        )
    else:
        # 모든 interval 응답
        return Response(
            {
                "status": 200,
                "message": "주가 데이터 조회 성공",
                "data": results,
            },
            status=status.HTTP_200_OK,
        )
