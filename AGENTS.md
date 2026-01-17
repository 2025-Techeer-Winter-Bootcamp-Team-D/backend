# AGENTS.md

이 파일은 AI 에이전트가 Django 프로젝트 코드베이스를 효과적으로 작업하기 위한 가이드라인을 제공합니다.

## 빌드/린트/테스트 명령어

### 개발 환경 실행
```bash
# 가상환경 활성화
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 데이터베이스 마이그레이션
python manage.py migrate

# 개발 서버 실행
python manage.py runserver
```

### Docker 환경 실행
```bash
# 전체 서비스 실행
docker-compose up --build -d

# 특정 서비스만 실행
docker-compose up db redis app

# 로그 확인
docker-compose logs -f app

# 서비스 중지
docker-compose down
```

### 테스트 명령어
```bash
# 전체 테스트 실행
python manage.py test

# 특정 앱 테스트 실행
python manage.py test companies
python manage.py test news
python manage.py test users
python manage.py test industries
python manage.py test comparisons
python manage.py test indices

# 특정 테스트 파일만 실행
python manage.py test companies.tests
python manage.py test news.tests

# 테스트 상세 출력
python manage.py test --verbosity=2

# 특정 테스트 메서드만 실행
python manage.py test companies.tests.CompanyModelTest.test_company_creation
```

### Django 관리 명령어
```bash
# 마이그레이션 생성 및 적용
python manage.py makemigrations
python manage.py migrate

# 슈퍼유저 생성
python manage.py createsuperuser

# Django 셸 실행
python manage.py shell

# 정적 파일 수집
python manage.py collectstatic
```

### Docker 환경에서 Django 명령 실행
```bash
# 앱 컨테이너 내부에서 명령 실행
docker-compose exec app python manage.py migrate
docker-compose exec app python manage.py test
docker-compose exec app python manage.py createsuperuser
```

## 코드 스타일 가이드라인

### 임포트 순서
1. 표준 라이브러리 임포트
2. 서드파티 라이브러리 임포트
3. Django 관련 임포트
4. 로컬 앱 임포트

```python
# 표준 라이브러리
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse

# 서드파티 라이브러리
import redis
import requests
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

# Django 관련
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

# 로컬 앱 임포트
from companies.models import Company
from companies.serializers import CompanySerializer
from core.services import BaseService
```

### 포맷팅 규칙
- **들여쓰기**: 4칸 스페이스 사용 (탭 사용 금지)
- **라인 길이**: 최대 88자 (Black 기준)
- **빈 줄**: 함수와 클래스 사이에는 2줄, 메서드 사이에는 1줄
- **문자열**: f-string 사용 권장, 복잡한 포맷팅은 .format() 사용

### 타입 힌트
```python
from typing import List, Dict, Optional, Union, Any
from django.http import HttpRequest, JsonResponse
from rest_framework.request import Request

def get_company_data(
    request: Request, 
    company_id: int
) -> JsonResponse:
    """기업 데이터 조회 API 엔드포인트"""
    pass

def process_news_articles(
    articles: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """뉴스 기사 처리 함수"""
    pass
```

### 네이밍 컨벤션
- **변수/함수**: snake_case 사용
- **클래스**: PascalCase 사용
- **상수**: UPPER_SNAKE_CASE 사용
- **파일명**: 소문자와 언더스코어 사용

```python
# 변수/함수
company_name = "삼성전자"
def get_user_profile(user_id: int) -> Dict:
    pass

# 클래스
class CompanyService:
    pass

# 상수
MAX_RETRY_COUNT = 3
DEFAULT_TIMEOUT = 30
API_BASE_URL = "https://api.example.com"

# 파일명
company_service.py
user_views.py
```

### 에러 핸들링
```python
# try-except 블록은 구체적인 예외 처리
try:
    company = Company.objects.get(id=company_id)
except Company.DoesNotExist:
    return Response(
        {"error": "존재하지 않는 기업입니다."}, 
        status=status.HTTP_404_NOT_FOUND
    )
except DatabaseError as e:
    logger.error(f"데이터베이스 오류: {e}")
    return Response(
        {"error": "서버 오류가 발생했습니다."}, 
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )

# 로깅은 항상 포함
import logging

logger = logging.getLogger(__name__)

def external_api_call(url: str) -> Dict:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"API 호출 실패: {url}, 오류: {e}")
        raise
```

### Django 모델 작성 규칙
```python
from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    """기업 정보 모델"""
    
    name = models.CharField("기업명", max_length=100)
    stock_code = models.CharField("종목코드", max_length=10, unique=True)
    description = models.TextField("설명", blank=True)
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)
    
    class Meta:
        verbose_name = "기업"
        verbose_name_plural = "기업들"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['stock_code']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self) -> str:
        return f"{self.name} ({self.stock_code})"
    
    def get_absolute_url(self) -> str:
        return f"/companies/{self.id}/"
```

### DRF 시리얼라이저 작성 규칙
```python
from rest_framework import serializers
from .models import Company

class CompanySerializer(serializers.ModelSerializer):
    """기업 정보 시리얼라이저"""
    
    market_cap = serializers.SerializerMethodField()
    
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'stock_code', 'description', 
            'market_cap', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_market_cap(self, obj: Company) -> int:
        """시가총액 계산"""
        return obj.get_market_cap()
    
    def validate_stock_code(self, value: str) -> str:
        """종목코드 유효성 검증"""
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError("종목코드는 6자리 숫자여야 합니다.")
        return value
```

### 뷰 작성 규칙
```python
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from .models import Company
from .serializers import CompanySerializer

class CompanyListCreateView(generics.ListCreateAPIView):
    """기업 목록 조회 및 생성 API"""
    
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """쿼리셋 커스터마이징"""
        queryset = super().get_queryset()
        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)
        return queryset

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_detail(request: Request, pk: int) -> Response:
    """기업 상세 정보 조회"""
    try:
        company = get_object_or_404(Company, pk=pk)
        serializer = CompanySerializer(company)
        return Response(serializer.data)
    except Exception as e:
        logger.error(f"기업 정보 조회 오류: {e}")
        return Response(
            {"error": "서버 오류가 발생했습니다."}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
```

### 서비스 레이어 작성 규칙
```python
from typing import List, Optional, Dict, Any
from django.core.cache import cache
from django.db import transaction

from .models import Company

class CompanyService:
    """기업 관련 비즈니스 로직 서비스"""
    
    CACHE_TIMEOUT = 300  # 5분
    
    @classmethod
    def get_company_by_code(cls, stock_code: str) -> Optional[Company]:
        """종목코드로 기업 조회 (캐싱 포함)"""
        cache_key = f"company:{stock_code}"
        company = cache.get(cache_key)
        
        if company is None:
            try:
                company = Company.objects.get(stock_code=stock_code)
                cache.set(cache_key, company, cls.CACHE_TIMEOUT)
            except Company.DoesNotExist:
                return None
        
        return company
    
    @classmethod
    @transaction.atomic
    def update_company_ranking(cls, rankings: List[Dict[str, Any]]) -> None:
        """기업 순위 정보 업데이트 (트랜잭션)"""
        for ranking_data in rankings:
            stock_code = ranking_data['stock_code']
            rank = ranking_data['rank']
            
            Company.objects.filter(stock_code=stock_code).update(rank=rank)
        
        # 캐시 무효화
        cache.delete_pattern("company:*")
```

## 프로젝트 특이사항

### 환경 변수 사용
- 모든 민감 정보는 `.env` 파일에 저장
- `config/settings.py`에서 `os.getenv()`로 가져오기
- Docker 환경에서는 `docker-compose.yml`의 `env_file` 사용

### 데이터베이스 아키텍처
- **TimescaleDB**: 시계열 데이터 저장용 PostgreSQL 확장
- **Redis**: 캐싱 및 세션 저장, Celery 브로커
- **OpenSearch**: 검색 엔진 (개발 환경에서 보안 플러그인 비활성화)

### Celery 비동기 작업
- 백그라운드 작업은 Celery 사용
- 환경 변수로 개별 작업 활성화/비활성화 가능
- `NEWS_BATCH_ENABLED`, `DART_SYNC_ENABLED`, `REPORT_PROCESSING_ENABLED`

### API 문서화
- drf-spectacular로 OpenAPI/Swagger 자동 생성
- `/api/docs/`에서 Swagger UI 접근 가능
- 모든 API 엔드포인트은 적절한 데코레이터로 문서화

### 커밋 메시지 규칙
```
<IssueType>: <Message>

feat: 회원가입 기능 구현 완료
fix: 로그인 시 토큰 만료 오류 수정
docs: API 명세서 업데이트
chore: Docker Compose 설정 추가
refactor: 사용자 인증 로직 개선
```
커밋을 할 때에는 논리적으로 묶어서 여러번 시행

## 기존 설정 파일
- `.cursor/rules`, `.cursorrules`, `.github/copilot-instructions.md` 파일은 존재하지 않음
- 기존 `AGENTS.md` 파일은 없어서 새로 생성

## 커뮤니케이션 규칙
- 한국어
- 주석 작성: 한국어
- 커밋 메시지: 한국어
- 변수/함수명: 영어(표준)
