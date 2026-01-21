from django.urls import path
from . import views

app_name = 'comparisons'

urlpatterns = [
    path('', views.ComparisonBaseView.as_view(), name='comparison-list'),
    path('<int:comparison_id>/', views.ComparisonDetailView.as_view(), name='comparison-detail'),
    path(
        '<int:comparison_id>/<str:stock_code>/',
        views.ComparisonCompanyDeleteView.as_view(),
        name='comparison-company-delete'
    ),
]