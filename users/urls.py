from django.urls import path, include
from . import views
#즐겨찾기 router
from rest_framework.routers import DefaultRouter
from .views import FavoriteViewSet

app_name = 'users'
# 라우터(즐겨찾기 endpoint 생성)
router = DefaultRouter()
router.register(r'favorites', FavoriteViewSet, basename='favorite')

urlpatterns = [
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('', include(router.urls)), #즐겨찾기
]