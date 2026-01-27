# 유저별 기업 방문 기록 기능 계획서

## 1. 개요

### 1.1 목적
사용자가 조회했던 기업들의 방문 기록을 저장하고, 이를 통해 최근 방문 기업 목록을 제공하는 기능을 구현합니다.

### 1.2 주요 기능
- 기업 상세 페이지 방문 시 자동으로 방문 기록 저장
- 사용자별 최근 방문 기업 목록 조회
- 방문 기록 삭제 (선택적)

### 1.3 기존 시스템과의 관계
| 기능 | 즐겨찾기 (Favorite) | 방문 기록 (CompanyVisit) |
|------|---------------------|--------------------------|
| 저장 방식 | 사용자 수동 추가 | 자동 기록 |
| 중복 허용 | 불가 (unique_together) | 허용 (재방문 기록) |
| 용도 | 관심 기업 관리 | 최근 조회 기업 확인 |

---

## 2. 데이터 모델 설계

### 2.1 CompanyVisit 모델

```python
# users/models.py

class CompanyVisit(models.Model):
    """사용자의 기업 방문 기록"""

    visit_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_visits'
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='visited_by'
    )
    visited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_visit'
        ordering = ['-visited_at']
        indexes = [
            models.Index(fields=['user', '-visited_at']),
            models.Index(fields=['company', '-visited_at']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.company.company_name} ({self.visited_at})"
```

### 2.2 ERD

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│      User        │       │   CompanyVisit   │       │     Company      │
├──────────────────┤       ├──────────────────┤       ├──────────────────┤
│ id (PK)          │──┐    │ visit_id (PK)    │    ┌──│ stock_code (PK)  │
│ email            │  └───>│ user_id (FK)     │    │  │ company_name     │
│ ...              │       │ company_id (FK)  │<───┘  │ logo_url         │
└──────────────────┘       │ visited_at       │       │ ...              │
                           └──────────────────┘       └──────────────────┘
```

### 2.3 인덱스 전략
- `(user, -visited_at)`: 사용자별 최근 방문 기록 조회 최적화
- `(company, -visited_at)`: 기업별 방문자 통계 (향후 확장 가능)

---

## 3. API 설계

### 3.1 엔드포인트 목록

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/users/visits/` | 방문 기록 목록 조회 |
| POST | `/api/users/visits/` | 방문 기록 추가 |
| DELETE | `/api/users/visits/{visitId}/` | 방문 기록 삭제 |
| DELETE | `/api/users/visits/clear/` | 전체 방문 기록 삭제 |

### 3.2 상세 API 명세

#### 3.2.1 방문 기록 목록 조회
```
GET /api/users/visits/
Authorization: Bearer {access_token}

Query Parameters:
- limit (optional): 조회 개수 (기본값: 20, 최대: 100)
- offset (optional): 시작 위치 (기본값: 0)

Response 200:
{
    "count": 45,
    "next": "/api/users/visits/?limit=20&offset=20",
    "previous": null,
    "results": [
        {
            "visitId": 123,
            "stockCode": "005930",
            "companyName": "삼성전자",
            "logoUrl": "https://...",
            "visitedAt": "2025-01-27T14:30:00+09:00"
        },
        ...
    ]
}
```

#### 3.2.2 방문 기록 추가
```
POST /api/users/visits/
Authorization: Bearer {access_token}
Content-Type: application/json

Request Body:
{
    "stockCode": "005930"
}

Response 201:
{
    "visitId": 124,
    "stockCode": "005930",
    "companyName": "삼성전자",
    "logoUrl": "https://...",
    "visitedAt": "2025-01-27T15:00:00+09:00"
}

Response 400:
{
    "error": "Company not found"
}
```

#### 3.2.3 방문 기록 삭제
```
DELETE /api/users/visits/{visitId}/
Authorization: Bearer {access_token}

Response 204: No Content

Response 404:
{
    "error": "Visit record not found"
}
```

#### 3.2.4 전체 방문 기록 삭제
```
DELETE /api/users/visits/clear/
Authorization: Bearer {access_token}

Response 204: No Content
```

### 3.3 중복 방문 처리 정책

두 가지 옵션 중 선택 필요:

**옵션 A: 모든 방문 기록 저장 (권장)**
- 사용자가 같은 기업을 여러 번 방문하면 각각 기록
- 방문 패턴 분석 가능
- 저장 공간 사용량 증가

**옵션 B: 최근 방문 시간만 업데이트**
- 같은 기업 재방문 시 `visited_at`만 갱신
- 저장 공간 효율적
- 방문 횟수 정보 손실

→ **옵션 A 권장**: 방문 패턴 데이터가 향후 추천 시스템 등에 활용 가능

---

## 4. 구현 계획

### 4.1 구현 단계

#### Phase 1: 기본 구현
1. **모델 생성** (`users/models.py`)
   - CompanyVisit 모델 정의
   - 마이그레이션 파일 생성 및 적용

2. **Serializer 작성** (`users/serializers.py`)
   - CompanyVisitSerializer 구현

3. **ViewSet 구현** (`users/views.py`)
   - CompanyVisitViewSet 구현
   - 권한 설정 (IsAuthenticated)

4. **URL 라우팅** (`users/urls.py`)
   - router에 visits 엔드포인트 등록

#### Phase 2: 고도화 (선택적)
5. **자동 기록 기능**
   - Company 상세 조회 API에서 자동으로 방문 기록 저장
   - 또는 프론트엔드에서 명시적으로 POST 호출

6. **데이터 정리 배치 작업**
   - 오래된 방문 기록 자동 삭제 (Celery Beat)
   - 예: 90일 이상 된 기록 삭제

### 4.2 파일 변경 목록

| 파일 | 변경 내용 |
|------|----------|
| `users/models.py` | CompanyVisit 모델 추가 |
| `users/serializers.py` | CompanyVisitSerializer 추가 |
| `users/views.py` | CompanyVisitViewSet 추가 |
| `users/urls.py` | visits 라우터 등록 |
| `users/migrations/` | 새 마이그레이션 파일 |

---

## 5. 구현 코드 (예시)

### 5.1 Model

```python
# users/models.py

class CompanyVisit(models.Model):
    """사용자의 기업 방문 기록"""

    visit_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_visits'
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='visited_by'
    )
    visited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_visit'
        ordering = ['-visited_at']
        indexes = [
            models.Index(fields=['user', '-visited_at']),
            models.Index(fields=['company', '-visited_at']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.company.company_name}"
```

### 5.2 Serializer

```python
# users/serializers.py

class CompanyVisitSerializer(serializers.ModelSerializer):
    """방문 기록 시리얼라이저"""

    visitId = serializers.IntegerField(source='visit_id', read_only=True)
    stockCode = serializers.CharField(source='company.stock_code')
    companyName = serializers.CharField(source='company.company_name', read_only=True)
    logoUrl = serializers.URLField(source='company.logo_url', read_only=True)
    visitedAt = serializers.DateTimeField(source='visited_at', read_only=True)

    class Meta:
        model = CompanyVisit
        fields = ['visitId', 'stockCode', 'companyName', 'logoUrl', 'visitedAt']

    def create(self, validated_data):
        company_data = validated_data.pop('company')
        stock_code = company_data['stock_code']

        try:
            company = Company.objects.get(stock_code=stock_code, is_deleted=False)
        except Company.DoesNotExist:
            raise serializers.ValidationError({'stockCode': 'Company not found'})

        return CompanyVisit.objects.create(
            user=self.context['request'].user,
            company=company
        )
```

### 5.3 ViewSet

```python
# users/views.py

from rest_framework.decorators import action

@extend_schema_view(
    list=extend_schema(summary="방문 기록 목록 조회", tags=["User"]),
    create=extend_schema(summary="방문 기록 추가", tags=["User"]),
    destroy=extend_schema(summary="방문 기록 삭제", tags=["User"]),
)
class CompanyVisitViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    """사용자 기업 방문 기록 ViewSet"""

    serializer_class = CompanyVisitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CompanyVisit.objects.filter(
            user=self.request.user
        ).select_related('company')

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """전체 방문 기록 삭제"""
        deleted_count, _ = self.get_queryset().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```

### 5.4 URL 라우팅

```python
# users/urls.py

router = DefaultRouter()
router.register(r'favorites', FavoriteViewSet, basename='favorite')
router.register(r'visits', CompanyVisitViewSet, basename='visit')  # 추가

urlpatterns = [
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('', include(router.urls)),
]
```

---

## 6. 고려사항

### 6.1 성능
- 인덱스 적용으로 조회 성능 확보
- `select_related('company')` 사용하여 N+1 쿼리 방지
- 페이지네이션 필수 적용

### 6.2 데이터 관리
- 방문 기록 보존 기간 정책 결정 필요 (예: 90일)
- 오래된 데이터 정리 배치 작업 구현 고려

### 6.3 보안
- `IsAuthenticated` 권한으로 인증된 사용자만 접근
- 자신의 방문 기록만 조회/삭제 가능 (queryset 필터링)

### 6.4 확장 가능성
- 방문 유형 구분 (상세 페이지, 재무제표, 뉴스 등)
- 방문 통계 대시보드
- 기업 추천 시스템 기초 데이터

---

## 7. 테스트 계획

### 7.1 단위 테스트
```python
# users/tests/test_company_visit.py

class CompanyVisitTestCase(TestCase):
    def test_create_visit_record(self):
        """방문 기록 생성 테스트"""
        pass

    def test_list_visit_records(self):
        """방문 기록 목록 조회 테스트"""
        pass

    def test_delete_visit_record(self):
        """방문 기록 삭제 테스트"""
        pass

    def test_clear_all_visits(self):
        """전체 방문 기록 삭제 테스트"""
        pass

    def test_unauthorized_access(self):
        """인증되지 않은 사용자 접근 차단 테스트"""
        pass
```

### 7.2 API 테스트
- Swagger UI에서 각 엔드포인트 테스트
- 인증 토큰 포함 여부에 따른 응답 확인

---

## 8. 일정 (예상)

| 단계 | 작업 내용 | 예상 작업량 |
|------|----------|------------|
| 1 | 모델 및 마이그레이션 | 소 |
| 2 | Serializer | 소 |
| 3 | ViewSet | 소 |
| 4 | URL 라우팅 | 소 |
| 5 | 테스트 작성 | 중 |
| 6 | API 문서 갱신 | 소 |

---

## 9. 관련 이슈

- GitHub Issue: #95

---

## 10. 변경 이력

| 날짜 | 버전 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| 2025-01-27 | 1.0 | Claude | 최초 작성 |
| 2025-01-27 | 1.1 | Claude | 필드명 companyId → stockCode로 변경 |
