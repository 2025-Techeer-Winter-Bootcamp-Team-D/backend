# API 레퍼런스

이 문서는 프로젝트에 구현된 모든 API 엔드포인트, Management Commands, Scripts, Celery Tasks를 구조적으로 정리한 레퍼런스입니다.

## 목차

1. [API 엔드포인트](#api-엔드포인트)
2. [Management Commands](#management-commands)
3. [Scripts](#scripts)
4. [Celery Tasks](#celery-tasks)

---

## API 엔드포인트

### 기본 엔드포인트

#### Health Check
- **GET** `/health/`
  - 서버 상태 및 연결된 서비스(DB, Redis) 상태 확인
  - 인증: 불필요
  - 태그: `Health Check`

#### API 문서
- **GET** `/api/schema/` - OpenAPI 스키마
- **GET** `/swagger/` - Swagger UI
- **GET** `/redoc/` - ReDoc

---

### 사용자 API (`/api/users/`)

#### 인증
- **POST** `/api/users/signup/`
  - 회원가입
  - 인증: 불필요
  - 태그: `User`

- **POST** `/api/users/login/`
  - 로그인 (JWT 토큰 발급)
  - 인증: 불필요
  - 태그: `User`

- **POST** `/api/users/logout/`
  - 로그아웃 (Refresh 토큰 필요)
  - 인증: 필요
  - 태그: `User`

#### 즐겨찾기
- **GET** `/api/users/favorites/`
  - 즐겨찾기 목록 조회
  - 인증: 필요
  - 태그: `Favorite`

- **POST** `/api/users/favorites/`
  - 즐겨찾기 추가
  - 인증: 필요
  - 태그: `Favorite`

- **DELETE** `/api/users/favorites/{id}/`
  - 즐겨찾기 삭제 (소프트 삭제)
  - 인증: 필요
  - 태그: `Favorite`

---

### 기업 API (`/api/companies/`)

#### 기업 정보
- **GET** `/api/companies/{stock_code}/`
  - 기업 기본 정보 조회
  - 인증: 불필요
  - 태그: `Company`
  - 설명: 종목코드로 기업 정보 조회, 필수 정보가 없거나 오래된 경우 백그라운드로 동기화 실행

- **GET** `/api/companies/{stock_code}/financials/`
  - 기업 재무 지표 조회
  - 인증: 불필요
  - 태그: `Company`
  - 쿼리 파라미터: `year` (선택, 기본값: 최근 3년)

- **GET** `/api/companies/{stock_code}/prices/`
  - 기업 주가 데이터 조회 (OHLCV)
  - 인증: 불필요
  - 태그: `Company`
  - 쿼리 파라미터: `interval` (선택: 1m, 15m, 1h, 1d, 기본값: 전체)
  - 지원 시간 단위:
    - `1m`: 1분봉 - 최근 1일치 데이터
    - `15m`: 15분봉 - 최근 5일치 데이터
    - `1h`: 1시간봉 - 최근 1달치 데이터
    - `1d`: 1일봉 - 최근 1년치 데이터

#### 기업 보고서
- **GET** `/api/companies/{stock_code}/reports/`
  - 기업 보고서 목록 조회
  - 인증: 불필요
  - 태그: `Reports`
  - 쿼리 파라미터:
    - `type`: 보고서 유형 (선택)
    - `page`: 페이지 번호 (기본값: 1)
    - `size`: 페이지 크기 (기본값: 20, 최대: 100)

- **GET** `/api/companies/{stock_code}/reports/{rcept_no}/`
  - 보고서 분석 결과 조회
  - 인증: 불필요
  - 태그: `Reports`
  - 설명: 보고서의 분석 결과(요약, 매출 구성, 정제된 본문 등) 조회

#### 기업 뉴스
- **GET** `/api/companies/{stock_code}/news/`
  - 기업 뉴스 목록 조회
  - 인증: 불필요
  - 태그: `Company News`
  - 쿼리 파라미터:
    - `page`: 페이지 번호 (기본값: 1)
    - `page_size`: 페이지당 항목 수 (기본값: 20, 최대: 100)

- **GET** `/api/companies/{stock_code}/news/{news_id}/`
  - 기업 뉴스 상세 조회
  - 인증: 불필요
  - 태그: `Company News`

#### 기업 순위
- **GET** `/api/companies/rankings/companies/`
  - 전체 기업 순위 조회
  - 인증: 불필요
  - 태그: `Ranking`
  - 설명: 최신 기준 날짜의 기업 순위 리스트 조회

#### 기업 전망 분석
- **GET** `/api/companies/{stock_code}/outlook/`
  - 기업 전망 분석
  - 인증: 불필요
  - 태그: `Company`
  - 쿼리 파라미터:
    - `days_back`: 검색 기간 (일, 기본값: 30, 최대: 90)
    - `max_news`: 최대 뉴스 수 (기본값: 10, 최대: 20)
    - `max_reports`: 최대 보고서 수 (기본값: 5, 최대: 10)
  - 설명: 기업 뉴스와 공시 보고서를 분석하여 투자 전망, 상승 여력, 투자 신호 제공
  - 캐싱: 1시간 TTL

#### 관리자 전용 API
- **POST** `/api/companies/{stock_code}/sync/`
  - DART 데이터 동기화 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Company`
  - 쿼리 파라미터:
    - `sync_info`: 기업 기본 정보 동기화 여부 (기본값: true)
    - `sync_financials`: 재무제표 동기화 여부 (기본값: false)
    - `sync_reports`: 보고서 목록 동기화 여부 (기본값: false)
    - `year`: 재무제표 동기화 시 조회할 연도 (기본값: 현재 연도)
    - `days`: 보고서 동기화 시 조회할 기간 (일 단위, 기본값: 365)
    - `async`: 비동기 실행 여부 (기본값: false)

- **POST** `/api/companies/sync/all/`
  - 전체 기업 DART 데이터 동기화 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Company`
  - 쿼리 파라미터: 위와 동일

- **POST** `/api/companies/{stock_code}/reports/process/`
  - 보고서 처리 시작 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Reports`
  - 쿼리 파라미터:
    - `limit`: 처리할 보고서 수 (기본값: 20, 최대: 100)

- **POST** `/api/companies/{stock_code}/reports/{rcept_no}/analyze/`
  - 특정 보고서 분석 시작 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Reports`
  - 쿼리 파라미터:
    - `async`: 비동기 실행 여부 (기본값: true)

- **POST** `/api/companies/{stock_code}/news/sync/`
  - 기업 뉴스 동기화 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Company News`
  - 쿼리 파라미터:
    - `max_articles`: 최대 크롤링 기사 수 (기본값: 10, 최대: 100)
    - `async`: 비동기 실행 여부 (기본값: true)

---

### 산업 API (`/api/industries/`)

#### 산업 정보
- **GET** `/api/industries/{industry_id}/companies`
  - 산업별 기업 순위 조회
  - 인증: 불필요
  - 태그: `Industry`

- **GET** `/api/industries/rankings/industries/`
  - 산업 순위 조회
  - 인증: 불필요
  - 태그: `Industry`

#### 산업 뉴스
- **GET** `/api/industries/{industry_id}/news/`
  - 산업 뉴스 조회
  - 인증: 불필요
  - 태그: `Industry`
  - 쿼리 파라미터:
    - `page`: 페이지 번호 (기본값: 1)
    - `page_size`: 페이지당 뉴스 수 (기본값: 20, 최대: 100)

#### 산업 전망 분석
- **GET** `/api/industries/{industry_id}/outlook/`
  - 산업 전망 분석
  - 인증: 불필요
  - 태그: `Industry`
  - 쿼리 파라미터:
    - `days_back`: 검색 기간 (일, 기본값: 30, 최대: 90)
    - `max_news`: 최대 뉴스 수 (기본값: 20, 최대: 50)
    - `max_reports`: 최대 보고서 수 (기본값: 10, 최대: 20)
    - `top_companies`: 보고서 수집 대상 상위 기업 수 (기본값: 10, 최대: 20)
  - 설명: 산업 관련 뉴스와 소속 기업 보고서를 분석하여 낙관/중립/비관 시나리오 제공
  - 캐싱: 1시간 TTL

---

### 뉴스 API (`/api/news/`)

- **GET** `/api/news/`
  - 뉴스 목록 조회
  - 인증: 불필요
  - 태그: `News`
  - 쿼리 파라미터:
    - `page`: 페이지 번호 (기본값: 1)
    - `page_size`: 페이지당 항목 수 (기본값: 20, 최대: 100)

- **GET** `/api/news/{news_id}/`
  - 뉴스 상세 조회
  - 인증: 불필요
  - 태그: `News`

---

### Core API (`/api/core/`)

#### Health Check
- **GET** `/api/core/health/`
  - 헬스 체크 (중복, 위의 `/health/`와 동일)

#### 주가 데이터 동기화 (관리자용)
- **POST** `/api/core/admin/stocks/{stock_code}/sync-history/`
  - 주가 히스토리 동기화 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Admin - Stock Data`
  - 쿼리 파라미터:
    - `intervals`: 동기화할 시간 단위 (콤마 구분: 1m,15m,1h,1d, 기본값: 전체)
    - `async`: 비동기 실행 여부 (기본값: true)
  - 설명: yfinance API를 통해 특정 종목의 과거 OHLCV 데이터를 동기화

- **POST** `/api/core/admin/stocks/sync-history/`
  - 여러 종목 주가 히스토리 동기화 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Admin - Stock Data`
  - 요청 본문:
    ```json
    {
        "stock_codes": ["005930", "000660", "035720"],
        "intervals": ["1d"]
    }
    ```

- **POST** `/api/core/admin/stocks/sync-realtime/`
  - Continuous Aggregate 수동 동기화 (관리자용)
  - 인증: 관리자 필요
  - 태그: `Admin - Stock Data`
  - 설명: Continuous Aggregate 데이터를 통합 테이블로 즉시 동기화

---

## Management Commands

### Companies 앱

#### `sync_corp_codes`
DART 고유번호 목록 동기화

**사용법:**
```bash
# 시가총액 상위 50개 기업만 동기화 (개발/테스트용, 권장)
python manage.py sync_corp_codes --top-companies --skip-industry-mapping

# 상위 N개 기업만 동기화
python manage.py sync_corp_codes --limit 100 --skip-industry-mapping

# 전체 동기화 (업종코드 조회 건너뛰기 - 빠른 동기화)
python manage.py sync_corp_codes --skip-industry-mapping

# 업종코드 포함 동기화 (느리지만 완전한 데이터)
python manage.py sync_corp_codes

# 기존 기업 업데이트
python manage.py sync_corp_codes --update-existing --skip-industry-mapping
```

**옵션:**
- `--top-companies`: 시가총액 상위 50개 기업만 동기화
- `--limit N`: 상위 N개 기업만 동기화
- `--skip-industry-mapping`: 업종코드 조회 건너뛰기 (빠른 동기화)
- `--update-existing`: 기존 기업 업데이트

**설명:** 상장기업(stock_code가 있는 기업)만 동기화합니다.

---

#### `sync_logo_urls`
기업 로고 URL 일괄 동기화

**사용법:**
```bash
python manage.py sync_logo_urls
python manage.py sync_logo_urls --overwrite
python manage.py sync_logo_urls --dry-run
```

**옵션:**
- `--overwrite`: 기존 logo_url이 있어도 덮어쓰기
- `--dry-run`: 실제 저장 없이 변경될 내용만 출력

**설명:** Logo.dev API를 활용하여 모든 기업의 logo_url 필드를 업데이트합니다.

---

#### `update_company_rankings`
시가총액 기준 기업 순위 계산 및 저장

**사용법:**
```bash
python manage.py update_company_rankings
```

**설명:** 시가총액(market_amount) 기준으로 기업 순위를 계산하여 `CompanyRanking` 테이블에 저장합니다.

---

### News 앱

#### `crawl_news`
뉴스 크롤링

**사용법:**
```bash
python manage.py crawl_news --keywords "AI" "반도체" --max-articles 10
python manage.py crawl_news --keywords "AI" --max-articles 5
```

**옵션:**
- `--keywords`: 검색할 키워드 리스트 (필수)
- `--max-articles`: 최대 크롤링 기사 수 (기본값: 10)

**설명:** 지정된 키워드로 뉴스를 크롤링하고 DB에 저장합니다.

---

### Core 앱

#### `subscribe_handler`
Redis Stream 구독하여 실시간 주가 데이터를 Django Channels로 전송

**사용법:**
```bash
python manage.py subscribe_handler
```

**설명:** Redis Stream(`stock:realtime`)을 구독하여 실시간 주가 데이터를 Django Channels로 전송합니다.

---

### Industries 앱

#### `seed_industries`
산업 데이터 초기화

**사용법:**
```bash
python manage.py seed_industries
python manage.py seed_industries --reset
```

**옵션:**
- `--reset`: 기존 산업 데이터를 삭제하고 새로 생성

**설명:** 한국표준산업분류(KSIC) 공식 코드를 사용하여 산업 데이터를 초기화합니다.

---

#### `update_industry_rankings`
산업별 시가총액 합계 기준 순위 계산 및 저장

**사용법:**
```bash
python manage.py update_industry_rankings
```

**설명:** 산업별 시가총액 합계를 계산하여 `IndustryRanking` 테이블에 저장합니다.

---

## Scripts

`scripts/` 디렉토리에 있는 테스트/유틸리티 스크립트들:

### 테스트 스크립트

- `test_dart_financial.py` - DART 재무제표 API 테스트
- `test_dart_response.py` - DART API 응답 테스트
- `test_jina_extraction.py` - Jina API 추출 테스트
- `test_opendartreader.py` - OpenDartReader 테스트
- `test_redis_pubsub.py` - Redis Pub/Sub 테스트
- `test_report_processing.py` - 보고서 처리 파이프라인 테스트
- `test_run_crawl_news.py` - 뉴스 크롤링 테스트

**사용법:**
```bash
python scripts/test_<script_name>.py
```

---

## Celery Tasks

### Companies 앱

#### DART 동기화 (`companies/tasks/dart_sync.py`)

- `sync_company_info_from_dart(stock_code: str)`
  - 기업 기본 정보 DART 동기화
  - 재시도: 3회 (DART API 오류 시 60초 후 재시도)
  - 설명: DART API에서 기업 기본 정보를 조회하여 Company 모델 업데이트

- `sync_financial_statements(stock_code: str, year: int)`
  - 재무제표 DART 동기화
  - 재시도: 3회
  - 설명: 지정된 연도의 재무제표를 DART API에서 조회하여 저장

- `sync_company_reports(stock_code: str, days: int)`
  - 기업 보고서 목록 DART 동기화
  - 재시도: 3회
  - 설명: 최근 N일간의 보고서 목록을 DART API에서 조회하여 저장

- `sync_all_companies_info_from_dart()`
  - 전체 기업 정보 동기화
  - 설명: DB에 있는 모든 기업의 정보를 동기화

- `sync_all_companies_financials_from_dart(year: int)`
  - 전체 기업 재무제표 동기화
  - 설명: 모든 기업의 지정된 연도 재무제표를 동기화

- `sync_all_companies_reports_from_dart(days: int)`
  - 전체 기업 보고서 동기화
  - 설명: 모든 기업의 최근 N일간 보고서를 동기화

---

#### 시가총액 갱신 (`companies/tasks/kis_market_amount.py`)

- `sync_market_amount(stock_code: str)`
  - 단건 시가총액 갱신
  - 재시도: 3회 (일시적 오류 시 30초 후 재시도)
  - 설명: KIS REST API를 통한 시가총액 갱신, 일시적 오류(네트워크, HTTP 5xx)는 재시도, 비일시적 오류(데이터 없음)는 재시도하지 않음

- `sync_all_market_amount()`
  - 전체 기업 시가총액 배치 갱신
  - 설명: 장 마감 후 Celery Beat에서 호출, API Rate Limit 대응을 위해 요청 간 0.6초 딜레이 적용

- `sync_all_market_amount_async()`
  - 전체 기업 시가총액 비동기 배치 갱신
  - 설명: 각 기업별로 별도 Celery task를 생성하여 병렬 처리, KIS API rate limit(초당 2회) 준수를 위해 countdown으로 스케줄링

---

#### 보고서 처리 (`companies/tasks/report_processing.py`)

- `process_company_reports(stock_code, limit)`
  - 기업의 미처리 보고서 일괄 처리
  - 재시도: 3회

- `process_single_report_pipeline(report_id)`
  - 단일 보고서 처리 파이프라인
  - 재시도: 3회

- `extract_report_content_task(report_id)`
  - 보고서 본문 추출
  - 재시도: 3회

- `refine_report_content_task(content)`
  - 보고서 본문 정제
  - 재시도: 3회

- `extract_report_info_task(refined_content)`
  - 보고서 구조화된 정보 추출
  - 재시도: 3회

- `create_report_embedding_task(report_id)`
  - 보고서 임베딩 생성
  - 재시도: 3회

- `save_report_to_opensearch_task(report_id)`
  - 보고서 OpenSearch 저장
  - 재시도: 3회

- `process_all_pending_reports()`
  - 모든 미처리 보고서 처리

- `process_reports_by_company(stock_code)`
  - 특정 기업의 미처리 보고서 처리

---

#### 순위 계산 (`companies/tasks/rankings.py`)

- `update_company_rankings()`
  - 기업 순위 계산 및 저장
  - 설명: 시가총액 기준으로 기업 순위를 계산

---

### News 앱

#### 뉴스 크롤링 (`news/tasks/company_news.py`)

- `crawl_company_news_task(stock_code, max_articles)`
  - 기업 뉴스 크롤링
  - 재시도: 3회

- `crawl_news_by_keywords(keywords, max_articles)`
  - 키워드 기반 뉴스 크롤링

- `crawl_all_companies_news(max_articles)`
  - 전체 기업 뉴스 크롤링

---

#### 뉴스 처리 (`news/tasks/processing.py`)

- `process_news_article(news_id)`
  - 뉴스 기사 처리 (본문 추출, 요약 등)
  - 재시도: 3회

- `batch_process_news(limit)`
  - 배치 뉴스 처리

---

#### 뉴스 저장 (`news/tasks/storage.py`)

- `save_news_to_database(news_data)`
  - 뉴스 데이터베이스 저장
  - 재시도: 3회

---

#### 뉴스 추출 (`news/tasks/extraction.py`)

- `extract_news_content(news_id)`
  - 뉴스 본문 추출
  - 재시도: 3회

- `extract_news_metadata(news_id)`
  - 뉴스 메타데이터 추출

---

#### 뉴스 임베딩 (`news/tasks/embedding.py`)

- `create_news_embedding(news_id)`
  - 뉴스 임베딩 생성
  - 재시도: 3회

- `batch_create_embeddings(limit)`
  - 배치 임베딩 생성

---

#### 뉴스 클러스터링 (`news/tasks/clustering.py`)

- `cluster_news_articles(limit)`
  - 뉴스 기사 클러스터링
  - 재시도: 3회

---

#### 뉴스 검색 (`news/tasks/search.py`)

- `search_news_articles(query, limit)`
  - 뉴스 기사 검색
  - 재시도: 3회

- `index_news_to_opensearch(news_id)`
  - 뉴스 OpenSearch 인덱싱

---

#### 뉴스 워크플로우 (`news/tasks/workflows.py`)

- `start_search_phase(keywords, max_articles_per_keyword, job_id)`
  - 검색 단계 시작: 키워드별 병렬 검색 후 추출 단계로 전달

- `start_extraction_phase(article_urls, job_id)`
  - 추출 단계 시작: 기사별 병렬 본문 추출 후 정제 단계로 전달

- `start_processing_phase(extracted_articles, job_id)`
  - 정제 단계 시작: 기사별 병렬 정제 및 요약 후 임베딩 단계로 전달

- `start_embedding_phase(processed_articles, job_id)`
  - 임베딩 단계 시작: 기사별 병렬 임베딩 생성 후 저장 단계로 전달

- `start_storage_phase(embedded_articles, job_id)`
  - 저장 단계 시작: PostgreSQL 저장 후 클러스터링 단계로 전달

- `start_clustering_phase(job_id)`
  - 클러스터링 단계 시작: 중복 제거 및 OpenSearch 저장

- `scheduled_crawl_news(keywords, max_articles)`
  - 스케줄된 뉴스 크롤링 (전체 파이프라인 실행)

- `full_news_pipeline(keywords, max_articles)`
  - 전체 뉴스 파이프라인 실행 (검색 → 추출 → 정제 → 임베딩 → 저장 → 클러스터링)

---

### Core 앱

#### 주가 데이터 동기화 (`core/tasks/yfinance_sync.py`)

- `sync_stock_history_task(stock_code: str, intervals: list[str] | None = None)`
  - 주가 히스토리 동기화
  - 재시도: 3회 (기본 재시도 딜레이: 60초)
  - 설명: yfinance API를 통해 과거 OHLCV 데이터 동기화, 시장 정보는 Company.market 필드에서 자동 조회
  - intervals: 동기화할 시간 단위 목록 (1m, 15m, 1h, 1d), None이면 전체

- `sync_multiple_stocks_task(stock_codes: list[str], intervals: list[str] | None = None)`
  - 여러 종목 히스토리 동기화
  - 설명: 여러 종목의 주가 히스토리를 병렬로 동기화

---

#### 실시간 주가 동기화 (`core/tasks/price_sync.py`)

- `sync_cagg_to_prices_1m()`
  - 1분봉 Continuous Aggregate → 통합 테이블 동기화
  - 재시도: 3회 (기본 재시도 딜레이: 30초)
  - 설명: 최근 10분간의 데이터를 동기화, 30초마다 실행 권장

- `sync_cagg_to_prices_15m()`
  - 15분봉 Continuous Aggregate → 통합 테이블 동기화
  - 재시도: 3회 (기본 재시도 딜레이: 60초)
  - 설명: 최근 1시간간의 데이터를 동기화

- `sync_cagg_to_prices_1h()`
  - 1시간봉 Continuous Aggregate → 통합 테이블 동기화
  - 재시도: 3회 (기본 재시도 딜레이: 120초)
  - 설명: 최근 6시간간의 데이터를 동기화

- `sync_cagg_to_prices_1d()`
  - 1일봉 Continuous Aggregate → 통합 테이블 동기화
  - 재시도: 3회 (기본 재시도 딜레이: 300초)
  - 설명: 최근 3일간의 데이터를 동기화

- `sync_all_prices()`
  - 모든 시간 단위 주가 데이터 동기화
  - 설명: 위의 모든 동기화 태스크를 순차 실행

---

## API 인증

### 인증 방식
- JWT (JSON Web Token) 기반 인증
- `rest_framework_simplejwt` 사용

### 인증이 필요한 엔드포인트
- 관리자 전용 API: `IsAdminUser` 권한 필요
- 사용자 전용 API: `IsAuthenticated` 권한 필요

### 인증이 불필요한 엔드포인트
- 공개 조회 API: `AllowAny` 권한
- Health Check, API 문서 등

---

## API 응답 형식

### 성공 응답
```json
{
    "status": 200,
    "message": "성공 메시지",
    "data": { ... }
}
```

### 에러 응답
```json
{
    "status": 400,
    "error": "에러 메시지"
}
```

---

## 참고 문서

- [API 명세서](./README_API.md) - 상세 API 명세
- [시스템 아키텍처](./SYSTEM_ARCHITECTURE.md) - 시스템 구조
- [PRD](./PRD.md) - 제품 요구사항 문서

---

**최종 업데이트:** 2026-01-18
