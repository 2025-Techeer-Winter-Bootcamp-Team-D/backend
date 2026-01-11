# API 문서

## 설정된 엔드포인트

### Health Check API
- **URL**: `http://localhost:8000/health/`
- **Method**: GET
- **설명**: 서버 상태 및 연결된 서비스(DB, Redis)의 상태를 확인합니다.

### Swagger UI (추천)
- **URL**: `http://localhost:8000/swagger/`
- **설명**: 인터랙티브 API 문서. 직접 API를 테스트할 수 있습니다.

### ReDoc
- **URL**: `http://localhost:8000/redoc/`
- **설명**: 읽기 편한 형식의 API 문서

### OpenAPI Schema (JSON)
- **URL**: `http://localhost:8000/api/schema/`
- **설명**: OpenAPI 3.0 스펙 JSON 파일

## 서버 실행 방법

### Docker Compose 사용 (권장)

```bash
# 모든 서비스 시작
docker-compose up

# 백그라운드 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f app
```

서버 시작 후:
1. Swagger UI: http://localhost:8000/swagger/
2. Health Check: http://localhost:8000/health/

## 새로운 API 추가 시 Swagger 문서화 방법

### 1. Function-based View 사용 시

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

@extend_schema(
    summary="API 요약",
    description="API 상세 설명",
    responses={
        200: OpenApiResponse(
            description="성공 응답 설명",
            response={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "example": "성공"},
                    "data": {"type": "object"},
                },
            },
        ),
    },
    tags=["카테고리명"],
)
@api_view(["GET"])
def my_api_view(request):
    return Response({"message": "성공"})
```

### 2. Class-based View (APIView) 사용 시

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

class MyAPIView(APIView):
    @extend_schema(
        summary="GET 요청 설명",
        responses={200: {"type": "object", "properties": {"message": {"type": "string"}}}},
        tags=["카테고리명"],
    )
    def get(self, request):
        return Response({"message": "GET 성공"})

    @extend_schema(
        summary="POST 요청 설명",
        request={
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "홍길동"},
                "age": {"type": "integer", "example": 25},
            },
        },
        responses={201: {"type": "object", "properties": {"id": {"type": "integer"}}}},
        tags=["카테고리명"],
    )
    def post(self, request):
        return Response({"id": 1}, status=201)
```

### 3. ViewSet 사용 시

```python
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema

class MyViewSet(viewsets.ModelViewSet):
    @extend_schema(
        summary="목록 조회",
        tags=["카테고리명"],
    )
    def list(self, request):
        pass

    @extend_schema(
        summary="상세 조회",
        tags=["카테고리명"],
    )
    def retrieve(self, request, pk=None):
        pass
```

### 4. Serializer를 사용한 자동 스키마 생성

```python
from rest_framework import serializers
from drf_spectacular.utils import extend_schema

class UserSerializer(serializers.Serializer):
    name = serializers.CharField(help_text="사용자 이름")
    email = serializers.EmailField(help_text="이메일 주소")
    age = serializers.IntegerField(help_text="나이")

@extend_schema(
    request=UserSerializer,
    responses={200: UserSerializer},
    tags=["사용자"],
)
@api_view(["POST"])
def create_user(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        return Response(serializer.data)
    return Response(serializer.errors, status=400)
```

## Swagger 설정 커스터마이징

`config/settings.py`의 `SPECTACULAR_SETTINGS`에서 추가 설정 가능:

```python
SPECTACULAR_SETTINGS = {
    # ...
    "TAGS": [
        {"name": "Health Check", "description": "서버 상태 확인"},
        {"name": "Users", "description": "사용자 관리 API"},
        {"name": "Products", "description": "상품 관리 API"},
    ],
}
```

## 참고 자료

- [drf-spectacular 공식 문서](https://drf-spectacular.readthedocs.io/)
- [OpenAPI Specification](https://swagger.io/specification/)
