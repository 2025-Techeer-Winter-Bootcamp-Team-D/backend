from django.urls import path
from .views import news_list, news_detail, get_news_keywords

app_name = "news"

urlpatterns = [
    # 뉴스 목록 조회
    path("", news_list, name="news_list"),
    # 뉴스 키워드 빈도수 조회
    path("keywords/", get_news_keywords, name="news_keywords"),
    # 뉴스 상세 조회
    path("<int:news_id>/", news_detail, name="news_detail"),
]
