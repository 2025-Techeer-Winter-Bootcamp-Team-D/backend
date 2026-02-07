from django.urls import path
from .views import IndexListView, AdminIndexInitializeView

urlpatterns = [
    path('<str:market_type>/', IndexListView.as_view(), name='index-list'),
    path('admin/initialize-indices/', AdminIndexInitializeView.as_view(), name='admin-init-indices'),
]