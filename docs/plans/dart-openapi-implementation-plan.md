# DART OpenAPI 연동 기업 정보 API 구현 계획서

**작성일**: 2026-01-13  
**작성자**: Claude (AI Assistant)  
**버전**: 1.0

---

## 1. 개요

### 1.1 목표
금융감독원 전자공시시스템(DART) OpenAPI를 활용하여 다음 3가지 API를 구현합니다:
1. **기업 기본 정보 조회 API** - 종목코드, 산업코드, 이름, 소개, 로고URL
2. **기업 재무 지표 조회 API** - 매출액, 시가총액, 매출 구성 등
3. **기업 보고서 조회 API** - 해당 기업의 정기/수시 보고서 목록

### 1.2 DART OpenAPI 주요 엔드포인트
| 기능 | 엔드포인트 | 설명 |
|-----|----------|------|
| 기업개황 | `GET /api/company.json` | 기업 기본 정보 조회 |
| 재무제표 | `GET /api/fnlttSinglAcntAll.json` | 단일회사 전체 재무제표 |
| 공시검색 | `GET /api/list.json` | 공시 보고서 목록 조회 |
| 고유번호 | `GET /api/corpCode.xml` (ZIP) | 전체 기업 고유번호 목록 |

### 1.3 DART API 기본 URL
- **Base URL**: `https://opendart.fss.or.kr/api`
- **인증**: 모든 요청에 `crtfc_key` 파라미터로 API 키 전달

---

## 2. 사전 작업

### 2.1 환경 설정

```bash
# .env 파일에 DART API 키 추가
DART_API_KEY=your_dart_api_key_here
```

```python
# config/settings.py 에 추가
DART_API_KEY = os.getenv("DART_API_KEY") or None
DART_API_BASE_URL = "https://opendart.fss.or.kr/api"
```

### 2.2 의존성 추가

```txt
# requirements.txt 에 추가
requests>=2.31.0  # 이미 있을 수 있음
xmltodict>=0.13.0  # XML 파싱용 (고유번호 목록)
```

---

## 3. 모델 설계

### 3.1 Company 모델 수정

**현재 모델** (`companies/models.py`):
```python
class Company(models.Model):
    stock_code = models.CharField(primary_key=True, max_length=255)
    industry = models.ForeignKey('industries.Industry', on_delete=models.CASCADE, related_name='companies', db_column='industry_id')
    company_name = models.CharField(max_length=255)
    description = models.TextField()
    market_amount = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'company'
```

**수정 제안**:
```python
# companies/models.py
class Company(models.Model):
    stock_code = models.CharField(primary_key=True, max_length=10)  # 종목코드 (6자리)
    corp_code = models.CharField(max_length=8, unique=True, null=True)  # DART 고유번호 (8자리) - 신규
    industry = models.ForeignKey('industries.Industry', on_delete=models.CASCADE, related_name='companies', db_column='industry_id')
    company_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    logo_url = models.URLField(max_length=500, blank=True, null=True)  # 신규
    market_amount = models.BigIntegerField(default=0)  # 시가총액
    # DART 기업개황 추가 필드
    ceo_name = models.CharField(max_length=100, blank=True, null=True)  # 대표자명
    establishment_date = models.DateField(null=True)  # 설립일
    homepage_url = models.URLField(max_length=500, blank=True, null=True)  # 홈페이지
    address = models.TextField(blank=True, null=True)  # 본사 주소
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'company'
```

### 3.2 FinancialStatement 모델 (신규)

```python
# companies/models.py
class FinancialStatement(models.Model):
    """기업 재무제표 데이터"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='financial_statements')
    fiscal_year = models.IntegerField()  # 사업연도 (예: 2024)
    report_code = models.CharField(max_length=5)  # 보고서 코드 (11011: 사업보고서, 11012: 반기보고서 등)
    
    # 주요 재무 지표 (단위: 원)
    revenue = models.BigIntegerField(null=True)  # 매출액
    operating_profit = models.BigIntegerField(null=True)  # 영업이익
    net_income = models.BigIntegerField(null=True)  # 당기순이익
    total_assets = models.BigIntegerField(null=True)  # 총자산
    total_liabilities = models.BigIntegerField(null=True)  # 총부채
    total_equity = models.BigIntegerField(null=True)  # 총자본
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'financial_statement'
        unique_together = ['company', 'fiscal_year', 'report_code']
        ordering = ['-fiscal_year', '-report_code']
```

**보고서 코드 (reprt_code) 참조**:
| 코드 | 보고서명 |
|-----|---------|
| 11011 | 사업보고서 |
| 11012 | 반기보고서 |
| 11013 | 1분기보고서 |
| 11014 | 3분기보고서 |

### 3.3 RevenueComposition 모델 (신규)

```python
# companies/models.py
class RevenueComposition(models.Model):
    """매출 구성 데이터"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='revenue_compositions')
    fiscal_year = models.IntegerField()  # 사업연도
    segment_name = models.CharField(max_length=255)  # 사업부문명
    revenue = models.BigIntegerField()  # 매출액
    ratio = models.DecimalField(max_digits=5, decimal_places=2, null=True)  # 매출 비중 (%)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_composition'
        ordering = ['-fiscal_year', '-revenue']
```

### 3.4 Report 모델 (신규)

```python
# companies/models.py
class Report(models.Model):
    """기업 공시 보고서"""
    REPORT_TYPE_CHOICES = [
        ('A', '정기공시'),
        ('B', '주요사항보고'),
        ('C', '발행공시'),
        ('D', '지분공시'),
        ('E', '기타공시'),
        ('F', '외부감사관련'),
        ('G', '펀드공시'),
        ('H', '자산유동화'),
        ('I', '거래소공시'),
        ('J', '공정위공시'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='reports')
    rcept_no = models.CharField(max_length=20, unique=True)  # 접수번호
    report_name = models.CharField(max_length=500)  # 보고서명
    report_type = models.CharField(max_length=1, choices=REPORT_TYPE_CHOICES)  # 공시유형
    submitted_at = models.DateField()  # 접수일자
    report_url = models.URLField(max_length=500)  # 보고서 URL
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'report'
        ordering = ['-submitted_at']
```

---

## 4. DART API 서비스 레이어

### 4.1 파일 구조

```
companies/
├── services/
│   ├── __init__.py
│   ├── dart_api.py          # DART API 클라이언트
│   ├── company_info.py      # 기업 기본 정보 서비스
│   ├── financial.py         # 재무 지표 서비스
│   └── reports.py           # 보고서 서비스
├── tasks/
│   ├── __init__.py
│   └── dart_sync.py         # Celery 비동기 작업
```

### 4.2 DART API 클라이언트 (`companies/services/dart_api.py`)

```python
import requests
from django.conf import settings
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class DartAPIClient:
    """DART OpenAPI 클라이언트"""
    
    BASE_URL = "https://opendart.fss.or.kr/api"
    
    def __init__(self):
        self.api_key = settings.DART_API_KEY
        if not self.api_key:
            raise ValueError("DART_API_KEY가 설정되지 않았습니다.")
    
    def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """API 요청 공통 메서드"""
        params['crtfc_key'] = self.api_key
        
        url = f"{self.BASE_URL}/{endpoint}"
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # DART API 응답 상태 코드 확인
        status = data.get('status', '000')
        if status != '000':
            raise DartAPIError(f"DART API 오류: {data.get('message', '알 수 없는 오류')}")
        
        return data
    
    def get_company_info(self, corp_code: str) -> Dict[str, Any]:
        """기업개황 조회"""
        return self._request('company.json', {'corp_code': corp_code})
    
    def get_financial_statements(
        self, 
        corp_code: str, 
        bsns_year: str,  # 사업연도 (예: "2024")
        reprt_code: str = "11011"  # 11011: 사업보고서
    ) -> Dict[str, Any]:
        """단일회사 전체 재무제표 조회"""
        params = {
            'corp_code': corp_code,
            'bsns_year': bsns_year,
            'reprt_code': reprt_code,
            'fs_div': 'CFS',  # CFS: 연결재무제표, OFS: 개별재무제표
        }
        return self._request('fnlttSinglAcntAll.json', params)
    
    def get_disclosure_list(
        self,
        corp_code: str,
        bgn_de: Optional[str] = None,  # 시작일 (YYYYMMDD)
        end_de: Optional[str] = None,  # 종료일 (YYYYMMDD)
        pblntf_ty: Optional[str] = None,  # 공시유형 (A, B, C, D, E, F, G, H, I, J)
        page_no: int = 1,
        page_count: int = 100
    ) -> Dict[str, Any]:
        """공시검색 (보고서 목록 조회)"""
        params = {
            'corp_code': corp_code,
            'page_no': str(page_no),
            'page_count': str(page_count),
        }
        if bgn_de:
            params['bgn_de'] = bgn_de
        if end_de:
            params['end_de'] = end_de
        if pblntf_ty:
            params['pblntf_ty'] = pblntf_ty
            
        return self._request('list.json', params)


class DartAPIError(Exception):
    """DART API 예외"""
    pass
```

### 4.3 DART API 응답 상태 코드

| 코드 | 설명 |
|-----|------|
| 000 | 정상 |
| 010 | 등록되지 않은 키입니다 |
| 011 | 사용할 수 없는 키입니다 |
| 012 | 접근할 수 없는 IP입니다 |
| 013 | 일일 요청 한도 초과 |
| 020 | 요청 파라미터 오류 |
| 100 | 조회된 데이터 없음 |
| 800 | 시스템 점검 중 |
| 900 | 정의되지 않은 오류 |

---

## 5. API 엔드포인트 설계

### 5.1 API 명세

| Method | Endpoint | 설명 | 인증 |
|--------|----------|------|-----|
| GET | `/companies/{stock_code}/` | 기업 기본 정보 조회 (기존 확장) | X |
| GET | `/companies/{stock_code}/financials/` | 기업 재무 지표 조회 (신규) | X |
| GET | `/companies/{stock_code}/reports/` | 기업 보고서 목록 조회 (신규) | X |
| POST | `/companies/{stock_code}/sync/` | DART 데이터 동기화 (관리용, 신규) | O |

### 5.2 응답 형식

#### 5.2.1 기업 기본 정보 응답

**Request:**
```http
GET /companies/005930/
```

**Response (200 OK):**
```json
{
  "status": 200,
  "message": "기업 정보 조회 성공",
  "data": {
    "stock_code": "005930",
    "corp_code": "00126380",
    "company_name": "삼성전자",
    "industry": {
      "industry_id": 1,
      "name": "반도체"
    },
    "description": "전자부품, 컴퓨터, 통신기기 제조업...",
    "logo_url": "https://...",
    "market_amount": 350000000000000,
    "ceo_name": "한종희",
    "establishment_date": "1969-01-13",
    "homepage_url": "https://www.samsung.com/sec/"
  }
}
```

#### 5.2.2 재무 지표 응답

**Request:**
```http
GET /companies/005930/financials/
```

**Query Parameters:**
- `year` (optional): 조회 연도 (기본값: 최근 3년)

**Response (200 OK):**
```json
{
  "status": 200,
  "message": "재무 지표 조회 성공",
  "data": {
    "stock_code": "005930",
    "company_name": "삼성전자",
    "market_amount": 350000000000000,
    "financial_statements": [
      {
        "fiscal_year": 2024,
        "report_type": "사업보고서",
        "revenue": 302231000000000,
        "operating_profit": 6565000000000,
        "net_income": 15487000000000,
        "total_assets": 455000000000000,
        "total_equity": 350000000000000
      },
      {
        "fiscal_year": 2023,
        "report_type": "사업보고서",
        "revenue": 258935000000000,
        "operating_profit": 6565000000000,
        "net_income": 15820000000000,
        "total_assets": 448000000000000,
        "total_equity": 340000000000000
      }
    ],
    "revenue_composition": [
      {
        "segment_name": "DS(반도체)",
        "revenue": 145000000000000,
        "ratio": 48.0
      },
      {
        "segment_name": "DX(가전/모바일)",
        "revenue": 130000000000000,
        "ratio": 43.0
      },
      {
        "segment_name": "SDC(디스플레이)",
        "revenue": 27000000000000,
        "ratio": 9.0
      }
    ]
  }
}
```

#### 5.2.3 보고서 목록 응답

**Request:**
```http
GET /companies/005930/reports/?type=A&page=1
```

**Query Parameters:**
- `type` (optional): 공시유형 (A: 정기공시, B: 주요사항보고 등)
- `page` (optional): 페이지 번호 (기본값: 1)
- `size` (optional): 페이지 크기 (기본값: 20, 최대: 100)

**Response (200 OK):**
```json
{
  "status": 200,
  "message": "보고서 목록 조회 성공",
  "data": {
    "total_count": 150,
    "page": 1,
    "page_size": 20,
    "reports": [
      {
        "rcept_no": "20240315000123",
        "report_name": "사업보고서 (2024.12)",
        "report_type": "정기공시",
        "submitted_at": "2024-03-15",
        "report_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240315000123"
      },
      {
        "rcept_no": "20240115000456",
        "report_name": "분기보고서 (2024.09)",
        "report_type": "정기공시",
        "submitted_at": "2024-11-15",
        "report_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240115000456"
      }
    ]
  }
}
```

---

## 6. Serializers 설계

### 6.1 기업 기본 정보 Serializer

```python
# companies/serializers.py

class IndustrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Industry
        fields = ['industry_id', 'name']


class CompanyDetailSerializer(serializers.ModelSerializer):
    industry = IndustrySerializer(read_only=True)
    
    class Meta:
        model = Company
        fields = [
            'stock_code', 'corp_code', 'company_name', 'industry',
            'description', 'logo_url', 'market_amount', 'ceo_name',
            'establishment_date', 'homepage_url', 'address'
        ]
```

### 6.2 재무 지표 Serializer

```python
# companies/serializers.py

class FinancialStatementSerializer(serializers.ModelSerializer):
    report_type = serializers.SerializerMethodField()
    
    class Meta:
        model = FinancialStatement
        fields = [
            'fiscal_year', 'report_type', 'revenue', 'operating_profit',
            'net_income', 'total_assets', 'total_liabilities', 'total_equity'
        ]
    
    def get_report_type(self, obj):
        report_types = {
            '11011': '사업보고서',
            '11012': '반기보고서',
            '11013': '1분기보고서',
            '11014': '3분기보고서',
        }
        return report_types.get(obj.report_code, '기타')


class RevenueCompositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueComposition
        fields = ['segment_name', 'revenue', 'ratio']


class CompanyFinancialsSerializer(serializers.Serializer):
    stock_code = serializers.CharField()
    company_name = serializers.CharField()
    market_amount = serializers.IntegerField()
    financial_statements = FinancialStatementSerializer(many=True)
    revenue_composition = RevenueCompositionSerializer(many=True)
```

### 6.3 보고서 Serializer

```python
# companies/serializers.py

class ReportSerializer(serializers.ModelSerializer):
    report_type = serializers.SerializerMethodField()
    
    class Meta:
        model = Report
        fields = ['rcept_no', 'report_name', 'report_type', 'submitted_at', 'report_url']
    
    def get_report_type(self, obj):
        return obj.get_report_type_display()


class ReportListSerializer(serializers.Serializer):
    total_count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    reports = ReportSerializer(many=True)
```

---

## 7. Views 구현

### 7.1 기업 재무 지표 조회 View

```python
# companies/views.py

@extend_schema(
    summary="기업 재무 지표 조회",
    description="티커 심볼을 통해 해당 기업의 재무 지표를 조회합니다.",
    parameters=[
        OpenApiParameter(
            name='stock_code',
            type=str,
            location=OpenApiParameter.PATH,
            description='조회할 기업의 종목코드 (예: 005930)'
        ),
        OpenApiParameter(
            name='year',
            type=int,
            location=OpenApiParameter.QUERY,
            description='조회할 연도 (기본값: 최근 3년)',
            required=False
        ),
    ],
    responses={200: CompanyFinancialsSerializer, 404: OpenApiResponse(description="Not Found")},
    tags=["Company"]
)
@api_view(["GET"])
def get_company_financials(request, stock_code):
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)
        
        # 재무제표 조회 (최근 3년)
        financial_statements = company.financial_statements.all()[:3]
        
        # 매출 구성 조회 (최신 연도)
        latest_year = financial_statements.first().fiscal_year if financial_statements else None
        revenue_composition = company.revenue_compositions.filter(
            fiscal_year=latest_year
        ) if latest_year else []
        
        data = {
            'stock_code': company.stock_code,
            'company_name': company.company_name,
            'market_amount': company.market_amount,
            'financial_statements': financial_statements,
            'revenue_composition': revenue_composition
        }
        
        serializer = CompanyFinancialsSerializer(data)
        return Response({
            'status': 200,
            'message': '재무 지표 조회 성공',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
```

### 7.2 기업 보고서 조회 View

```python
# companies/views.py

@extend_schema(
    summary="기업 보고서 목록 조회",
    description="티커 심볼을 통해 해당 기업의 공시 보고서 목록을 조회합니다.",
    parameters=[
        OpenApiParameter(
            name='stock_code',
            type=str,
            location=OpenApiParameter.PATH,
            description='조회할 기업의 종목코드 (예: 005930)'
        ),
        OpenApiParameter(
            name='type',
            type=str,
            location=OpenApiParameter.QUERY,
            description='공시유형 (A: 정기공시, B: 주요사항보고 등)',
            required=False
        ),
        OpenApiParameter(
            name='page',
            type=int,
            location=OpenApiParameter.QUERY,
            description='페이지 번호 (기본값: 1)',
            required=False
        ),
        OpenApiParameter(
            name='size',
            type=int,
            location=OpenApiParameter.QUERY,
            description='페이지 크기 (기본값: 20, 최대: 100)',
            required=False
        ),
    ],
    responses={200: ReportListSerializer, 404: OpenApiResponse(description="Not Found")},
    tags=["Company"]
)
@api_view(["GET"])
def get_company_reports(request, stock_code):
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)
        
        # 쿼리 파라미터
        report_type = request.query_params.get('type')
        page = int(request.query_params.get('page', 1))
        size = min(int(request.query_params.get('size', 20)), 100)
        
        # 보고서 조회
        reports = company.reports.all()
        if report_type:
            reports = reports.filter(report_type=report_type)
        
        total_count = reports.count()
        
        # 페이지네이션
        start = (page - 1) * size
        end = start + size
        reports = reports[start:end]
        
        serializer = ReportSerializer(reports, many=True)
        return Response({
            'status': 200,
            'message': '보고서 목록 조회 성공',
            'data': {
                'total_count': total_count,
                'page': page,
                'page_size': size,
                'reports': serializer.data
            }
        }, status=status.HTTP_200_OK)
        
    except Company.DoesNotExist:
        return Response(
            {"status": 404, "error": "Company not found"}, 
            status=status.HTTP_404_NOT_FOUND
        )
```

---

## 8. URL 라우팅

```python
# companies/urls.py
from django.urls import path
from .views import (
    get_company_info,
    get_company_financials,
    get_company_reports,
)

urlpatterns = [
    path('<str:stock_code>/', get_company_info, name='company_detail'),
    path('<str:stock_code>/financials/', get_company_financials, name='company_financials'),
    path('<str:stock_code>/reports/', get_company_reports, name='company_reports'),
]
```

---

## 9. Celery 데이터 동기화 작업

### 9.1 동기화 Task 구현

```python
# companies/tasks/dart_sync.py
from celery import shared_task
from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.models import Company, FinancialStatement, Report
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_company_info_from_dart(self, stock_code: str):
    """DART에서 기업 기본 정보 동기화"""
    try:
        company = Company.objects.get(pk=stock_code)
        
        if not company.corp_code:
            logger.warning(f"Corp code not found for {stock_code}")
            return
        
        client = DartAPIClient()
        data = client.get_company_info(company.corp_code)
        
        # 기업 정보 업데이트
        company.ceo_name = data.get('ceo_nm')
        company.homepage_url = data.get('hm_url')
        company.address = data.get('adres')
        company.save()
        
        logger.info(f"Synced company info for {stock_code}")
        
    except DartAPIError as e:
        logger.error(f"DART API error: {e}")
        self.retry(countdown=60)
    except Exception as e:
        logger.error(f"Error syncing company info: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def sync_financial_statements(self, stock_code: str, year: int):
    """DART에서 재무제표 동기화"""
    try:
        company = Company.objects.get(pk=stock_code)
        
        if not company.corp_code:
            return
        
        client = DartAPIClient()
        
        # 사업보고서 조회
        data = client.get_financial_statements(
            company.corp_code, 
            str(year), 
            reprt_code='11011'
        )
        
        # 재무제표 저장 로직
        # ... (상세 구현 필요)
        
        logger.info(f"Synced financial statements for {stock_code} ({year})")
        
    except DartAPIError as e:
        logger.error(f"DART API error: {e}")
        self.retry(countdown=60)
    except Exception as e:
        logger.error(f"Error syncing financial statements: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def sync_company_reports(self, stock_code: str, days: int = 365):
    """DART에서 보고서 목록 동기화"""
    from datetime import datetime, timedelta
    
    try:
        company = Company.objects.get(pk=stock_code)
        
        if not company.corp_code:
            return
        
        client = DartAPIClient()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        data = client.get_disclosure_list(
            company.corp_code,
            bgn_de=start_date.strftime('%Y%m%d'),
            end_de=end_date.strftime('%Y%m%d')
        )
        
        # 보고서 저장
        for item in data.get('list', []):
            Report.objects.update_or_create(
                rcept_no=item['rcept_no'],
                defaults={
                    'company': company,
                    'report_name': item['report_nm'],
                    'report_type': item.get('pblntf_ty', 'E'),
                    'submitted_at': datetime.strptime(item['rcept_dt'], '%Y%m%d').date(),
                    'report_url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}"
                }
            )
        
        logger.info(f"Synced reports for {stock_code}")
        
    except DartAPIError as e:
        logger.error(f"DART API error: {e}")
        self.retry(countdown=60)
    except Exception as e:
        logger.error(f"Error syncing reports: {e}")
        raise
```

### 9.2 Celery Beat 스케줄 설정

```python
# config/settings.py 에 추가

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # ... 기존 스케줄 ...
    
    # DART 기업 정보 동기화: 주 1회 (일요일 새벽 3시)
    'sync-dart-company-info-weekly': {
        'task': 'companies.tasks.dart_sync.sync_all_company_info',
        'schedule': crontab(day_of_week=0, hour=3, minute=0),
    },
    
    # DART 보고서 목록 동기화: 일 1회 (새벽 4시)
    'sync-dart-reports-daily': {
        'task': 'companies.tasks.dart_sync.sync_all_reports',
        'schedule': crontab(hour=4, minute=0),
    },
}
```

---

## 10. 구현 일정 (예상 3-4일)

### Day 1: 기반 작업
- [ ] `.env`에 `DART_API_KEY` 추가 및 `settings.py` 설정
- [ ] `requirements.txt`에 의존성 추가 (`xmltodict`)
- [ ] Company 모델 필드 추가 (`corp_code`, `logo_url`, `ceo_name` 등)
- [ ] `FinancialStatement`, `RevenueComposition`, `Report` 모델 생성
- [ ] 마이그레이션 생성 및 적용

### Day 2: DART API 서비스 레이어
- [ ] `companies/services/dart_api.py` - DART API 클라이언트 구현
- [ ] `companies/services/company_info.py` - 기업 기본 정보 서비스
- [ ] `companies/services/financial.py` - 재무 지표 서비스
- [ ] `companies/services/reports.py` - 보고서 서비스

### Day 3: API 엔드포인트 구현
- [ ] 기업 기본 정보 조회 API 확장 (로고, 상세정보 포함)
- [ ] 재무 지표 조회 API 구현 (`/companies/{ticker}/financials/`)
- [ ] 보고서 목록 조회 API 구현 (`/companies/{ticker}/reports/`)
- [ ] Serializer 작성

### Day 4: Celery 작업 및 테스트
- [ ] DART 데이터 동기화 Celery Task 구현
- [ ] 주기적 동기화 스케줄 설정 (일 1회)
- [ ] API 테스트 및 Swagger 문서화
- [ ] 에러 핸들링 및 로깅

---

## 11. 고려 사항

### 11.1 DART API 제약 사항
- **일일 호출 한도**: 10,000건/일 (추가 요청 시 확장 가능)
- **corp_code 필요**: 종목코드(stock_code)와 DART 고유번호(corp_code)는 다름
  - 최초 전체 기업 고유번호 목록을 다운로드하여 매핑 테이블 구축 필요
  - 엔드포인트: `GET /api/corpCode.xml` (ZIP 파일)

### 11.2 로고 URL 처리
DART API에서 로고를 제공하지 않으므로 다음 대안을 검토:
1. 기업 홈페이지에서 크롤링 (Jina.ai 활용)
2. 외부 금융 데이터 제공 서비스 활용 (예: Clearbit Logo API)
3. 수동으로 주요 기업 로고 등록

### 11.3 산업 코드 매핑
- DART는 "업종코드"를 제공 (예: "264", "265")
- 현재 `Industry` 모델과 매핑 필요
- 매핑 테이블 또는 변환 로직 구현 필요

### 11.4 종목코드 ↔ DART 고유번호 매핑

DART API는 `corp_code`(8자리 고유번호)를 사용하지만, 우리 시스템은 `stock_code`(6자리 종목코드)를 사용합니다.

**매핑 방법**:
1. DART의 `corpCode.xml` (전체 기업 목록) 다운로드
2. 종목코드 보유 기업만 필터링하여 매핑 테이블 구축
3. Company 모델의 `corp_code` 필드에 저장

```python
# companies/management/commands/sync_corp_codes.py
# 고유번호 목록 동기화 커맨드 구현 필요
```

---

## 12. 파일 변경 요약

| 파일 | 변경 내용 |
|------|----------|
| `.env` | `DART_API_KEY` 추가 |
| `config/settings.py` | DART API 설정 추가, Celery Beat 스케줄 추가 |
| `requirements.txt` | `xmltodict` 추가 |
| `companies/models.py` | Company 필드 추가, 신규 모델 3개 |
| `companies/services/` | DART API 서비스 모듈 신규 생성 |
| `companies/tasks/` | Celery 동기화 작업 신규 생성 |
| `companies/views.py` | 신규 API 엔드포인트 2개 추가 |
| `companies/serializers.py` | 신규 Serializer 5개 추가 |
| `companies/urls.py` | 신규 URL 패턴 2개 추가 |

---

## 13. 참고 자료

- [DART OpenAPI 공식 문서](https://opendart.fss.or.kr/intro/main.do)
- [DART OpenAPI 개발가이드](https://opendart.fss.or.kr/guide/main.do)
- [OpenDartReader (Python 라이브러리)](https://github.com/FinanceData/OpenDartReader)
- [PRD 문서 - 기업 정보 API 명세](../PRD.md#42-기업-api-companies)

---

**문서 버전 이력**

| 버전 | 날짜 | 작성자 | 변경 내용 |
|-----|-----|-------|----------|
| 1.0 | 2026-01-13 | Claude (AI Assistant) | 초기 문서 작성 |
