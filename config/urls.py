"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from core.views import health_check


# 임시 메인 페이지 함수
def main_page(request):
    return HttpResponse("메인 페이지입니다.")


urlpatterns = [
    # Prometheus metrics (내부 전용 경로로 제한)
    # /internal/metrics 경로로 접근 가능 (프로덕션에서는 nginx/로드밸런서에서 IP 제한 필요)
    path("internal/", include("django_prometheus.urls")),
    # Health Check
    path("health/", health_check, name="health_check"),
    # Admin
    path("admin/", admin.site.urls),
    # API Schema & Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "swagger/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    path("api/users/", include("users.urls")),
    path("api/core/", include("core.urls")),
    path("api/companies/", include("companies.urls")),
    path("api/industries/", include("industries.urls")),
    path("api/comparisons/", include("comparisons.urls")),
    path("api/news/", include("news.urls")),
    path("api/indices/", include("indices.urls")),
    path("api/sankeys/", include("sankeys.urls"))
]
