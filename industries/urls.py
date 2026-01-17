from django.urls import path
from .views import IndustryCompanyRankView, get_industry_rankings, get_industry_news

urlpatterns = [
    # config에서 'api/industries/'로 들어왔으므로, 여기서는 그 뒷부분만 정의합니다.
    path('<int:industry_id>/companies', IndustryCompanyRankView.as_view(), name='industry_company_rank'),
    path('<int:industry_id>/news/', get_industry_news, name='industry_news'),
    path('rankings/industries/', get_industry_rankings, name='industry_rankings'),
]