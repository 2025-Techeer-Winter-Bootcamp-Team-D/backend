# 기업 보고서 처리 파이프라인 구현 계획

## 개요

DART API에서 기업 공시 보고서를 가져와서:
- **본문 추출**: OpenDartReader로 DART에서 직접 XML 본문 추출 (무료)
- **본문 정제**: Gemini로 불필요한 요소 제거
- **구조화된 정보 추출**: Gemini로 보고서 유형별 핵심 정보 + 매출 구성 **한 번에** 추출
- **벡터 임베딩**: Gemini Embedding으로 벡터 변환
- **OpenSearch 적재**: 벡터 검색을 위한 인덱스 저장

**핵심 기술:**
- Django 6.0 + DRF
- Celery (비동기 작업 처리)
- Redis (Message Broker)
- DART OpenAPI (보고서 목록 조회)
- **OpenDartReader** (보고서 본문 추출 - 무료)
- Gemini API (정제, 구조화된 정보 추출, 벡터 임베딩)
- OpenSearch (벡터 검색 엔진)
- PostgreSQL (메타데이터 저장)

**최적화:**
- 매출 구성 추출 + 요약을 **1회 Gemini 호출로 통합** → 비용 절감

## OpenDartReader 소개

OpenDartReader는 DART OpenAPI를 래핑한 파이썬 라이브러리로, 보고서 원문을 XML 형식으로 직접 가져올 수 있습니다.

### 설치
```bash
pip install opendartreader
```

### 주요 메서드
```python
import OpenDartReader

dart = OpenDartReader(api_key)

# 단일 보고서 원문 (XML)
xml_text = dart.document('20220816001711')  # rcept_no (접수번호)

# 첨부된 모든 보고서 원문 (XML 리스트)
xml_text_list = dart.document_all('20220816001711')
```

### Jina.ai 대비 장점
| 비교 항목 | OpenDartReader | Jina.ai |
|----------|----------------|---------|
| 비용 | **무료** (DART API) | 유료 or 제한 |
| 데이터 품질 | 원본 XML (구조화) | HTML→텍스트 변환 |
| 속도 | 직접 다운로드 | 웹 크롤링 |
| 안정성 | 공식 API | 사이트 구조 의존 |

## 비용 예측

### Gemini 2.5 Flash Lite 단가
- 입력: $0.10 / 1M tokens
- 출력: $0.40 / 1M tokens
- 임베딩: $0.15 / 1M tokens

### 보고서 1건당 예상 비용

| 단계 | 입력 토큰 | 출력 토큰 | 예상 비용 |
|------|----------|----------|----------|
| 본문 추출 (OpenDartReader) | - | - | **무료** |
| 본문 정제 | 10,000 | 10,000 | ~$0.0050 |
| 구조화된 정보 추출 (요약 + 매출구성 통합) | 10,000 | 800 | ~$0.0013 |
| 벡터 임베딩 | 10,000 | - | ~$0.0015 |
| **합계** | - | - | **~$0.0078** |

> **참고**: 
> - OpenDartReader를 사용하여 본문 추출 비용이 무료입니다.
> - 매출 구성 추출과 요약을 **1회 호출로 통합**하여 비용 절감 (~7% 절감)

### 규모별 예상 비용

| 규모 | 보고서 수 | 예상 비용 |
|------|----------|----------|
| 기업 100개 × 20건 | 2,000건 | ~$15.6 |
| 기업 500개 × 20건 | 10,000건 | ~$78 |
| 기업 1,000개 × 20건 | 20,000건 | ~$156 |
| 기업 2,000개 × 20건 | 40,000건 | ~$312 |

## 아키텍처

```
[스케줄러/API] → POST /companies/{stock_code}/sync/ (sync_reports=true)
                    ↓
              [Django API]
                    ↓
         [Report 모델에 보고서 목록 저장]
                    ↓
              [Celery Task: process_reports_task]
                    ↓
              [Redis Broker]
                    ↓
            [Celery Worker]
                    ↓
         [OpenDartReader] → [보고서 본문 추출 (XML → 텍스트)]
                    ↓
         [RefineService] → [본문 정제 (Gemini)]
                    ↓
              ┌─────┴─────┐
              ↓           ↓
    [구조화된 정보 추출]  [임베딩 생성]
    (요약 + 매출구성 통합)  (Gemini)
              ↓           ↓
    ┌─────────┴─────────┐ ↓
    ↓                   ↓ ↓
[RevenueComposition] [Report.extracted_info] [OpenSearch]
(PostgreSQL)         (PostgreSQL - JSON)   (벡터 인덱스)
```

**데이터 흐름:**
1. DART API로 보고서 목록 동기화 (기존 기능)
2. **OpenDartReader**로 보고서 원문 XML 직접 추출 (무료)
3. XML에서 텍스트 추출 후 Gemini로 본문 정제
4. **통합 추출 (1회 Gemini 호출)**:
   - 보고서 유형별 핵심 정보 추출 → Report.extracted_info (JSON)
   - 매출 구성 추출 → RevenueComposition 테이블
5. **임베딩 생성**: Gemini Embedding으로 벡터 변환 → OpenSearch

## 데이터 모델 변경

### Report 모델 수정 (companies/models.py)

```python
class Report(models.Model):
    """기업 공시 보고서"""
    
    # 기존 필드
    company = models.ForeignKey(Company, ...)
    rcept_no = models.CharField(max_length=20, unique=True)
    report_name = models.CharField(max_length=500)
    report_type = models.CharField(max_length=1, choices=REPORT_TYPE_CHOICES)
    submitted_at = models.DateField()
    report_url = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # 신규 필드
    raw_content = models.TextField(null=True, blank=True)  # OpenDartReader 추출 원본
    refined_content = models.TextField(null=True, blank=True)  # Gemini 정제 본문
    extracted_info = models.JSONField(null=True, blank=True)  # 구조화된 추출 정보 (요약 + 핵심정보)
    embedding = models.JSONField(null=True, blank=True)  # 벡터 임베딩 (768차원)
    processed_at = models.DateTimeField(null=True, blank=True)  # 처리 완료 시간
    processing_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', '대기'),
            ('processing', '처리중'),
            ('completed', '완료'),
            ('failed', '실패'),
        ],
        default='pending'
    )
```

### OpenSearch 인덱스 추가

```python
# news/services/opensearch.py 확장 또는 companies/services/opensearch.py 신규

REPORTS_INDEX_NAME = "report_vectors"

index_body = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100,
        }
    },
    "mappings": {
        "properties": {
            "report_id": {"type": "long"},
            "company_stock_code": {"type": "keyword"},
            "company_name": {"type": "text"},
            "report_name": {"type": "text"},
            "report_type": {"type": "keyword"},
            "content": {"type": "text"},
            "summary": {"type": "text"},
            "content_vector": {
                "type": "knn_vector",
                "dimension": 768,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                }
            },
            "submitted_at": {"type": "date"},
        }
    }
}
```

## 보고서 유형별 구조화된 추출 스키마

보고서 유형에 따라 다른 정보를 추출합니다. **매출 구성과 핵심 정보를 1회 Gemini 호출로 통합 추출**합니다.

### 추출 응답 형식 (JSON)

```json
{
  "report_type": "자기주식취득결정",
  "company_name": "삼성전자",
  "summary": {
    "title": "자기주식 취득 결정",
    "date": "2026-01-07",
    "one_line": "임직원 주식보상 목적으로 보통주 1,800만주(2.5조원) 취득 결정"
  },
  "key_info": {
    "취득예정주식": "보통주 18,000,000주",
    "취득예정금액": "2조 5,002억원",
    "취득기간": "2026.01.08 ~ 2026.04.07",
    "취득목적": "임직원 주식보상",
    "이사회결의일": "2026.01.07"
  },
  "revenue_composition": []
}
```

### 보고서 유형별 추출 필드

| 보고서 유형 | key_info 추출 필드 |
|------------|-------------------|
| **사업보고서 (A)** | 주요사업내용, 재무요약, 향후전망, 위험요소 |
| **자기주식취득결정** | 취득주식수, 금액, 기간, 목적, 결의일 |
| **타법인주식취득** | 투자대상, 투자금액, 투자목적, 투자기간, 결의일 |
| **유상증자결정** | 증자방식, 발행주식수, 발행가액, 자금사용목적 |
| **배당결정** | 배당종류, 배당금액, 배당기준일, 배당지급일 |
| **합병/분할** | 합병/분할 대상, 비율, 일정, 목적 |

### 사업보고서의 경우 매출 구성 포함

```json
{
  "report_type": "사업보고서",
  "company_name": "삼성전자",
  "summary": {
    "title": "2025년 사업보고서",
    "date": "2026-03-14",
    "one_line": "2025년 매출 302조원, 영업이익 36조원 달성"
  },
  "key_info": {
    "매출액": "302조원",
    "영업이익": "36조원",
    "당기순이익": "28조원",
    "주요사업": "반도체, 디스플레이, 모바일"
  },
  "revenue_composition": [
    {"segment": "DS부문(반도체)", "revenue": 136000000000000, "ratio": 45.0},
    {"segment": "DX부문(모바일/가전)", "revenue": 120000000000000, "ratio": 39.7},
    {"segment": "SDC(디스플레이)", "revenue": 32000000000000, "ratio": 10.6},
    {"segment": "기타", "revenue": 14000000000000, "ratio": 4.7}
  ]
}
```

## 구현 단계

### 1단계: 모델 마이그레이션

**companies/models.py 수정:**

```python
class Report(models.Model):
    # ... 기존 필드 ...
    
    # 신규 필드 추가
    raw_content = models.TextField(null=True, blank=True, verbose_name="원본 본문")
    refined_content = models.TextField(null=True, blank=True, verbose_name="정제된 본문")
    extracted_info = models.JSONField(null=True, blank=True, verbose_name="구조화된 추출 정보")
    embedding = models.JSONField(null=True, blank=True, verbose_name="벡터 임베딩")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="처리 완료 시간")
    processing_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', '대기'),
            ('processing', '처리중'),
            ('completed', '완료'),
            ('failed', '실패'),
        ],
        default='pending',
        verbose_name="처리 상태"
    )
```

마이그레이션:
```bash
python manage.py makemigrations companies
python manage.py migrate
```

### 2단계: 서비스 레이어 구현

#### 2-1. 보고서 본문 추출 서비스

**companies/services/report_extractor.py (신규)**

```python
"""
보고서 본문 추출 서비스
OpenDartReader를 사용하여 DART에서 직접 보고서 원문을 추출합니다.
"""
import OpenDartReader
from bs4 import BeautifulSoup
from django.conf import settings
import re
import logging

logger = logging.getLogger(__name__)


class ReportExtractorService:
    """보고서 본문 추출 서비스 (OpenDartReader 기반)"""
    
    def __init__(self):
        self.dart = OpenDartReader(settings.DART_API_KEY)
    
    def extract_content(self, rcept_no: str) -> str | None:
        """
        DART에서 보고서 본문 추출 (XML → 텍스트)
        
        Args:
            rcept_no: 보고서 접수번호 (예: '20220816001711')
            
        Returns:
            추출된 본문 텍스트 (실패 시 None)
        """
        try:
            # OpenDartReader로 XML 원문 가져오기
            xml_text = self.dart.document(rcept_no)
            
            if not xml_text:
                logger.warning(f"보고서 XML 가져오기 실패: {rcept_no}")
                return None
            
            # XML에서 텍스트 추출
            text = self._parse_xml_to_text(xml_text)
            
            if text and len(text.strip()) > 100:
                logger.info(f"보고서 본문 추출 성공: {rcept_no} - {len(text)}자")
                return text
            else:
                logger.warning(f"보고서 본문이 너무 짧음: {rcept_no}")
                return None
                
        except Exception as e:
            logger.error(f"보고서 본문 추출 실패: {rcept_no} - {e}")
            return None
    
    def extract_all_documents(self, rcept_no: str) -> list[str]:
        """
        첨부된 모든 보고서 본문 추출
        
        Args:
            rcept_no: 보고서 접수번호
            
        Returns:
            본문 텍스트 리스트
        """
        try:
            xml_text_list = self.dart.document_all(rcept_no)
            
            if not xml_text_list:
                return []
            
            texts = []
            for xml_text in xml_text_list:
                text = self._parse_xml_to_text(xml_text)
                if text and len(text.strip()) > 100:
                    texts.append(text)
            
            logger.info(f"보고서 전체 문서 추출: {rcept_no} - {len(texts)}개 문서")
            return texts
            
        except Exception as e:
            logger.error(f"보고서 전체 문서 추출 실패: {rcept_no} - {e}")
            return []
    
    def _parse_xml_to_text(self, xml_text: str) -> str:
        """
        XML 텍스트에서 본문 텍스트 추출
        
        Args:
            xml_text: XML 원문
            
        Returns:
            정제된 텍스트
        """
        try:
            # BeautifulSoup으로 XML 파싱
            soup = BeautifulSoup(xml_text, 'lxml-xml')
            
            # 모든 텍스트 추출 (태그 제거)
            text = soup.get_text(separator='\n', strip=True)
            
            # 연속된 공백/줄바꿈 정리
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r' {2,}', ' ', text)
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"XML 파싱 실패: {e}")
            return ""
```

#### 2-2. 통합 정보 추출 서비스 (요약 + 매출 구성)

**companies/services/report_info_extractor.py (신규)**

```python
"""
통합 정보 추출 서비스
Gemini를 사용하여 보고서에서 구조화된 핵심 정보와 매출 구성을 한 번에 추출합니다.
"""
from google import genai
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)


class ReportInfoExtractorService:
    """통합 정보 추출 서비스 (요약 + 매출 구성)"""
    
    def __init__(self):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash-lite"
    
    def extract_info(self, refined_content: str, report_name: str, company_name: str) -> dict:
        """
        정제된 본문에서 구조화된 정보와 매출 구성을 한 번에 추출
        
        Args:
            refined_content: 정제된 보고서 본문
            report_name: 보고서명 (유형 판단용)
            company_name: 기업명
            
        Returns:
            구조화된 추출 정보 (JSON)
        """
        # 입력 길이 제한
        max_input_length = 30000
        if len(refined_content) > max_input_length:
            refined_content = refined_content[:max_input_length]
        
        prompt = f"""다음 기업 보고서에서 핵심 정보를 구조화하여 추출하세요.

기업명: {company_name}
보고서명: {report_name}

요구사항:
1. 보고서 유형을 파악하고, 해당 유형에 맞는 핵심 정보를 추출
2. 한 줄 요약(one_line)은 50자 이내로 핵심만
3. key_info는 보고서 유형에 따라 다름:
   - 사업보고서: 매출액, 영업이익, 주요사업, 향후전망
   - 자기주식취득: 취득주식수, 금액, 기간, 목적
   - 타법인주식취득: 투자대상, 금액, 목적, 기간
   - 배당결정: 배당종류, 금액, 기준일
   - 기타: 변동내용, 일자, 금액 등 핵심사항
4. 매출 구성(revenue_composition)은 사업보고서에서만 추출, 없으면 빈 배열

응답 형식 (JSON만 출력):
{{
  "report_type": "보고서 유형명",
  "company_name": "{company_name}",
  "summary": {{
    "title": "보고서 제목",
    "date": "YYYY-MM-DD",
    "one_line": "50자 이내 한 줄 요약"
  }},
  "key_info": {{
    "항목1": "값1",
    "항목2": "값2"
  }},
  "revenue_composition": [
    {{"segment": "사업부문명", "revenue": 금액(원), "ratio": 비율}}
  ]
}}

=== 보고서 본문 시작 ===
{refined_content}
=== 보고서 본문 끝 ===

위 보고서의 핵심 정보를 JSON으로 응답하세요."""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            text = response.text.strip()
            
            # JSON 파싱
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_text = text[start:end]
                return json.loads(json_text)
            
            return {"error": "JSON 파싱 실패"}
        except Exception as e:
            logger.error(f"정보 추출 실패: {e}")
            return {"error": str(e)}
```

#### 2-3. OpenSearch 보고서 서비스

**companies/services/report_opensearch.py (신규)**

```python
"""
보고서 OpenSearch 서비스
보고서 벡터를 OpenSearch에 저장하고 검색합니다.
"""
from opensearchpy import OpenSearch, helpers
from django.conf import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ReportOpenSearchService:
    """보고서 OpenSearch 서비스"""
    
    REPORTS_INDEX_NAME = "report_vectors"
    VECTOR_DIMENSION = 768
    
    def __init__(self):
        host = settings.OPENSEARCH_HOST
        if ":" in host:
            host_parts = host.split(":")
            host_name = host_parts[0]
            port = int(host_parts[1])
        else:
            host_name = host
            port = 9200
        
        self.client = OpenSearch(
            hosts=[{"host": host_name, "port": port}],
            http_compress=True,
            use_ssl=settings.OPENSEARCH_USE_SSL,
            verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
            ssl_show_warn=False,
        )
        
        self._ensure_index_exists()
    
    def _ensure_index_exists(self):
        """인덱스가 없으면 생성"""
        if not self.client.indices.exists(index=self.REPORTS_INDEX_NAME):
            index_body = {
                "settings": {
                    "index": {
                        "knn": True,
                        "knn.algo_param.ef_search": 100,
                    }
                },
                "mappings": {
                    "properties": {
                        "report_id": {"type": "long"},
                        "company_stock_code": {"type": "keyword"},
                        "company_name": {"type": "text"},
                        "report_name": {"type": "text"},
                        "report_type": {"type": "keyword"},
                        "content": {"type": "text"},
                        "summary": {"type": "text"},
                        "content_vector": {
                            "type": "knn_vector",
                            "dimension": self.VECTOR_DIMENSION,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "lucene",
                                "parameters": {
                                    "ef_construction": 128,
                                    "m": 24,
                                },
                            },
                        },
                        "submitted_at": {"type": "date"},
                    }
                },
            }
            self.client.indices.create(index=self.REPORTS_INDEX_NAME, body=index_body)
            logger.info(f"Created index: {self.REPORTS_INDEX_NAME}")
    
    def save_report_vector(self, report_id, company_stock_code, company_name,
                           report_name, report_type, content, summary,
                           content_vector, submitted_at=None):
        """보고서 벡터 저장"""
        if not content_vector or len(content_vector) != self.VECTOR_DIMENSION:
            logger.error(f"Invalid vector dimension: {len(content_vector) if content_vector else 0}")
            return False
        
        doc = {
            "report_id": report_id,
            "company_stock_code": company_stock_code,
            "company_name": company_name,
            "report_name": report_name,
            "report_type": report_type,
            "content": content,
            "summary": summary,
            "content_vector": content_vector,
        }
        
        if submitted_at:
            doc["submitted_at"] = submitted_at.isoformat() if isinstance(submitted_at, datetime) else submitted_at
        
        try:
            response = self.client.index(
                index=self.REPORTS_INDEX_NAME,
                id=report_id,
                body=doc,
                refresh=True,
            )
            return response.get("result") in ["created", "updated"]
        except Exception as e:
            logger.error(f"Failed to save report vector: {e}")
            return False
    
    def search_similar_reports(self, query_vector, size=10, company_stock_code=None):
        """유사 보고서 검색"""
        if not query_vector or len(query_vector) != self.VECTOR_DIMENSION:
            return []
        
        query = {
            "size": size,
            "query": {
                "knn": {
                    "content_vector": {
                        "vector": query_vector,
                        "k": size,
                    }
                }
            },
            "_source": ["report_id", "company_stock_code", "company_name",
                       "report_name", "summary", "submitted_at"],
        }
        
        # 특정 기업 필터
        if company_stock_code:
            query["query"] = {
                "bool": {
                    "must": [{"knn": {"content_vector": {"vector": query_vector, "k": size}}}],
                    "filter": [{"term": {"company_stock_code": company_stock_code}}],
                }
            }
        
        try:
            response = self.client.search(index=self.REPORTS_INDEX_NAME, body=query)
            return [
                {**hit["_source"], "score": hit["_score"]}
                for hit in response.get("hits", {}).get("hits", [])
            ]
        except Exception as e:
            logger.error(f"Failed to search reports: {e}")
            return []
```

### 3단계: Celery 태스크 구현

**companies/tasks/report_processing.py (신규)**

```python
"""
보고서 처리 Celery 태스크
보고서 본문 추출, 정제, 요약, 매출 구성 추출, 임베딩 생성을 수행합니다.
"""
from celery import shared_task, chord, group
from django.utils import timezone
from typing import Dict, Any, List
import logging

from companies.models import Report, RevenueComposition
from companies.services.report_extractor import ReportExtractorService
from companies.services.revenue_extractor import RevenueExtractorService
from companies.services.report_summarizer import ReportSummarizerService
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.refiner import RefineService
from news.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def extract_report_content_task(self, report_id: int) -> Dict[str, Any] | None:
    """보고서 본문 추출 (OpenDartReader 사용)"""
    try:
        report = Report.objects.get(id=report_id)
        report.processing_status = 'processing'
        report.save()
        
        extractor = ReportExtractorService()
        # rcept_no (접수번호)를 사용하여 DART에서 직접 본문 추출
        raw_content = extractor.extract_content(report.rcept_no)
        
        if not raw_content:
            logger.warning(f"보고서 본문 추출 실패: {report_id} (rcept_no: {report.rcept_no})")
            report.processing_status = 'failed'
            report.save()
            return None
        
        report.raw_content = raw_content
        report.save()
        
        return {
            "report_id": report_id,
            "rcept_no": report.rcept_no,
            "raw_content": raw_content,
            "company_stock_code": report.company.stock_code,
            "company_name": report.company.company_name,
            "report_name": report.report_name,
            "report_type": report.report_type,
            "submitted_at": str(report.submitted_at),
        }
    except Report.DoesNotExist:
        logger.error(f"Report not found: {report_id}")
        return None
    except Exception as e:
        logger.error(f"보고서 본문 추출 오류: {report_id} - {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def refine_report_content_task(self, data: Dict[str, Any]) -> Dict[str, Any] | None:
    """보고서 본문 정제"""
    if not data:
        return None
    
    try:
        report_id = data["report_id"]
        raw_content = data["raw_content"]
        
        refiner = RefineService()
        refined_content = refiner.get_refined_body(raw_content)
        
        if not refined_content or len(refined_content.strip()) < 100:
            logger.warning(f"보고서 정제 결과가 너무 짧음: {report_id}")
            return None
        
        # DB 업데이트
        Report.objects.filter(id=report_id).update(refined_content=refined_content)
        
        data["refined_content"] = refined_content
        return data
    except Exception as e:
        logger.error(f"보고서 정제 오류: {data.get('report_id')} - {e}")
        raise


@shared_task(bind=True, max_retries=3)
def extract_report_info_task(self, data: Dict[str, Any]) -> Dict[str, Any] | None:
    """통합 정보 추출 (요약 + 매출 구성)"""
    if not data:
        return None
    
    try:
        report_id = data["report_id"]
        refined_content = data["refined_content"]
        company_name = data["company_name"]
        company_stock_code = data["company_stock_code"]
        report_name = data["report_name"]
        submitted_at = data.get("submitted_at", "")
        
        # 1회 호출로 요약 + 매출 구성 통합 추출
        extractor = ReportInfoExtractorService()
        extracted_info = extractor.extract_info(refined_content, report_name, company_name)
        
        # DB 업데이트 (extracted_info JSON으로 저장)
        Report.objects.filter(id=report_id).update(extracted_info=extracted_info)
        
        # 매출 구성이 있으면 별도 테이블에도 저장
        revenue_composition = extracted_info.get("revenue_composition", [])
        if revenue_composition:
            fiscal_year = int(submitted_at[:4]) if submitted_at else timezone.now().year
            for segment in revenue_composition:
                RevenueComposition.objects.update_or_create(
                    company_id=company_stock_code,
                    fiscal_year=fiscal_year,
                    segment_name=segment.get("segment", ""),
                    defaults={
                        "revenue": segment.get("revenue", 0),
                        "ratio": segment.get("ratio"),
                    }
                )
            logger.info(f"매출 구성 저장 완료: {report_id} - {len(revenue_composition)}개 부문")
        
        data["extracted_info"] = extracted_info
        return data
    except Exception as e:
        logger.error(f"정보 추출 오류: {data.get('report_id')} - {e}")
        raise


@shared_task(bind=True, max_retries=3)
def create_report_embedding_task(self, data: Dict[str, Any]) -> Dict[str, Any] | None:
    """보고서 임베딩 생성"""
    if not data:
        return None
    
    try:
        report_id = data["report_id"]
        refined_content = data["refined_content"]
        
        embedding_service = EmbeddingService()
        embedding = embedding_service.create_embedding(refined_content)
        
        if not embedding:
            logger.warning(f"임베딩 생성 실패: {report_id}")
            return data
        
        # DB 업데이트
        Report.objects.filter(id=report_id).update(embedding=embedding)
        
        data["embedding"] = embedding
        return data
    except Exception as e:
        logger.error(f"임베딩 생성 오류: {data.get('report_id')} - {e}")
        return data


@shared_task
def save_report_to_opensearch_task(data: Dict[str, Any]) -> bool:
    """OpenSearch에 보고서 저장"""
    if not data or not data.get("embedding"):
        return False
    
    try:
        # extracted_info에서 요약 추출
        extracted_info = data.get("extracted_info", {})
        summary = extracted_info.get("summary", {}).get("one_line", "")
        
        opensearch = ReportOpenSearchService()
        success = opensearch.save_report_vector(
            report_id=data["report_id"],
            company_stock_code=data["company_stock_code"],
            company_name=data["company_name"],
            report_name=data["report_name"],
            report_type=data["report_type"],
            content=data.get("refined_content", "")[:10000],  # 본문 일부만
            summary=summary,
            content_vector=data["embedding"],
            submitted_at=data.get("submitted_at"),
        )
        
        if success:
            Report.objects.filter(id=data["report_id"]).update(
                processing_status='completed',
                processed_at=timezone.now(),
            )
            logger.info(f"OpenSearch 저장 성공: {data['report_id']}")
        
        return success
    except Exception as e:
        logger.error(f"OpenSearch 저장 오류: {data.get('report_id')} - {e}")
        return False


@shared_task
def process_single_report_pipeline(report_id: int):
    """단일 보고서 처리 파이프라인"""
    from celery import chain
    
    workflow = chain(
        extract_report_content_task.s(report_id),
        refine_report_content_task.s(),
        extract_report_info_task.s(),  # 통합: 요약 + 매출구성 1회 호출
        create_report_embedding_task.s(),
        save_report_to_opensearch_task.s(),
    )
    
    return workflow.apply_async()


@shared_task
def process_company_reports(stock_code: str, limit: int = 20):
    """기업의 미처리 보고서 일괄 처리"""
    reports = Report.objects.filter(
        company_id=stock_code,
        processing_status='pending',
    ).order_by('-submitted_at')[:limit]
    
    logger.info(f"보고서 처리 시작: {stock_code} - {reports.count()}건")
    
    for report in reports:
        process_single_report_pipeline.delay(report.id)
    
    return reports.count()
```

### 4단계: API 엔드포인트

**companies/views.py에 추가:**

```python
@extend_schema(
    summary="보고서 처리 시작",
    description="기업의 미처리 보고서를 일괄 처리합니다 (본문 추출, 정제, 구조화된 정보 추출, OpenSearch 적재).",
    parameters=[
        OpenApiParameter(name="limit", type=int, description="처리할 보고서 수 (기본값: 20)"),
    ],
    responses={
        202: OpenApiResponse(description="처리 시작됨"),
        404: OpenApiResponse(description="Company not found"),
    },
    tags=["Reports"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def process_company_reports_view(request, stock_code):
    """보고서 처리 API"""
    from companies.tasks.report_processing import process_company_reports
    
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)
        limit = int(request.query_params.get("limit", 20))
        
        # Celery 태스크 실행
        task = process_company_reports.delay(stock_code, limit)
        
        return Response({
            "status": 202,
            "message": f"보고서 처리 시작됨",
            "data": {
                "stock_code": stock_code,
                "task_id": task.id,
                "limit": limit,
            }
        }, status=status.HTTP_202_ACCEPTED)
    except Company.DoesNotExist:
        return Response({"error": "Company not found"}, status=404)
```

## 파일 구조

```
companies/
├── services/
│   ├── report_extractor.py       # 보고서 본문 추출 (신규)
│   ├── report_info_extractor.py  # 통합 정보 추출: 요약+매출구성 (신규)
│   ├── report_opensearch.py      # OpenSearch 보고서 서비스 (신규)
│   ├── reports.py                # 기존 보고서 목록 서비스
│   └── ...
├── tasks/
│   ├── __init__.py
│   ├── dart_sync.py              # 기존 동기화 태스크
│   └── report_processing.py      # 보고서 처리 태스크 (신규)
├── models.py                     # Report 모델 수정
├── views.py                      # API 엔드포인트 추가
└── urls.py                       # URL 패턴 추가
```

## 구현 순서

1. [ ] Report 모델에 신규 필드 추가 + 마이그레이션
2. [ ] `companies/services/report_extractor.py` 구현
3. [ ] `companies/services/report_info_extractor.py` 구현 (요약+매출구성 통합)
4. [ ] `companies/services/report_opensearch.py` 구현
5. [ ] `companies/tasks/report_processing.py` 구현
6. [ ] API 엔드포인트 추가
7. [ ] 테스트 스크립트 작성
8. [ ] Celery Beat 스케줄 등록 (선택)

## 주의사항

1. **API 요금 관리**: Gemini API 호출 횟수 모니터링 필요
2. **Rate Limiting**: DART API, Gemini API 모두 요청 제한 있음
3. **에러 처리**: 각 단계별 실패 시 재시도 로직 필요
4. **데이터 무결성**: 부분 실패 시 처리 상태 관리 필요
5. **스케일링**: 대량 처리 시 Celery Worker 수 조절 필요
6. **OpenDartReader 의존성**: `pip install opendartreader lxml beautifulsoup4` 필요

## 패키지 설치

```bash
# requirements.txt에 추가
opendartreader>=0.2.3
lxml>=5.0.0
beautifulsoup4>=4.12.0
```