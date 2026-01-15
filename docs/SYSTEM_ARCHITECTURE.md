# 시스템 아키텍처 문서

## 목차
1. [시스템 개요](#시스템-개요)
2. [뉴스 크롤링 시스템](#뉴스-크롤링-시스템)
3. [DART API 기업 정보 시스템](#dart-api-기업-정보-시스템)
4. [KIS 실시간 주가 데이터 처리](#kis-실시간-주가-데이터-처리)
5. [인프라 구성](#인프라-구성)
6. [기술 스택](#기술-스택)
7. [트러블슈팅 가이드](#트러블슈팅-가이드)

---

## 시스템 개요

본 시스템은 세 가지 주요 기능을 제공합니다:

1. **뉴스 크롤링 및 분석**: 금융 뉴스를 자동으로 수집하고 AI로 분석하여 저장
2. **DART API 기업 정보**: 금융감독원 전자공시시스템(DART)을 통한 기업 개황, 재무제표, 공시보고서 수집
3. **실시간 주가 데이터 처리**: 한국투자증권(KIS) API를 통한 실시간 주가 데이터 수집 및 저장

### 핵심 특징
- **비동기 병렬 처리**: Celery를 활용한 대규모 데이터 병렬 처리
- **확장 가능한 아키텍처**: 마이크로서비스 기반 컨테이너 구조
- **AI 기반 분석**: Gemini AI를 활용한 본문 정제, 요약, 벡터 임베딩
- **고성능 검색**: OpenSearch를 활용한 벡터 유사도 검색
- **시계열 데이터 최적화**: TimescaleDB를 활용한 주가 데이터 저장

---

## 뉴스 크롤링 시스템

### 1. 전체 워크플로우

뉴스 크롤링은 **Celery Canvas**를 활용한 6단계 병렬 처리 파이프라인으로 구성되어 있습니다.

```
키워드 입력
    ↓
1️⃣ 검색 (Search)
    ↓ (병렬, group + chord)
2️⃣ 본문 추출 (Extraction)
    ↓ (병렬, group + chord)
3️⃣ 정제 + 요약 (Processing)
    ↓ (병렬, group + chord)
4️⃣ 임베딩 생성 (Embedding)
    ↓ (병렬, group + chord)
5️⃣ PostgreSQL 저장 (Storage)
    ↓ (순차, chain)
6️⃣ 클러스터링 + OpenSearch 저장 (Clustering)
    ↓
완료
```

### 2. 단계별 상세 설명

#### 1️⃣ 검색 단계 (Search Phase)
**파일**: `news/tasks/search.py`

- **API**: Naver News Search API
- **처리 방식**: 키워드별 병렬 검색 (Celery group)
- **중복 제거**: URL 기준 중복 검색 결과 자동 제거
- **반환 데이터**: `title`, `link`, `description`, `published_at`

```python
# 단일 키워드 검색 태스크 (병렬 실행)
@shared_task(bind=True, max_retries=3)
def search_single_keyword_task(self, keyword: str, max_articles_per_keyword: int = 10)

# 검색 결과 집계 (chord callback)
@shared_task
def aggregate_search_results(results: List[List[Dict[str, Any]]])
```

**기술적 특징**:
- 최대 3회 재시도 (exponential backoff: 2^n초)
- 타임아웃: 5초
- 정렬 방식: 날짜순 (`sort=date`)

---

#### 2️⃣ 본문 추출 단계 (Extraction Phase)
**파일**: `news/tasks/extraction.py`, `news/services/jina_api.py`

- **API**: Jina.ai Reader API (https://r.jina.ai/)
- **처리 방식**: 기사별 병렬 본문 추출 (Celery group)
- **중복 체크**: DB에 이미 존재하는 URL은 건너뜀
- **출력 형식**: Markdown 형식의 본문 (`raw_content`)

```python
# 단일 기사 본문 추출 (병렬 실행)
@shared_task(bind=True, max_retries=3)
def extract_single_article_task(self, article: Dict[str, Any])

# 추출 결과 집계 및 실패 항목 필터링
@shared_task
def aggregate_extraction_results(results: List[Dict[str, Any] | None])
```

**Jina Reader 특징**:
- 자동 HTML 정리 및 Markdown 변환
- 이미지 alt 텍스트 포함 옵션
- 타임아웃: 30초 (뉴스 사이트 로딩 시간 고려)
- 최소 본문 길이: 100자

---

#### 3️⃣ 정제 + 요약 단계 (Processing Phase)
**파일**: `news/tasks/processing.py`, `news/services/refiner.py`, `news/services/summarizer.py`

##### 정제 (Refinement)
- **AI 모델**: Gemini 2.5 Flash Lite
- **목적**: Markdown 메타데이터 제거, HTML 태그 제거, 광고/메뉴 제거
- **처리 흐름**:
  1. Markdown 메타데이터 분리 ("Markdown Content:" 이후 내용만 추출)
  2. HTML 태그 정규식 제거
  3. 이미지 참조 텍스트 제거 (예: "Image 2: 로그인")
  4. Gemini AI 2차 정제 (프롬프트 인젝션 방지 적용)

**프롬프트 인젝션 방지**:
```python
prompt = """당신은 데이터 정제 전문가입니다...
=== 입력 데이터 시작 ===
{input_text}
=== 입력 데이터 끝 ===
"""
```

##### 요약 (Summarization)
- **AI 모델**: Gemini 2.5 Flash Lite
- **출력 형식**: JSON (`{"summary": "3줄 이내 요약"}`)
- **최대 입력 길이**: 50,000자
- **Safety Settings**: 유해 콘텐츠 차단 (BLOCK_MEDIUM_AND_ABOVE)

```python
# 단일 기사 정제 + 요약 (병렬 실행)
@shared_task(bind=True, max_retries=3)
def refine_and_summarize_single_article_task(self, article: Dict[str, Any])
```

**품질 보장**:
- 정제된 본문 최소 길이: 30자
- AI API 실패 시 로컬 정제본 사용 (fallback)
- 쿼터 초과 시 자동 로컬 정제본 반환

---

#### 4️⃣ 임베딩 생성 단계 (Embedding Phase)
**파일**: `news/tasks/embedding.py`, `news/services/embedding.py`

- **AI 모델**: Gemini text-embedding-004
- **벡터 차원**: 768차원
- **Task Type**: RETRIEVAL_DOCUMENT
- **처리 방식**: 기사별 병렬 임베딩 생성

```python
# 단일 기사 임베딩 생성 (병렬 실행)
@shared_task(bind=True, max_retries=3)
def create_single_embedding_task(self, article: Dict[str, Any])

# EmbeddingService 사용
embedding_service = EmbeddingService()
result = embedding_service.get_embeddings_batch([refined_content])
```

**기술적 특징**:
- 배치 처리 지원 (내부적으로 반복문 사용)
- 쿼터 초과 시 자동 스킵 (None 반환)
- 다국어 지원

---

#### 5️⃣ PostgreSQL 저장 단계 (Storage Phase)
**파일**: `news/tasks/storage.py`

- **저장 항목**: 메타데이터만 저장
  - `title`: 뉴스 제목
  - `url`: 원본 링크 (UNIQUE 제약)
  - `summary`: AI 생성 요약문
  - `published_at`: 발행일

- **저장하지 않는 항목**:
  - `embedding`: 벡터 임베딩 (OpenSearch에 저장)
  - `refined_content`: 정제된 본문 (OpenSearch에 저장)

```python
# 순차 저장 (chain)
@shared_task(bind=True, max_retries=3)
def save_to_db_task(self, articles: List[Dict[str, Any]])

# Django ORM 사용
news, created = News.objects.get_or_create(
    url=url,
    defaults={
        "title": article.get("title", ""),
        "summary": article.get("summary", ""),
        "published_at": article.get("published_at"),
    },
)
```

**소프트 삭제**:
- `is_deleted=False`로 복구 가능
- 중복 URL 발견 시 기존 뉴스 업데이트

---

#### 6️⃣ 클러스터링 + OpenSearch 저장 단계 (Clustering Phase)
**파일**: `news/tasks/clustering.py`, `news/utils/clustering.py`

##### DBSCAN 클러스터링
- **알고리즘**: DBSCAN (Density-Based Spatial Clustering)
- **파라미터**:
  - `eps=0.1`: 이웃 거리 임계값
  - `min_samples=2`: 클러스터 형성을 위한 최소 샘플 수
- **목적**: 유사 뉴스 자동 탐지 및 중복 제거

##### 중복 제거 전략
- **전략**: `latest_longest` (최신 + 최장 기사 선택)
- **우선순위**:
  1. 발행일이 최신인 기사
  2. 본문 길이가 긴 기사

##### OpenSearch 저장
- **저장 항목**:
  - `news_id`: PostgreSQL 참조 키
  - `title`: 제목
  - `content`: 정제된 본문 (`refined_content`)
  - `content_vector`: 768차원 벡터 임베딩
  - `published_at`: 발행일

```python
# OpenSearch 인덱스 설정
"content_vector": {
    "type": "knn_vector",
    "dimension": 768,
    "method": {
        "name": "hnsw",  # Hierarchical Navigable Small World
        "space_type": "cosinesimil",  # 코사인 유사도
        "engine": "lucene",
        "parameters": {
            "ef_construction": 128,
            "m": 24,
        },
    },
}
```

**처리 결과**:
- 유지된 뉴스: OpenSearch에 저장
- 중복 뉴스: PostgreSQL에서 소프트 삭제 (`is_deleted=True`)

---

### 3. Celery Canvas 패턴

#### Group + Chord 패턴
병렬 처리 후 결과 집계에 사용:

```python
# 검색 단계 예시
search_group = group(
    search_single_keyword_task.s(keyword, max_articles_per_keyword)
    for keyword in keywords
)

workflow = chord(search_group)(
    aggregate_search_results.s() | start_extraction_phase.s(job_id)
)
```

#### Chain 패턴
순차 처리에 사용:

```python
# 저장 → 클러스터링
workflow = chain(
    save_to_db_task.s(articles),
    start_clustering_phase.s(job_id),
)
```

---

### 4. 실행 방법

#### 동기 실행 (테스트용)
```bash
python manage.py crawl_news --keywords "AI" "반도체" --max-articles 10
```

#### 비동기 실행 (프로덕션)
```bash
python manage.py crawl_news --keywords "AI" "반도체" --max-articles 10 --async
```

#### Celery Beat (스케줄링)
`config/celery.py`에 정의된 주기적 작업:
```python
app.conf.beat_schedule = {
    'crawl-news-every-hour': {
        'task': 'news.tasks.workflows.scheduled_crawl_news',
        'schedule': crontab(minute=0),  # 매 시간 0분
        'args': (['AI', '반도체', '삼성전자', 'SK하이닉스'], 10)
    },
}
```

---

### 5. 모니터링

#### Flower Dashboard
```
http://localhost:5555
```

- 태스크 진행 상황 실시간 확인
- 워커 상태 모니터링
- 태스크 성공/실패 통계

#### CrawlJob 모델
```python
from news.models import CrawlJob

# 최근 작업 조회
job = CrawlJob.objects.order_by('-created_at').first()
print(f"상태: {job.status}")
print(f"성공: {job.successful_articles}")
print(f"실패: {job.failed_articles}")
```

---

## DART API 기업 정보 시스템

### 1. 시스템 개요

DART (Data Analysis, Retrieval and Transfer System)는 금융감독원 전자공시시스템입니다. 본 시스템은 DART OpenAPI를 활용하여 상장기업의 기본 정보, 재무제표, 공시보고서를 자동으로 수집하고 관리합니다.

#### 주요 기능
1. **기업 고유번호 동기화**: 전체 상장기업 목록 및 DART 고유번호 수집
2. **기업 개황 조회**: 기업명, 대표자, 설립일, 홈페이지, 주소, 업종코드 등
3. **재무제표 수집**: 매출액, 영업이익, 당기순이익, 자산, 부채, 자본 등
4. **공시보고서 목록**: 정기공시, 주요사항보고, 발행공시 등 다양한 보고서 정보

---

### 2. 데이터 모델

#### Company (기업)
```python
class Company(models.Model):
    stock_code = models.CharField(primary_key=True, max_length=6)  # 종목코드
    corp_code = models.CharField(max_length=8, unique=True)  # DART 고유번호
    company_name = models.CharField(max_length=255)  # 기업명
    induty_code = models.CharField(max_length=20)  # 업종코드
    
    # DART 기업개황 필드
    ceo_name = models.CharField(max_length=100)  # 대표자명
    establishment_date = models.DateField()  # 설립일
    homepage_url = models.URLField()  # 홈페이지
    address = models.TextField()  # 본사 주소
    
    market_amount = models.BigIntegerField()  # 시가총액
    description = models.TextField()  # 기업 설명
    logo_url = models.URLField()  # 로고 URL
```

#### FinancialStatement (재무제표)
```python
class FinancialStatement(models.Model):
    company = models.ForeignKey(Company)
    fiscal_year = models.IntegerField()  # 사업연도 (예: 2024)
    report_code = models.CharField(max_length=5)  # 보고서 코드
    
    # 주요 재무 지표 (단위: 원)
    revenue = models.BigIntegerField()  # 매출액
    operating_profit = models.BigIntegerField()  # 영업이익
    net_income = models.BigIntegerField()  # 당기순이익
    total_assets = models.BigIntegerField()  # 총자산
    total_liabilities = models.BigIntegerField()  # 총부채
    total_equity = models.BigIntegerField()  # 총자본
```

**보고서 코드**:
- `11011`: 사업보고서 (연간)
- `11012`: 반기보고서
- `11013`: 1분기보고서
- `11014`: 3분기보고서

#### Report (공시보고서)
```python
class Report(models.Model):
    company = models.ForeignKey(Company)
    rcept_no = models.CharField(max_length=20, unique=True)  # 접수번호
    report_name = models.CharField(max_length=500)  # 보고서명
    report_type = models.CharField(max_length=1)  # 공시유형
    submitted_at = models.DateField()  # 접수일자
    report_url = models.URLField()  # 보고서 URL
```

**공시유형**:
- `A`: 정기공시
- `B`: 주요사항보고
- `C`: 발행공시
- `D`: 지분공시
- `E`: 기타공시
- `F`: 외부감사관련
- `G`: 펀드공시
- `H`: 자산유동화
- `I`: 거래소공시
- `J`: 공정위공시

---

### 3. DART API 클라이언트

**파일**: `companies/services/dart_api.py`

#### 핵심 API 메서드

##### 1. 기업 고유번호 목록 다운로드
```python
def get_corp_code_list(self) -> bytes:
    """
    전체 기업 고유번호 목록 다운로드 (ZIP 파일)
    
    Returns:
        ZIP 파일의 바이너리 데이터
    """
    params = {"crtfc_key": self.api_key}
    url = f"{self.BASE_URL}/corpCode.xml"
    response = requests.get(url, params=params, timeout=60)
    return response.content
```

##### 2. 기업 개황 조회
```python
def get_company_info(self, corp_code: str) -> Dict[str, Any]:
    """
    기업개황 조회
    
    Returns:
        {
            'corp_name': '삼성전자',
            'ceo_nm': '한종희',
            'est_dt': '19690113',
            'hm_url': 'http://www.samsung.com',
            'adres': '경기도 수원시...',
            'induty_code': '264'
        }
    """
    return self._request("company.json", {"corp_code": corp_code})
```

##### 3. 재무제표 조회
```python
def get_financial_statements(
    self,
    corp_code: str,
    bsns_year: str,  # 사업연도 (예: "2024")
    reprt_code: str = "11011",  # 11011: 사업보고서
) -> Dict[str, Any]:
    """
    단일회사 전체 재무제표 조회
    
    Returns:
        {
            'list': [
                {
                    'account_nm': '매출액',
                    'account_id': 'ifrs-full_Revenue',
                    'thstrm_amount': '302231000000000'  # 당기금액
                },
                ...
            ]
        }
    """
    params = {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": "CFS",  # CFS: 연결재무제표, OFS: 개별재무제표
    }
    return self._request("fnlttSinglAcntAll.json", params)
```

##### 4. 공시보고서 목록 조회
```python
def get_disclosure_list(
    self,
    corp_code: str,
    bgn_de: Optional[str] = None,  # 시작일 (YYYYMMDD)
    end_de: Optional[str] = None,  # 종료일 (YYYYMMDD)
    pblntf_ty: Optional[str] = None,  # 공시유형 (A, B, C, ...)
    page_no: int = 1,
    page_count: int = 100,
) -> Dict[str, Any]:
    """
    공시검색 (보고서 목록 조회)
    
    Returns:
        {
            'list': [
                {
                    'rcept_no': '20240101000001',
                    'report_nm': '사업보고서 (2023.12)',
                    'pblntf_ty': 'A',
                    'rcept_dt': '20240101'
                },
                ...
            ]
        }
    """
```

#### 오류 처리
- **상태 코드 000**: 정상
- **상태 코드 013**: 조회된 데이터가 없습니다 (정상, 해당 보고서 없음)
- **기타 상태 코드**: DartAPIError 발생

---

### 4. 서비스 계층

#### CompanyInfoService (기업 개황)

**파일**: `companies/services/company_info.py`

```python
class CompanyInfoService:
    def sync_company_info(self, company: Company) -> Company:
        """
        DART API에서 기업 기본 정보를 조회하여 Company 모델 업데이트
        
        처리 항목:
        - 기업명 (corp_name)
        - 대표자명 (ceo_nm)
        - 설립일 (est_dt)
        - 홈페이지 (hm_url)
        - 주소 (adres)
        - 업종코드 (induty_code)
        """
        data = self.dart_client.get_company_info(company.corp_code)
        
        # 데이터 매핑
        if data.get("corp_name"):
            company.company_name = data["corp_name"]
        if data.get("ceo_nm"):
            company.ceo_name = data["ceo_nm"]
        # ... (나머지 필드)
        
        company.save()
        return company
```

---

#### FinancialService (재무제표)

**파일**: `companies/services/financial.py`

```python
class FinancialService:
    def sync_financial_statements(
        self,
        company: Company,
        year: int,
        sync_all_reports: bool = False,
    ) -> List[FinancialStatement]:
        """
        DART API에서 재무제표를 조회하여 FinancialStatement 모델에 저장
        
        Args:
            company: Company 인스턴스
            year: 사업연도 (예: 2024)
            sync_all_reports: 모든 보고서 조회 (11011, 11012, 11013, 11014)
        
        Returns:
            생성/업데이트된 FinancialStatement 인스턴스 리스트
        """
```

##### 재무 지표 추출 로직

DART API는 계정과목 리스트를 반환하므로, 주요 계정과목을 매핑해야 합니다:

```python
# 계정과목 코드 매핑
account_code_map = {
    "ifrs-full_Revenue": "revenue",  # 매출액
    "ifrs-full_ProfitLossFromOperatingActivities": "operating_profit",  # 영업이익
    "dart_OperatingIncomeLoss": "operating_profit",  # 영업이익 (DART 코드)
    "ifrs-full_ProfitLoss": "net_income",  # 당기순이익
    "ifrs-full_Assets": "total_assets",  # 총자산
    "ifrs-full_Liabilities": "total_liabilities",  # 총부채
    "ifrs-full_Equity": "total_equity",  # 총자본
}

for account in account_list:
    account_id = account.get("account_id")
    thstrm_amount = account.get("thstrm_amount")  # 당기금액
    
    if account_id in account_code_map:
        key = account_code_map[account_id]
        value = int(thstrm_amount)  # 문자열 → 정수 변환
        financial_data[key] = value
```

---

#### ReportsService (공시보고서)

**파일**: `companies/services/reports.py`

```python
class ReportsService:
    def sync_reports(
        self,
        company: Company,
        days: int = 365,
        incremental: bool = True,
        report_types: Optional[List[str]] = None,
    ) -> List[Report]:
        """
        DART API에서 보고서 목록을 조회하여 Report 모델에 저장
        
        Args:
            company: Company 인스턴스
            days: 조회할 기간 (일 단위)
            incremental: 증분 동기화 (마지막 동기화 이후 보고서만)
            report_types: 공시유형 필터 (기본값: ["A", "B"])
        
        Returns:
            생성/업데이트된 Report 인스턴스 리스트
        """
```

##### 증분 동기화

```python
# 마지막 동기화 날짜 확인
latest_report = (
    Report.objects.filter(company=company)
    .order_by("-submitted_at")
    .first()
)

if latest_report:
    start_date = latest_report.submitted_at  # 마지막 보고서 날짜 이후만
else:
    start_date = datetime.now().date() - timedelta(days=days)  # 전체 조회
```

##### 페이지네이션

```python
page_no = 1
page_count = 100

while True:
    data = self.dart_client.get_disclosure_list(
        company.corp_code,
        bgn_de=start_date.strftime("%Y%m%d"),
        end_de=end_date.strftime("%Y%m%d"),
        pblntf_ty=report_type,
        page_no=page_no,
        page_count=page_count,
    )
    
    report_list = data.get("list", [])
    if not report_list:
        break  # 더 이상 결과 없음
    
    # 보고서 저장 로직...
    
    # 다음 페이지 확인
    total_count = data.get("total_count", 0)
    if page_no * page_count >= total_count:
        break
    
    page_no += 1
```

---

### 5. Management Commands

#### sync_corp_codes (기업 고유번호 동기화)

**파일**: `companies/management/commands/sync_corp_codes.py`

##### 사용법
```bash
# 기본 실행 (빠른 동기화, 업종코드 건너뜀)
python manage.py sync_corp_codes --skip-industry-mapping

# 업종코드 포함 동기화 (느리지만 완전한 데이터)
python manage.py sync_corp_codes

# 기존 기업 업데이트
python manage.py sync_corp_codes --update-existing --skip-industry-mapping

# Dry Run (실제 저장하지 않음)
python manage.py sync_corp_codes --dry-run
```

##### 처리 흐름

```
1. DART API에서 ZIP 파일 다운로드
   └─ 전체 기업 고유번호 목록 (corpCode.xml)

2. ZIP에서 XML 추출
   └─ 약 10MB 크기의 XML 파일

3. XML 파싱 (코스피/코스닥 필터링)
   └─ 종목코드 범위: 000001~005999, 010000~099999
   └─ 비상장기업 자동 제외

4. Company 생성/업데이트
   └─ stock_code 기준으로 get_or_create
   └─ corp_code, company_name 저장
   └─ 옵션: 업종코드 조회 (개별 API 호출)
```

##### CorpCodeParser (XML 파서)

**파일**: `companies/services/corp_code_parser.py`

```python
class CorpCodeParser:
    @staticmethod
    def parse_corp_code_xml(xml_content: str) -> List[Dict[str, Any]]:
        """
        DART 고유번호 목록 XML을 파싱하여 코스피/코스닥 기업 정보 리스트 반환
        
        필터링 기준:
        - stock_code가 있는 기업만 (상장기업)
        - 종목코드 범위: 000001~005999 (코스피), 010000~099999 (코스닥)
        
        Returns:
            [
                {
                    'corp_code': '00126380',
                    'corp_name': '삼성전자',
                    'stock_code': '005930',
                    'modify_date': '20240101'
                },
                ...
            ]
        """
```

---

#### update_rankings (시가총액 순위)

**파일**: `companies/management/commands/update_rankings.py`

##### 사용법
```bash
# 시가총액 기준 순위 계산 및 저장
python manage.py update_rankings
```

##### 처리 로직
```python
# 1. market_amount 기준 내림차순 정렬
companies = Company.objects.filter(is_deleted=False).order_by('-market_amount')

# 2. 순위 생성
for index, company in enumerate(companies, start=1):
    CompanyRanking.objects.create(
        stock_code=company,
        rank=index,
        base_date=date.today()
    )
```

---

### 6. API 엔드포인트 (예시)

#### 기업 정보 조회
```
GET /api/companies/{stock_code}/
GET /api/companies/{stock_code}/info/
```

#### 재무제표 조회
```
GET /api/companies/{stock_code}/financials/?year=2024
GET /api/companies/{stock_code}/financials/?years=2022,2023,2024
```

#### 공시보고서 목록
```
GET /api/companies/{stock_code}/reports/?page=1&size=20
GET /api/companies/{stock_code}/reports/?report_type=A
```

---

### 7. 데이터 동기화 전략

#### 초기 동기화
```bash
# 1. 기업 고유번호 동기화 (약 2,000개 기업)
python manage.py sync_corp_codes --skip-industry-mapping

# 2. 주요 기업 정보 동기화 (수동, API 호출 제한 고려)
# - 시가총액 상위 100개 기업 우선
# - Celery Task로 비동기 처리 권장

# 3. 재무제표 동기화 (최근 3년)
# - 사업보고서(11011)만 수집
# - Celery Task로 비동기 처리 권장

# 4. 공시보고서 동기화 (최근 1년)
# - 정기공시(A) + 주요사항보고(B)만 수집
# - 증분 동기화 활용
```

#### 정기 업데이트
```bash
# 매일: 공시보고서 증분 동기화
python manage.py sync_reports --incremental

# 분기별: 재무제표 동기화
python manage.py sync_financials --year=2024

# 연간: 기업 고유번호 전체 동기화
python manage.py sync_corp_codes --update-existing
```

---

### 8. 주의사항 및 Best Practices

#### API 호출 제한
- **DART API 제한**: 분당 1,000건 (공식 제한은 없으나 과도한 호출 시 차단 가능)
- **권장 사항**:
  - 배치 처리 시 딜레이 추가 (0.1~0.5초)
  - Celery Task로 비동기 처리
  - 증분 동기화 활용

#### 데이터 검증
```python
# 금액 문자열 → 정수 변환 시 예외 처리
try:
    if thstrm_amount and thstrm_amount != "":
        value = int(thstrm_amount)
        if value != 0:  # 0 값은 무시
            financial_data[key] = value
except (ValueError, TypeError) as e:
    logger.warning(f"Invalid amount format: {thstrm_amount}")
```

#### 업종코드 매핑
- DART 업종코드: KSIC (한국표준산업분류) 코드
- `industries/models.py`의 `Industry` 모델과 매핑 필요
- `IndustryMapper` 서비스 활용

---

### 9. 트러블슈팅

#### 1. DART API 응답 없음
**증상**: "조회된 데이타가 없습니다" (status: 013)

**해결**:
```python
# 정상 케이스: 해당 보고서가 없을 수 있음
if "013" in error_message or "조회된 데이타가 없습니다" in error_message:
    logger.debug("재무제표 데이터 없음 (정상)")
    continue
```

#### 2. XML 파싱 실패
**증상**: `BadZipFile` 또는 파싱 오류

**해결**:
```bash
# ZIP 파일 다운로드 재시도
python manage.py sync_corp_codes

# 수동 확인
curl "https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key=YOUR_API_KEY" -o corpCode.zip
unzip -t corpCode.zip
```

#### 3. 재무 지표 누락
**증상**: 특정 기업의 재무 지표가 None

**해결**:
```python
# DART API 응답 확인 (계정과목 코드가 다를 수 있음)
# test_dart_financial.py 스크립트 활용
python scripts/test_dart_financial.py --corp-code 00126380 --year 2023
```

---

## KIS 실시간 주가 데이터 처리

### 1. 아키텍처

KIS 실시간 주가 데이터 처리는 **Pub/Sub 패턴**을 활용한 3개의 독립적인 서비스로 구성됩니다:

```
KIS WebSocket API
       ↓
  kis-publisher (WebSocket → Redis Pub/Sub)
       ↓
  Redis Pub/Sub Channel: stock:realtime:{종목코드}
       ↓         ↘
persistence-worker   subscribe-handler (Django)
       ↓                    ↓
  TimescaleDB          Django Channels (WebSocket)
                            ↓
                       클라이언트
```

---

### 2. kis-publisher

**파일**: `kis-publisher/main.py`

#### 역할
- KIS WebSocket API 연결
- 종목 구독 관리
- 실시간 체결 데이터 파싱
- Redis Pub/Sub 발행

#### 핵심 기능

##### 종목 구독
```python
# 환경변수 설정
KIS_SYMBOL_LIMIT = 10  # 동시 구독 종목 수 제한
KIS_SUBSCRIPTION_DELAY = 0.5  # 구독 메시지 간 딜레이 (초)
KIS_BATCH_SIZE = 5  # 배치 크기
KIS_BATCH_DELAY = 1.0  # 배치 간 딜레이 (초)

# 구독할 종목 코드 로드
ALL_SYMBOLS = get_all_listed_symbols()  # companies_data.csv에서 로드
SUBSCRIBE_SYMBOLS = ALL_SYMBOLS[:MAX_SUBSCRIBE_SYMBOLS]
```

##### 데이터 파싱
KIS API 형식: `데이터구분|TR_ID|종목코드|데이터부`

```python
class KISParser:
    @staticmethod
    def parse_trade_data(raw_message: str) -> dict:
        parts = raw_message.split("|")
        body_parts = parts[3].split("^")
        
        return {
            "symbol": parts[2],  # KIS 내부 식별자
            "stock_code": body_parts[0],  # 실제 6자리 종목코드
            "time": body_parts[1],  # 체결시간 (HHMMSS)
            "price": int(body_parts[2]),  # 현재가
            "volume": int(body_parts[12]),  # 체결량
        }
```

##### Redis 발행
```python
# 채널 형식: stock:realtime:{종목코드}
channel = f"stock:realtime:{parsed_data['stock_code']}"
payload = json.dumps(parsed_data)
await redis_client.publish(channel, payload)
```

#### 재연결 로직
- 최대 재연결 시도: 10회 (환경변수 `KIS_MAX_RECONNECT`)
- Exponential backoff: 5초 → 10초 → 20초 → ... (최대 300초)
- APP_KEY 중복 사용 시 즉시 종료 (재시도 무의미)

#### 테스트 모드
```python
# 환경변수 설정
KIS_USE_TEST_MODE=true
KIS_TEST_WS_URL=ws://kis-mock-server:8080

# Mock 서버 사용 (kis-publisher/mock_server.py)
# 실제 KIS API 없이도 테스트 가능
```

---

### 3. persistence-worker

**파일**: `persistence-worker/main.py`

#### 역할
- Redis Pub/Sub 구독 (`stock:realtime:*` 패턴)
- 메모리 버퍼링 (배치 처리)
- TimescaleDB 대량 저장 (COPY 명령 사용)

#### 핵심 기능

##### 버퍼링 전략
```python
class PersistenceWorker:
    def __init__(self):
        self.buffer = []
        self.batch_size = 200  # 배치 크기
        self.flush_interval = 5  # 5초마다 자동 플러시
```

##### 시간 파싱
```python
def parse_time(self, time_str: str) -> datetime:
    """HHMMSS 형식을 datetime으로 변환"""
    today = datetime.now().date()
    hour = int(time_str[0:2])
    minute = int(time_str[2:4])
    second = int(time_str[4:6])
    return datetime(today.year, today.month, today.day, hour, minute, second)
```

##### TimescaleDB 저장
```python
# COPY 명령을 사용한 고성능 대량 삽입
await conn.copy_records_to_table(
    "stock_ticks",
    columns=("time", "symbol", "stock_code", "price", "volume"),
    records=records,
)
```

#### 성능 최적화
- **배치 삽입**: 200건씩 모아서 한 번에 저장
- **COPY 명령**: INSERT보다 10-100배 빠름
- **자동 플러시**: 5초마다 버퍼 비우기 (데이터 유실 방지)
- **비동기 I/O**: asyncpg를 활용한 비동기 데이터베이스 연결

---

### 4. subscribe-handler (Django)

**파일**: `core/management/commands/subscribe_handler.py`

#### 역할
- Redis Pub/Sub 구독 (Django 내부)
- 실시간 데이터 로깅
- (향후) Django Channels를 통한 WebSocket 전송

```python
# Redis 구독
pubsub = r.pubsub()
await pubsub.psubscribe("stock:realtime:*")

# 메시지 수신 및 처리
async for message in pubsub.listen():
    if message["type"] == "pmessage":
        data = json.loads(message["data"])
        symbol = data.get("symbol")
        price = data.get("price")
        
        # TODO: Django Channels를 통해 클라이언트에게 전송
        print(f"[{time}] {symbol} {price} {volume}")
```

---

### 5. StockTick 모델 (TimescaleDB)

**파일**: `core/models.py`

```python
class StockTick(models.Model):
    symbol = models.CharField(max_length=10)  # KIS 내부 식별자
    stock_code = models.CharField(max_length=10)  # 실제 종목코드
    time = models.DateTimeField()  # 체결시간
    price = models.DecimalField(max_digits=12, decimal_places=2)
    volume = models.BigIntegerField()
    
    class Meta:
        db_table = "stock_ticks"
        unique_together = [["symbol", "time"]]
        managed = False  # Hypertable은 RunSQL로 생성
```

#### TimescaleDB 마이그레이션
```python
# core/migrations/0001_initial.py
operations = [
    # 1. 테이블 생성 (복합 primary key)
    migrations.RunSQL("""
        CREATE TABLE stock_ticks (
            symbol VARCHAR(10) NOT NULL,
            stock_code VARCHAR(10),
            time TIMESTAMPTZ NOT NULL,
            price NUMERIC(12, 2) NOT NULL,
            volume BIGINT NOT NULL,
            PRIMARY KEY (symbol, time)
        );
    """),
    
    # 2. Hypertable 변환 (시계열 최적화)
    migrations.RunSQL("""
        SELECT create_hypertable('stock_ticks', 'time');
    """),
]
```

#### Hypertable 특징
- **자동 파티셔닝**: `time` 컬럼 기준으로 chunk 분할
- **압축**: 오래된 데이터 자동 압축
- **빠른 시계열 쿼리**: `time_bucket()` 등 시계열 함수 제공

---

### 6. 데이터 흐름

```
1. KIS WebSocket 연결
   └─ kis-publisher가 실시간 체결 데이터 수신

2. 데이터 파싱
   └─ KISParser가 "0|H0STCNT0|001|^005930^153000^..." 형식 파싱

3. Redis 발행
   └─ 채널: stock:realtime:005930
   └─ 페이로드: {"symbol": "001", "stock_code": "005930", "time": "153000", "price": 75000, "volume": 100}

4-A. persistence-worker 구독
   └─ 메모리 버퍼에 적재 (200건 또는 5초)
   └─ TimescaleDB에 COPY 명령으로 대량 삽입

4-B. subscribe-handler 구독
   └─ Django에서 실시간 데이터 수신
   └─ (향후) Django Channels를 통해 WebSocket 전송
```

---

### 7. 실행 방법

#### kis-publisher 실행
```bash
# Docker Compose
docker-compose up -d kis-publisher

# 로컬 실행
cd kis-publisher
python main.py
```

#### persistence-worker 실행
```bash
# Docker Compose
docker-compose up -d persistence-worker

# 로컬 실행
cd persistence-worker
python main.py
```

#### subscribe-handler 실행
```bash
# Django Management Command
python manage.py subscribe_handler
```

---

## 인프라 구성

### Docker Compose 서비스

#### 1. 데이터베이스 (db)
- **이미지**: `timescale/timescaledb:latest-pg16`
- **포트**: 5432
- **볼륨**: `postgres_data`
- **Healthcheck**: `pg_isready`

#### 2. 캐시/메시지 브로커 (redis)
- **이미지**: `redis:7-alpine`
- **포트**: 6379
- **볼륨**: `redis_data`
- **Healthcheck**: `redis-cli ping`

#### 3. 벡터 검색 엔진 (opensearch)
- **이미지**: `opensearchproject/opensearch:latest`
- **포트**: 9200 (REST API), 9600 (Performance Analyzer)
- **볼륨**: `opensearch_data`
- **메모리**: 512MB (Xms512m, Xmx512m)
- **모드**: single-node
- **보안**: 비활성화 (개발 환경)

#### 4. Django 애플리케이션 (app)
- **빌드**: Dockerfile
- **포트**: 8000
- **의존성**: db, redis, opensearch

#### 5. Celery Worker (celery-worker)
- **명령**: `celery -A config worker --loglevel=info`
- **의존성**: db, redis, opensearch
- **재시작**: always

#### 6. Celery Beat (celery-beat)
- **명령**: `celery -A config beat --loglevel=info`
- **의존성**: db, redis
- **재시작**: always

#### 7. Flower (flower)
- **명령**: `celery -A config flower --port=5555`
- **포트**: 5555
- **의존성**: redis, celery-worker

#### 8. KIS Publisher (kis-publisher)
- **빌드**: kis-publisher/Dockerfile
- **의존성**: redis, kis-mock-server
- **재시작**: on-failure (최대 3회)

#### 9. KIS Mock Server (kis-mock-server)
- **빌드**: kis-publisher/Dockerfile
- **명령**: `python mock_server.py`
- **포트**: 8080
- **목적**: 테스트용 WebSocket 서버

#### 10. Persistence Worker (persistence-worker)
- **빌드**: persistence-worker/Dockerfile
- **의존성**: redis, db
- **재시작**: always

---

### 네트워크 구성

```
django-network (Bridge)
├── db (postgres-timescaledb)
├── redis
├── opensearch
├── app (django)
├── celery-worker
├── celery-beat
├── flower
├── kis-publisher
├── kis-mock-server
└── persistence-worker
```

---

## 기술 스택

### 백엔드
- **Django 5.x**: 웹 프레임워크
- **Celery**: 분산 태스크 큐
- **Redis**: 메시지 브로커 및 캐시
- **PostgreSQL 16 + TimescaleDB**: 메인 데이터베이스 및 시계열 DB
- **OpenSearch**: 벡터 유사도 검색

### AI/ML
- **Google Gemini 2.5 Flash Lite**: 본문 정제, 요약
- **Gemini text-embedding-004**: 768차원 벡터 임베딩
- **DBSCAN**: 뉴스 클러스터링 및 중복 제거

### 외부 API
- **Naver News Search API**: 뉴스 검색
- **Jina.ai Reader API**: 웹 페이지 본문 추출
- **DART OpenAPI**: 기업 개황, 재무제표, 공시보고서
- **KIS WebSocket API**: 실시간 주가 데이터

### 인프라
- **Docker & Docker Compose**: 컨테이너화
- **asyncio**: 비동기 I/O
- **asyncpg**: 비동기 PostgreSQL 클라이언트
- **websockets**: WebSocket 클라이언트

---

## 트러블슈팅 가이드

### 뉴스 크롤링 관련

#### 1. Gemini API 쿼터 초과
**증상**: "Gemini API 쿼터 초과" 로그 출력

**해결**:
```bash
# 로컬 정제본 사용 (AI 없이)
# - refiner.py와 summarizer.py가 자동으로 fallback
# - 품질은 떨어지지만 크롤링은 계속 진행됨

# API 쿼터 확인
# https://aistudio.google.com/apikeys

# 대안: 다른 API 키 사용
export GEMINI_API_KEY="your-new-api-key"
```

#### 2. Celery Worker 응답 없음
**증상**: 태스크가 pending 상태로 멈춤

**해결**:
```bash
# Celery Worker 재시작
docker-compose restart celery-worker

# Worker 로그 확인
docker-compose logs -f celery-worker

# Flower 대시보드 확인
# http://localhost:5555
```

#### 3. OpenSearch 연결 실패
**증상**: "Failed to connect to OpenSearch" 에러

**해결**:
```bash
# OpenSearch 상태 확인
curl -X GET "http://localhost:9200/_cluster/health?pretty"

# OpenSearch 재시작
docker-compose restart opensearch

# 인덱스 확인
curl -X GET "http://localhost:9200/news_vectors/_search?pretty"
```

---

### KIS 실시간 주가 관련

#### 1. APP_KEY 중복 사용
**증상**: "APP_KEY already in use" 에러

**해결**:
```bash
# KIS API는 동일 APP_KEY로 동시 접속 불가
# 1. 기존 연결 종료 대기 (30초~1분)
# 2. 다른 APP_KEY 사용
# 3. 테스트 모드 사용

# 테스트 모드 활성화
docker-compose up -d kis-mock-server
# docker-compose.yml에 KIS_USE_TEST_MODE=true 설정됨
```

#### 2. persistence-worker 데이터 저장 안 됨
**증상**: Redis에는 메시지가 오지만 DB에 저장 안 됨

**해결**:
```bash
# persistence-worker 로그 확인
docker-compose logs -f persistence-worker

# Redis Pub/Sub 구독 테스트
docker-compose exec redis redis-cli
> PSUBSCRIBE stock:realtime:*

# TimescaleDB 확인
docker-compose exec db psql -U postgres -d postgres
postgres=# SELECT COUNT(*) FROM stock_ticks;
postgres=# SELECT * FROM stock_ticks ORDER BY time DESC LIMIT 10;
```

#### 3. WebSocket 연결 끊김
**증상**: "WebSocket connection closed" 반복

**해결**:
```bash
# 재연결 시도 횟수 증가
export KIS_MAX_RECONNECT=20

# 구독 딜레이 증가 (서버 부하 감소)
export KIS_SUBSCRIPTION_DELAY=1.0
export KIS_BATCH_DELAY=2.0

# 구독 종목 수 감소
export KIS_SYMBOL_LIMIT=5

# kis-publisher 재시작
docker-compose restart kis-publisher
```

---

### DART API 관련

#### 1. DART API 키 오류
**증상**: "DART_API_KEY가 설정되지 않았습니다" 에러

**해결**:
```bash
# .env 파일 확인
cat .env | grep DART_API_KEY

# API 키 설정
export DART_API_KEY="your-dart-api-key"

# DART API 키 발급
# https://opendart.fss.or.kr/
```

#### 2. 재무 지표 누락
**증상**: 특정 기업의 재무 지표가 None

**해결**:
```bash
# DART API 응답 직접 확인
python scripts/test_dart_financial.py --corp-code 00126380 --year 2023

# 계정과목 코드가 다를 수 있음 (IFRS vs DART 코드)
# financial.py의 account_code_map 확인 및 수정 필요

# 해당 보고서가 없을 수도 있음 (status: 013)
# - 반기/분기 보고서는 없을 수 있음
# - 사업보고서(11011)만 조회 권장
```

#### 3. XML 파싱 실패
**증상**: `BadZipFile` 또는 파싱 오류

**해결**:
```bash
# ZIP 파일 수동 다운로드 및 확인
curl "https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key=YOUR_API_KEY" -o corpCode.zip
unzip -t corpCode.zip
unzip corpCode.zip
head -n 20 CORPCODE.xml

# 네트워크 문제일 수 있음 (재시도)
python manage.py sync_corp_codes

# API 키 오류 확인
# - 잘못된 키: "000: API 인증키가 유효하지 않습니다"
```

#### 4. 업종코드 조회 느림
**증상**: sync_corp_codes 실행 시 매우 느림 (2,000회 API 호출)

**해결**:
```bash
# --skip-industry-mapping 옵션 사용 (권장)
python manage.py sync_corp_codes --skip-industry-mapping

# 업종코드는 나중에 필요한 기업만 개별 업데이트
# - CompanyInfoService.sync_company_info() 사용
# - Celery Task로 비동기 처리
```

#### 5. 증분 동기화 실패
**증상**: 새로운 공시가 저장되지 않음

**해결**:
```bash
# 증분 동기화 확인
python manage.py sync_reports --incremental

# 로그 확인
# - "증분 동기화: 마지막 동기화 날짜 이후..." 메시지 확인
# - 날짜 범위 확인 (bgn_de, end_de)

# 전체 동기화 시도
python manage.py sync_reports --no-incremental --days 30
```

---

### 일반적인 문제

#### Redis 연결 실패
```bash
# Redis 상태 확인
docker-compose exec redis redis-cli ping

# Redis 재시작
docker-compose restart redis

# 연결 URL 확인
echo $REDIS_URL
```

#### PostgreSQL 연결 실패
```bash
# PostgreSQL 상태 확인
docker-compose exec db pg_isready -U postgres

# 연결 테스트
docker-compose exec db psql -U postgres -d postgres -c "SELECT version();"

# TimescaleDB 확장 확인
docker-compose exec db psql -U postgres -d postgres -c "\dx"
```

#### Docker Compose 전체 재시작
```bash
# 전체 서비스 재시작
docker-compose down
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

---

## 참고 자료

### 뉴스 크롤링
- [Celery Canvas 공식 문서](https://docs.celeryproject.org/en/stable/userguide/canvas.html)
- [Gemini API 문서](https://ai.google.dev/gemini-api/docs)
- [OpenSearch k-NN 문서](https://opensearch.org/docs/latest/search-plugins/knn/index/)
- [Jina Reader API](https://jina.ai/reader/)

### DART API 기업 정보
- [DART OpenAPI 공식 문서](https://opendart.fss.or.kr/guide/main.do)
- [DART API 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)
- [금융감독원 전자공시시스템](https://dart.fss.or.kr/)

### KIS 실시간 주가
- [한국투자증권 OpenAPI 문서](https://apiportal.koreainvestment.com/)
- [TimescaleDB 공식 문서](https://docs.timescale.com/)
- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)

---

## 버전 정보

- Django: 5.1
- Celery: 5.4.0
- Redis: 7.0
- PostgreSQL: 16 + TimescaleDB 2.16
- OpenSearch: 2.18
- Python: 3.12

---

## 라이선스

본 프로젝트는 내부 사용을 목적으로 합니다.

---

**작성일**: 2026-01-14  
**작성자**: System Documentation Bot
