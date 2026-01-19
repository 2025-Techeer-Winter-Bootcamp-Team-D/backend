from django.urls import path
from .views import (
    IndustryCompanyRankView,
    get_industry_rankings,
    get_industry_news,
    get_industry_indices,
    IndustryChartView,
    IndustryBackfillView,
    get_industry_outlook,
)

urlpatterns = [
    # 산업 내 기업 순위 조회 (induty_code로 조회)
    path(
        "<str:induty_code>/companies/",
        IndustryCompanyRankView.as_view(),
        name="industry_company_rank",
    ),
    # 산업 뉴스 조회 (induty_code로 조회)
    path("<str:induty_code>/news/", get_industry_news, name="industry_news"),
    path("<str:induty_code>/outlook/", get_industry_outlook, name="industry_outlook"),
    # 전체 산업 순위 목록
    path("rankings/industries/", get_industry_rankings, name="industry_rankings"),
    # 산업 지수 목록 (사용자 작업분)
    path("indices/", get_industry_indices, name="industry_indices"),
    # 특정 산업 차트 데이터 조회 (induty_code로 조회)
    path(
        "<str:induty_code>/chart/", IndustryChartView.as_view(), name="industry_chart"
    ),
    # 관리자 전용 데이터 적재 API (사용자 작업분)
    path("admin/backfill/", IndustryBackfillView.as_view(), name="industry_backfill"),
]
