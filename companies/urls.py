from django.urls import path
from .views import get_company_info

urlpatterns = [
    # 기업 상세 정보 주소
    path('<str:ticker_symbol>/', get_company_info, name='company_detail'),
]