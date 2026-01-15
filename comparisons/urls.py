from django.urls import path
from . import views

app_name = 'comparisons'

urlpatterns = [
    path('', views.ComparisonBaseView.as_view(), name='comparison-list'),
    
    # 상세조회, 추가, 전체삭제 틀이 나옴
    path('<int:comparison_id>/', views.ComparisonDetailView.as_view(), name='comparison-detail'),
    
    # 이제 여기는 DELETE 틀 딱 하나만 나옴! (GET, POST가 아예 클래스에 없으니까)
    path('<int:comparison_id>/<str:stock_code>/', views.ComparisonCompanyDeleteView.as_view(), name='comparison-company-delete'),
]