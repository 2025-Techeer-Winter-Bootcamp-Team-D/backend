from django.urls import path
from .views import (
    get_company_info,
    get_company_financials,
    get_company_reports,
    sync_company_from_dart,
    get_company_rankings,
    process_company_reports_view,
    get_company_prices,
)

urlpatterns = [
    # 기업 상세 정보 주소
    path("<str:stock_code>/", get_company_info, name="company_detail"),
    # 기업 재무 지표 조회
    path(
        "<str:stock_code>/financials/",
        get_company_financials,
        name="company_financials",
    ),
    # 기업 보고서 목록 조회
    path("<str:stock_code>/reports/", get_company_reports, name="company_reports"),
    # 기업 주가 데이터 조회
    path("<str:stock_code>/prices/", get_company_prices, name="company_prices"),
    # DART 데이터 동기화 (관리자용)
    path("<str:stock_code>/sync/", sync_company_from_dart, name="company_sync"),
    # 보고서 처리 (관리자용)
    path(
        "<str:stock_code>/reports/process/",
        process_company_reports_view,
        name="company_reports_process",
    ),
    # 기업 랭킹 조회
    path("rankings/companies/", get_company_rankings, name="company_rankings"),
]
