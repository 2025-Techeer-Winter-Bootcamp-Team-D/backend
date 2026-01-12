from django.urls import path
from .views import CompanyListAPIView

urlpatterns = [
    path('', CompanyListAPIView.as_view(), name='company-list'),
]