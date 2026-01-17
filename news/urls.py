from django.urls import path
from .views import news_list, news_detail, get_news_keywords, trigger_crawl_news

app_name = "news"

urlpatterns = [
    # 뉴스 목록 조회
    path("", news_list, name="news_list"),
    # 뉴스 키워드 빈도수 조회
    path("keywords/", get_news_keywords, name="news_keywords"),
    # 뉴스 상세 조회
    path("<int:news_id>/", news_detail, name="news_detail"),
    # 관리자용 뉴스 크롤링 수동 실행
    path("admin/crawl/", trigger_crawl_news, name="admin_crawl_news"),
]
