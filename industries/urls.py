from django.urls import path
from .views import IndustryCompanyRankView # 이전 답변에서 작성한 View

urlpatterns = [
    # config에서 'api/industries/'로 들어왔으므로, 여기서는 그 뒷부분만 정의합니다.
    path('<int:industry_id>/companies', IndustryCompanyRankView.as_view(), name='industry_company_rank'),
]