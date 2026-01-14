from django.urls import path
from .views import (
    get_company_info,
    get_company_financials,
    get_company_reports,
    sync_company_from_dart,
    get_company_rankings,
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
    # DART 데이터 동기화 (관리자용)
    path("<str:stock_code>/sync/", sync_company_from_dart, name="company_sync"),
    # 기업 랭킹 조회
    path('rankings/companies/', get_company_rankings, name='company_rankings'),
]
