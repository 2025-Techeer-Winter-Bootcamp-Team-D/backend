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
    sync_all_companies_news,
    search_companies,
    get_company_outlook,
    SankeyAdminBulkSyncView,
    SankeyDataDetailView,
    MainRecentReportListView,
    sync_top_companies,
    run_e2e_tests,
)

urlpatterns = [
    # 기업 검색
    path("search/", search_companies, name="company_search"),
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
    # 보고서 처리 (관리자용) - reports/<rcept_no>/ 보다 위에 배치해야 함
    path(
        "<str:stock_code>/reports/process/",
        process_company_reports_view,
        name="company_reports_process",
    ),
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
    # 기업 전망 분석
    path("<str:stock_code>/outlook/", get_company_outlook, name="company_outlook"),
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
    # 전체 기업 뉴스 동기화 (관리자용)
    path("news/sync/all/", sync_all_companies_news, name="sync_all_companies_news"),
    # DART 데이터 동기화 (관리자용)
    path("<str:stock_code>/sync/", sync_company_from_dart, name="company_sync"),
    # 전체 기업 DART 데이터 동기화 (관리자용)
    path("sync/all/", sync_all_companies_from_dart, name="sync_all_companies"),
    # 기업 랭킹 조회
    path("rankings/companies/", get_company_rankings, name="company_rankings"),
    # 전체 기업 sankey 데이터 업데이트 (관리자용)
    path("sankeys/admin/", SankeyAdminBulkSyncView.as_view(), name="sankey_admin_sync"),
    # 특정 기업의 sankey 데이터 조회
    path(
        "sankeys/<str:stock_code>/",
        SankeyDataDetailView.as_view(),
        name="sankey_detail",
    ),
    # 메인페이지 최신 기업 보고서 조회
    path(
        "reports/recent/",
        MainRecentReportListView.as_view(),
        name="main_recent_reports",
    ),
    # 시가총액 상위 기업 동기화 (관리자용)
    path("sync/top/", sync_top_companies, name="sync_top_companies"),
    # E2E 테스트 (관리자용)
    path("test/e2e/", run_e2e_tests, name="run_e2e_tests"),
]
