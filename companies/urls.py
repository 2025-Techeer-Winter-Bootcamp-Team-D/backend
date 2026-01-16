from django.urls import path
from .views import (
    get_company_info,
    get_company_financials,
    get_company_reports,
    get_report_detail,
    sync_company_from_dart,
    sync_all_companies_from_dart,
    get_company_rankings,
    process_company_reports_view,
    process_single_report_view,
    get_company_prices,
    get_company_news_list,
    get_company_news_detail,
    sync_company_news,
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
    # 기업 보고서 분석 결과 조회
    path(
        "<str:stock_code>/reports/<str:rcept_no>/",
        get_report_detail,
        name="report_detail",
    ),
    # 특정 보고서 분석 시작 (관리자용)
    path(
        "<str:stock_code>/reports/<str:rcept_no>/analyze/",
        process_single_report_view,
        name="process_single_report",
    ),
    # 기업 주가 데이터 조회
    path("<str:stock_code>/prices/", get_company_prices, name="company_prices"),
    # 기업 뉴스 목록 조회
    path("<str:stock_code>/news/", get_company_news_list, name="company_news_list"),
    # 기업 뉴스 상세 조회
    path(
        "<str:stock_code>/news/<int:news_id>/",
        get_company_news_detail,
        name="company_news_detail",
    ),
    # 기업 뉴스 동기화 (관리자용)
    path(
        "<str:stock_code>/news/sync/",
        sync_company_news,
        name="company_news_sync",
    ),
    # DART 데이터 동기화 (관리자용)
    path("<str:stock_code>/sync/", sync_company_from_dart, name="company_sync"),
    # 전체 기업 DART 데이터 동기화 (관리자용)
    path("sync/all/", sync_all_companies_from_dart, name="sync_all_companies"),
    # 보고서 처리 (관리자용)
    path(
        "<str:stock_code>/reports/process/",
        process_company_reports_view,
        name="company_reports_process",
    ),
    # 기업 랭킹 조회
    path("rankings/companies/", get_company_rankings, name="company_rankings"),
]
