from django.urls import path
from .views import FinancialSankeyView, AdminSankeyUpdateView # 추가

urlpatterns = [
    # 기존 조회용 API
    path('<str:stock_code>/', FinancialSankeyView.as_view(), name='sankey-detail'),
    
    # 관리자용 전수 업데이트 API
    path('admin/update/', AdminSankeyUpdateView.as_view(), name='admin-sankey-update'),
]