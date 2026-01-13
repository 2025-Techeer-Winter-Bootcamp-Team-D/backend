from django.urls import path
from .views import get_company_info, get_company_rankings

urlpatterns = [
    # 기업 상세 정보 주소
    path('companies/<str:stock_code>/', get_company_info, name='company_detail'),
    path('rankings/', get_company_rankings, name='company_rankings'),
    ]