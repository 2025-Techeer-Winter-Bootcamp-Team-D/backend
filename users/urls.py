from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('login/', views.login_account, name='login'),
    path('logout/', views.logout_account, name='logout'),
]