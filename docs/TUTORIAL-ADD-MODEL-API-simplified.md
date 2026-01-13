# Django 앱 생성 및 REST API 구현 튜토리얼

이 문서는 Django 프로젝트에서 새로운 앱을 생성하고, 모델을 추가하고, REST API를 구현하는 과정을 단계별로 설명합니다.

## 목차

1. Django 앱 생성
2. 모델 추가
3. 마이그레이션 생성 및 적용
4. Serializer 작성
5. ViewSet 작성
6. URL 라우팅 설정
7. API 문서화
8. 테스트 작성

---

## 1. Django 앱 생성

### 앱 생성

```bash
# Docker 환경
docker-compose exec app python manage.py startapp users

# 로컬 환경
python manage.py startapp users
```

### 앱 등록

`config/settings.py`의 `INSTALLED_APPS`에 추가:

```python
INSTALLED_APPS = [
    # ... 기존 앱들
    "users",  # 추가
]
```

### 디렉토리 구조 (권장)

```
users/
├── models.py
├── serializers.py  # 생성
├── urls.py         # 생성
├── views.py
└── tests/
```

---

## 2. 모델 추가

### 모델 정의 예시

```python
# users/models.py
from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nickname = models.CharField(max_length=50, unique=True)
    bio = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
        ordering = ['-created_at']
```

---

## 3. 마이그레이션 생성 및 적용

```bash
# 마이그레이션 생성
python manage.py makemigrations users

# 마이그레이션 적용
python manage.py migrate
```

---

## 4. Serializer 작성

```python
# users/serializers.py
from rest_framework import serializers
from .models import UserProfile

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
```

---

## 5. ViewSet 작성

```python
# users/views.py
from rest_framework import viewsets
from .models import UserProfile
from .serializers import UserProfileSerializer

class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
```

---

## 6. URL 라우팅 설정

### 앱 URL 설정

```python
# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserProfileViewSet

router = DefaultRouter()
router.register(r'profiles', UserProfileViewSet, basename='userprofile')

urlpatterns = [
    path('', include(router.urls)),
]
```

### 프로젝트 URL 설정

```python
# config/urls.py
urlpatterns = [
    # ... 기존 URL들
    path("api/users/", include("users.urls")),  # 추가
]
```

---

## 7. API 문서화

`drf-spectacular` 설정 확인:

```python
# config/settings.py
SPECTACULAR_SETTINGS = {
    "TAGS": [
        {"name": "User Profile", "description": "사용자 프로필 관리"},
    ],
}
```

Swagger UI: http://localhost:8000/api/docs/

---

## 8. 테스트 작성

```python
# users/tests.py
from django.test import TestCase
from rest_framework.test import APITestCase

class UserProfileAPITest(APITestCase):
    def test_list_profiles(self):
        response = self.client.get('/api/users/profiles/')
        self.assertEqual(response.status_code, 200)
```

---

## 체크리스트

- [ ] 모델 정의 완료
- [ ] 마이그레이션 생성 및 적용
- [ ] Serializer 작성
- [ ] ViewSet 작성
- [ ] URL 라우팅 설정
- [ ] API 문서화 확인
- [ ] 테스트 작성 및 실행

---

## 참고 문서

- [Django 공식 문서](https://docs.djangoproject.com/)
- [Django REST Framework 문서](https://www.django-rest-framework.org/)
- [drf-spectacular 문서](https://drf-spectacular.readthedocs.io/)
