# API 문서

## 기본 엔드포인트

### Health Check API
- **URL**: `GET /health/`
- **설명**: 서버 상태 및 연결된 서비스(DB, Redis)의 상태를 확인합니다.
- **응답 예시**:
```json
{
  "status": "healthy",
  "database": "connected",
  "cache": "connected"
}
```

### Swagger UI (추천)
- **URL**: `http://localhost:8000/swagger/`
- **설명**: 인터랙티브 API 문서. 직접 API를 테스트할 수 있습니다.

### ReDoc
- **URL**: `http://localhost:8000/redoc/`
- **설명**: 읽기 편한 형식의 API 문서

### OpenAPI Schema (JSON)
- **URL**: `http://localhost:8000/api/schema/`
- **설명**: OpenAPI 3.0 스펙 JSON 파일

---

## 사용자 API (Users)

### 회원가입
- **URL**: `POST /api/users/signup/`
- **설명**: 새로운 사용자를 등록합니다.
- **Request Body**:
```json
{
  "username": "사용자명",
  "email": "user@example.com",
  "password": "비밀번호",
  "password2": "비밀번호 확인"
}
```
- **응답**: `201 Created`

### 로그인
- **URL**: `POST /api/users/login/`
- **설명**: 사용자 인증 후 JWT 토큰을 발급합니다.
- **Request Body**:
```json
{
  "email": "user@example.com",
  "password": "비밀번호"
}
```
- **응답 예시**:
```json
{
  "refresh": "리프레시 토큰",
  "access": "액세스 토큰",
  "email": "user@example.com",
  "username": "사용자명"
}
```

### 로그아웃
- **URL**: `POST /api/users/logout/`
- **설명**: 리프레시 토큰을 블랙리스트에 등록하여 로그아웃합니다.
- **인증**: 필요 (Bearer Token)
- **Request Body**:
```json
{
  "refresh": "리프레시 토큰"
}
```
- **응답**: `205 Reset Content`

### 즐겨찾기 목록 조회
- **URL**: `GET /api/users/favorites/`
- **설명**: 사용자의 즐겨찾기 기업 목록을 조회합니다.
- **인증**: 필요 (Bearer Token)
- **응답 예시**:
```json
[
  {
    "favoriteId": 1,
    "companyId": "005930",
    "companyName": "삼성전자",
    "logoUrl": "https://example.com/logo.png"
  }
]
```

### 즐겨찾기 추가
- **URL**: `POST /api/users/favorites/`
- **설명**: 기업을 즐겨찾기에 추가합니다.
- **인증**: 필요 (Bearer Token)
- **Request Body**:
```json
{
  "companyId": "005930"
}
```
- **응답 예시**:
```json
{
  "status": 201,
  "message": "즐겨찾기 추가 성공",
  "data": {
    "favoriteId": 1,
    "companyId": "005930",
    "companyName": "삼성전자",
    "logoUrl": "https://example.com/logo.png"
  }
}
```

### 즐겨찾기 삭제
- **URL**: `DELETE /api/users/favorites/{id}/`
- **설명**: 즐겨찾기를 삭제합니다 (소프트 삭제).
- **인증**: 필요 (Bearer Token)
- **응답 예시**:
```json
{
  "status": 200,
  "message": "즐겨찾기 삭제 성공",
  "data": null
}
```

---

## 기업 API (Company)

### 기업 기본 정보 조회
- **URL**: `GET /api/companies/{stock_code}/`
- **설명**: 종목코드로 기업의 기본 정보를 조회합니다.
- **Path Parameters**:
  - `stock_code`: 조회할 기업의 종목코드 (예: 005930)
- **응답 예시**:
```json
{
  "status": 200,
  "message": "기업 정보 조회 성공",
  "data": {
    "stock_code": "005930",
    "corp_code": "00126380",
    "company_name": "삼성전자",
    "induty_code": "264",
    "industry": {
      "industry_id": 1,
      "name": "반도체",
      "induty_code": "264"
    },
    "description": "기업 설명",
    "logo_url": "https://example.com/logo.png",
    "market_amount": 500000000000000,
    "ceo_name": "한종희",
    "establishment_date": "1969-01-13",
    "homepage_url": "https://www.samsung.com",
    "address": "경기도 수원시 영통구 삼성로 129"
  }
}
```

### 기업 재무 지표 조회
- **URL**: `GET /api/companies/{stock_code}/financials/`
- **설명**: 종목코드로 기업의 재무 지표를 조회합니다.
- **Path Parameters**:
  - `stock_code`: 조회할 기업의 종목코드
- **Query Parameters**:
  - `year` (optional): 조회할 연도 (기본값: 최근 3년)
- **응답 예시**:
```json
{
  "status": 200,
  "message": "재무 지표 조회 성공",
  "data": {
    "stock_code": "005930",
    "company_name": "삼성전자",
    "market_amount": 500000000000000,
    "financial_statements": [
      {
        "fiscal_year": 2024,
        "report_type": "사업보고서",
        "revenue": 300000000000000,
        "operating_profit": 50000000000000,
        "net_income": 40000000000000,
        "total_assets": 450000000000000,
        "total_liabilities": 100000000000000,
        "total_equity": 350000000000000
      }
    ],
    "revenue_composition": [
      {
        "segment_name": "DS부문",
        "revenue": 100000000000000,
        "ratio": 33.3
      }
    ]
  }
}
```

### 기업 보고서 목록 조회
- **URL**: `GET /api/companies/{stock_code}/reports/`
- **설명**: 종목코드로 기업의 공시 보고서 목록을 조회합니다.
- **Path Parameters**:
  - `stock_code`: 조회할 기업의 종목코드
- **Query Parameters**:
  - `page` (optional): 페이지 번호 (기본값: 1)
  - `size` (optional): 페이지 크기 (기본값: 20, 최대: 100)
- **응답 예시**:
```json
{
  "status": 200,
  "message": "보고서 목록 조회 성공",
  "data": {
    "total_count": 50,
    "page": 1,
    "page_size": 20,
    "reports": [
      {
        "rcept_no": "20240101000001",
        "report_name": "사업보고서 (2024.12)",
        "report_type": "정기공시",
        "submitted_at": "2024-03-15T09:00:00Z",
        "report_url": "https://dart.fss.or.kr/..."
      }
    ]
  }
}
```

### DART 데이터 동기화 (관리자용)
- **URL**: `POST /api/companies/{stock_code}/sync/`
- **설명**: DART API에서 기업 정보, 재무제표, 보고서를 DB에 동기화합니다.
- **인증**: 필요 (Bearer Token)
- **Path Parameters**:
  - `stock_code`: 동기화할 기업의 종목코드
- **Query Parameters**:
  - `sync_info` (optional): 기업 기본 정보 동기화 여부 (기본값: true)
  - `sync_financials` (optional): 재무제표 동기화 여부 (기본값: false)
  - `sync_reports` (optional): 보고서 목록 동기화 여부 (기본값: false)
  - `year` (optional): 재무제표 동기화 시 조회할 연도 (기본값: 현재 연도)
  - `days` (optional): 보고서 동기화 시 조회할 기간 (일 단위, 기본값: 365)
  - `async` (optional): 비동기 실행 여부 (Celery 작업으로 실행, 기본값: false)
- **응답 예시**:
```json
{
  "status": 200,
  "message": "동기화 완료",
  "data": {
    "stock_code": "005930",
    "sync_info": true,
    "sync_financials": true,
    "sync_reports": false,
    "results": {
      "info": "기업 정보 동기화 완료",
      "financials": "2024년 재무제표 동기화 완료 (4개 보고서)"
    }
  }
}
```

### 보고서 처리 시작 (관리자용)
- **URL**: `POST /api/companies/{stock_code}/reports/process/`
- **설명**: 기업의 미처리 보고서를 일괄 처리합니다 (본문 추출, 정제, 구조화된 정보 추출, OpenSearch 적재).
- **인증**: 필요 (Bearer Token)
- **Path Parameters**:
  - `stock_code`: 처리할 기업의 종목코드
- **Query Parameters**:
  - `limit` (optional): 처리할 보고서 수 (기본값: 20, 최대: 100)
- **응답 예시**:
```json
{
  "status": 202,
  "message": "보고서 처리가 시작되었습니다.",
  "data": {
    "stock_code": "005930",
    "company_name": "삼성전자",
    "task_id": "abc123-def456",
    "limit": 20,
    "pending_count": 15
  }
}
```

### 기업 주가 데이터 조회
- **URL**: `GET /api/companies/{stock_code}/prices/`
- **설명**: 특정 종목의 OHLCV 주가 데이터를 조회합니다.
- **Path Parameters**:
  - `stock_code`: 종목코드 (6자리, 예: 005930)
- **Query Parameters**:
  - `interval` (optional): 시간 단위 (1m, 15m, 1h, 1d). 미지정 시 모든 interval 반환
- **응답 예시**:
```json
{
  "status": 200,
  "message": "주가 데이터 조회 성공",
  "data": {
    "1d": {
      "stock_code": "005930",
      "interval": "1d",
      "total_count": 365,
      "data": [
        {
          "bucket": "2024-01-15T00:00:00Z",
          "stock_code": "005930",
          "open": 75000.0,
          "high": 76000.0,
          "low": 74500.0,
          "close": 75500.0,
          "volume": 1000000,
          "amount": 75500000000.0,
          "trade_count": 5000,
          "source": "yfinance"
        }
      ]
    }
  }
}
```

### 전체 기업 순위 조회
- **URL**: `GET /api/companies/rankings/companies/`
- **설명**: 최신 기준 날짜의 기업 순위 리스트를 가져옵니다.
- **응답 예시**:
```json
{
  "status": 200,
  "message": "전체 기업 순위 조회를 성공하였습니다.",
  "data": [
    {
      "rank": 1,
      "companyId": "005930",
      "name": "삼성전자",
      "logo": "https://example.com/logo.png",
      "amount": 500000000000000
    }
  ]
}
```

---

## 산업 API (Industry)

### 산업 내 기업 순위 조회
- **URL**: `GET /api/industries/{industry_id}/companies`
- **설명**: 특정 산업 ID를 입력받아 해당 산업에 속한 기업들의 순위를 조회합니다 (시가총액 기준).
- **Path Parameters**:
  - `industry_id`: 산업 ID
- **응답 예시**:
```json
{
  "status": 200,
  "message": "해당 산업 내 기업 순위 조회를 성공하였습니다.",
  "data": [
    {
      "stock_code": "005930",
      "company_name": "삼성전자",
      "description": "기업 설명",
      "rank": 1
    }
  ]
}
```

---

## 뉴스 API (News)

### 뉴스 목록 조회
- **URL**: `GET /api/news/`
- **설명**: 저장된 뉴스 목록을 조회합니다. 페이지네이션을 지원합니다.
- **Query Parameters**:
  - `page` (optional): 페이지 번호 (기본값: 1)
  - `page_size` (optional): 페이지당 항목 수 (기본값: 20, 최대: 100)
- **응답 예시**:
```json
{
  "total_count": 100,
  "total_pages": 5,
  "current_page": 1,
  "page_size": 20,
  "results": [
    {
      "news_id": 1,
      "title": "뉴스 제목",
      "url": "https://news.example.com/article/1",
      "summary": "뉴스 요약",
      "published_at": "2024-01-15T09:00:00Z",
      "created_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

### 뉴스 상세 조회
- **URL**: `GET /api/news/{news_id}/`
- **설명**: 특정 뉴스의 상세 정보를 조회합니다.
- **Path Parameters**:
  - `news_id`: 조회할 뉴스 ID
- **응답 예시**:
```json
{
  "news_id": 1,
  "title": "뉴스 제목",
  "url": "https://news.example.com/article/1",
  "summary": "뉴스 요약",
  "published_at": "2024-01-15T09:00:00Z",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

---

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

---

## 인증 방식

본 API는 JWT (JSON Web Token) 기반 인증을 사용합니다.

### 토큰 사용법

1. `/api/users/login/` 엔드포인트로 로그인하여 `access` 토큰과 `refresh` 토큰을 발급받습니다.
2. 인증이 필요한 API 호출 시 헤더에 `Authorization: Bearer {access_token}`을 포함합니다.
3. `access` 토큰이 만료되면 `refresh` 토큰을 사용하여 새로운 `access` 토큰을 발급받습니다.

### 인증이 필요한 API
- `POST /api/users/logout/`
- `GET /api/users/favorites/`
- `POST /api/users/favorites/`
- `DELETE /api/users/favorites/{id}/`
- `POST /api/companies/{stock_code}/sync/`
- `POST /api/companies/{stock_code}/reports/process/`
- `POST /api/core/admin/stocks/{stock_code}/sync-history/` (관리자 전용)
- `POST /api/core/admin/stocks/sync-history/` (관리자 전용)
- `POST /api/core/admin/stocks/sync-realtime/` (관리자 전용)

---

## 관리자 API (Admin)

### 주가 히스토리 동기화 (단일 종목)
- **URL**: `POST /api/core/admin/stocks/{stock_code}/sync-history/`
- **설명**: yfinance API를 통해 특정 종목의 과거 OHLCV 데이터를 동기화합니다.
- **인증**: 필요 (관리자 권한, Bearer Token)
- **Path Parameters**:
  - `stock_code`: 종목코드 (6자리, 예: 005930)
- **Query Parameters**:
  - `intervals` (optional): 동기화할 시간 단위 (콤마 구분: 1m,15m,1h,1d). 기본값: 전체
  - `async` (optional): 비동기 실행 여부. 기본값: true
- **수집 범위**:
  - 1분봉: 최근 1일
  - 15분봉: 최근 5일
  - 1시간봉: 최근 1달
  - 1일봉: 최근 1년
- **응답 예시** (비동기 실행):
```json
{
  "status": "accepted",
  "message": "동기화 작업이 시작되었습니다.",
  "data": {
    "task_id": "abc123-def456",
    "stock_code": "005930",
    "market": "KOSPI",
    "intervals": ["1m", "15m", "1h", "1d"]
  }
}
```

### 주가 히스토리 동기화 (여러 종목)
- **URL**: `POST /api/core/admin/stocks/sync-history/`
- **설명**: yfinance API를 통해 여러 종목의 과거 OHLCV 데이터를 동기화합니다.
- **인증**: 필요 (관리자 권한, Bearer Token)
- **Request Body**:
```json
{
  "stock_codes": ["005930", "000660", "035720"],
  "intervals": ["1d"]
}
```
- **응답 예시**:
```json
{
  "status": "accepted",
  "message": "3개 종목의 동기화 작업이 시작되었습니다.",
  "data": {
    "total_stocks": 3,
    "intervals": ["1d"],
    "tasks": [
      {"stock_code": "005930", "task_id": "task-001"},
      {"stock_code": "000660", "task_id": "task-002"},
      {"stock_code": "035720", "task_id": "task-003"}
    ]
  }
}
```

### 실시간 주가 데이터 동기화
- **URL**: `POST /api/core/admin/stocks/sync-realtime/`
- **설명**: Continuous Aggregate 데이터를 통합 테이블로 즉시 동기화합니다. 일반적으로 Celery Beat이 자동으로 실행하지만, 수동으로 실행할 때 사용합니다.
- **인증**: 필요 (관리자 권한, Bearer Token)
- **응답 예시**:
```json
{
  "status": "completed",
  "message": "실시간 데이터 동기화가 완료되었습니다.",
  "data": {
    "synced_count": 150,
    "timestamp": "2024-01-15T10:00:00Z"
  }
}
```

---

## 참고 자료

- [drf-spectacular 공식 문서](https://drf-spectacular.readthedocs.io/)
- [OpenAPI Specification](https://swagger.io/specification/)
