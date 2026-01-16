from django.urls import path
from .views import IndexListView

urlpatterns = [
    path('<str:market_type>/', IndexListView.as_view(), name='index-list'),
]