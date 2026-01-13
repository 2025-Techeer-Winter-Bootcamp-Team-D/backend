from datetime import datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from .models import Company
from .serializers import (
    CompanySerializer,
    CompanyDetailSerializer,
    CompanyFinancialsSerializer,
    FinancialStatementSerializer,
    RevenueCompositionSerializer,
    ReportListSerializer,
    ReportSerializer,
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
                pass

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
            name="type",
            type=str,
            location=OpenApiParameter.QUERY,
            description="공시유형 (A: 정기공시, B: 주요사항보고 등)",
            required=False,
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
        page = int(request.query_params.get("page", 1))
        size = min(int(request.query_params.get("size", 20)), 100)
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

        # 비동기 실행
        if use_async:
            if sync_info:
                sync_company_info_from_dart.delay(stock_code)
                results["info"] = "동기화 작업이 큐에 등록되었습니다."
            if sync_financials:
                year = int(request.query_params.get("year", datetime.now().year))
                sync_financial_statements.delay(stock_code, year)
                results["financials"] = (
                    f"{year}년 재무제표 동기화 작업이 큐에 등록되었습니다."
                )
            if sync_reports:
                days = int(request.query_params.get("days", 365))
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

    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"},
            status=status.HTTP_404_NOT_FOUND,
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
