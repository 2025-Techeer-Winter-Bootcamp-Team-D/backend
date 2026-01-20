# sankeys/urls.py
from django.urls import path
from .views import SankeyDataDetailView, SankeyAdminBulkSyncView

urlpatterns = [
    # 관리자 전용 일괄 업데이트 
    path('sync/all/', SankeyAdminBulkSyncView.as_view(), name='admin-bulk-sync'),
    # 프론트엔드 조회
    path('<str:stock_code>/', SankeyDataDetailView.as_view(), name='sankey-detail'),
]