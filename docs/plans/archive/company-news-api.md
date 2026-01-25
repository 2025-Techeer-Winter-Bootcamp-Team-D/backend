# 기업별 뉴스 API 구현 계획

## 개요

특정 기업과 관련된 뉴스를 수집, 저장, 조회하는 API를 구현합니다. 기존 뉴스 크롤링 시스템을 확장하여 기업별로 뉴스를 매핑하고, 추가 메타데이터(저자, 언론사, 키워드)를 추출합니다.

### 핵심 기능
- 기업(stock_code) 기반 뉴스 매핑 및 저장
- 뉴스 메타데이터 추출: 저자, 언론사, 키워드
- 기업별 뉴스 조회 API

### 기술 스택
- Django 6.0 + DRF
- Celery (비동기 작업)
- Naver 검색 API (기업명 기반 뉴스 검색)
- Jina.ai (본문 추출)
- Gemini API (요약 생성 + 메타데이터 추출)
- PostgreSQL (뉴스 데이터 저장)
- OpenSearch (벡터 검색, 선택적)

---

## 아키텍처

```
[API 요청: GET /companies/{stock_code}/news/]
                    ↓
              [Django API]
                    ↓
         [CompanyNews 테이블 조회]
                    ↓
              [응답 반환]

---

[백그라운드: 기업별 뉴스 수집]

[Celery Beat / 수동 트리거]
              ↓
    [Company 목록 조회]
              ↓
    [각 기업별 병렬 처리]
              ↓
    ┌─────────┴─────────┐
    ↓                   ↓
[Naver API]         [기존 News에서]
[기업명 검색]        [키워드 매칭]
    ↓                   ↓
    └─────────┬─────────┘
              ↓
       [중복 제거]
              ↓
      [Jina.ai 본문 추출]
              ↓
       [Gemini 정제]
              ↓
    ┌─────────┴─────────┐
    ↓                   ↓
[요약 생성]      [메타데이터 추출]
                 (저자, 언론사, 키워드)
    ↓                   ↓
    └─────────┬─────────┘
              ↓
     [CompanyNews 저장]
        (PostgreSQL)
              ↓
     [OpenSearch 저장]
       (선택적, 벡터검색용)
```

---

## 데이터 모델

### 1. CompanyNews 테이블 (신규)

기업과 뉴스를 1:N으로 연결하는 테이블입니다.

```python
# news/models.py (추가)

class CompanyNews(models.Model):
    """
    기업별 뉴스 데이터
    
    - 특정 기업(stock_code)과 관련된 뉴스를 저장
    - 뉴스 메타데이터 포함: 저자, 언론사, 키워드
    """
    
    news_id = models.BigAutoField(primary_key=True, verbose_name="뉴스 ID")
    
    # 기업 연결 (Company.stock_code FK)
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        to_field='stock_code',
        related_name='news',
        db_column='stock_code',
        verbose_name="기업"
    )
    
    # 기본 뉴스 정보
    title = models.CharField(max_length=500, verbose_name="제목")
    url = models.URLField(max_length=1000, verbose_name="원본 링크")
    summary = models.TextField(null=True, blank=True, verbose_name="요약")
    content = models.TextField(null=True, blank=True, verbose_name="본문")
    
    # 메타데이터
    author = models.CharField(max_length=100, null=True, blank=True, verbose_name="저자/기자")
    press = models.CharField(max_length=100, null=True, blank=True, verbose_name="언론사")
    keywords = models.JSONField(default=list, blank=True, verbose_name="키워드 목록")
    
    # 날짜 정보
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="발행일")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 시간")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 시간")
    
    # 상태 관리
    is_deleted = models.BooleanField(default=False, verbose_name="삭제 여부")
    
    class Meta:
        db_table = "company_news"
        ordering = ["-published_at", "-created_at"]
        verbose_name = "기업 뉴스"
        verbose_name_plural = "기업 뉴스 목록"
        indexes = [
            models.Index(fields=["company", "-published_at"]),
            models.Index(fields=["press", "-published_at"]),
            models.Index(fields=["-published_at", "is_deleted"]),
        ]
        constraints = [
            # 동일 기업에 같은 URL의 뉴스 중복 방지
            models.UniqueConstraint(
                fields=["company", "url"],
                name="unique_company_news_url"
            )
        ]
    
    def __str__(self):
        return f"[{self.company_id}] {self.title[:50]}"
```

### 2. DB 스키마 (SQL)

```sql
CREATE TABLE company_news (
    news_id         BIGSERIAL       PRIMARY KEY,
    stock_code      VARCHAR(6)      NOT NULL REFERENCES company(stock_code) ON DELETE CASCADE,
    title           VARCHAR(500)    NOT NULL,
    url             VARCHAR(1000)   NOT NULL,
    summary         TEXT            NULL,
    content         TEXT            NULL,
    author          VARCHAR(100)    NULL,
    press           VARCHAR(100)    NULL,
    keywords        JSONB           DEFAULT '[]',
    published_at    TIMESTAMP       NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NULL,
    is_deleted      BOOLEAN         NOT NULL DEFAULT FALSE,
    
    CONSTRAINT unique_company_news_url UNIQUE (stock_code, url)
);

-- 인덱스
CREATE INDEX idx_company_news_company_published ON company_news(stock_code, published_at DESC);
CREATE INDEX idx_company_news_press_published ON company_news(press, published_at DESC);
CREATE INDEX idx_company_news_published_deleted ON company_news(published_at DESC, is_deleted);

-- GIN 인덱스 (키워드 검색용)
CREATE INDEX idx_company_news_keywords ON company_news USING GIN(keywords);
```

---

## 메타데이터 추출 방법

### 추출 전략 요약

| 필드 | 1차 | 2차 | 3차 | Gemini 사용 |
|------|-----|-----|-----|-------------|
| **언론사** | URL 도메인 매핑 | 본문 정규식 | 저작권 표시 파싱 | 최후 폴백 |
| **저자** | 정규식 (기자명 패턴) | 본문 하단 검색 | 이메일 패턴 | 최후 폴백 |
| **키워드** | - | - | - | 사용 (유일한 경우) |

> **원칙**: 저자와 언론사는 규칙 기반 추출을 최대한 활용하고, Gemini는 모든 규칙이 실패했을 때만 최후 폴백으로 사용합니다.

---

### 1. 언론사(Press) 추출

**1차: URL 도메인 매핑**
```python
PRESS_DOMAIN_MAP = {
    # 종합 일간지
    "www.chosun.com": "조선일보",
    "www.joongang.co.kr": "중앙일보",
    "www.donga.com": "동아일보",
    "www.hani.co.kr": "한겨레",
    "www.khan.co.kr": "경향신문",
    
    # 경제지
    "www.hankyung.com": "한국경제",
    "www.mk.co.kr": "매일경제",
    "www.sedaily.com": "서울경제",
    "www.mt.co.kr": "머니투데이",
    "www.edaily.co.kr": "이데일리",
    "www.fnnews.com": "파이낸셜뉴스",
    "www.asiae.co.kr": "아시아경제",
    "biz.chosun.com": "조선비즈",
    
    # IT/전문지
    "www.etnews.com": "전자신문",
    "zdnet.co.kr": "ZDNet Korea",
    "www.bloter.net": "블로터",
    "www.techm.kr": "테크M",
    
    # 통신사
    "www.yna.co.kr": "연합뉴스",
    "www.newsis.com": "뉴시스",
    "news1.kr": "뉴스1",
    
    # 방송사
    "www.ytn.co.kr": "YTN",
    "news.sbs.co.kr": "SBS",
    "news.kbs.co.kr": "KBS",
    "imnews.imbc.com": "MBC",
    "www.jtbc.co.kr": "JTBC",
    
    # 포털 뉴스
    "news.naver.com": None,  # 네이버는 원본 언론사 추출 필요
    "news.daum.net": None,   # 다음도 마찬가지
}

def extract_press_from_url(url: str) -> str | None:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    
    # 정확한 매칭
    if domain in PRESS_DOMAIN_MAP:
        return PRESS_DOMAIN_MAP[domain]
    
    # 서브도메인 포함 매칭
    for key, value in PRESS_DOMAIN_MAP.items():
        if domain.endswith(key) or key.endswith(domain):
            return value
    
    return None
```

**2차: 본문 정규식 (저작권/출처 표시)**
```python
import re

PRESS_PATTERNS = [
    # 저작권 표시
    r"ⓒ\s*([가-힣A-Za-z0-9]+(?:\s*[가-힣A-Za-z0-9]+)?)",  # ⓒ 한국경제
    r"©\s*([가-힣A-Za-z0-9]+(?:\s*[가-힣A-Za-z0-9]+)?)",  # © 조선일보
    r"\(c\)\s*([가-힣A-Za-z0-9]+)",                        # (c) 연합뉴스
    
    # 출처 표시
    r"출처\s*[:=]\s*([가-힣A-Za-z0-9]+)",                  # 출처: 매일경제
    r"\[([가-힣]+(?:일보|신문|경제|뉴스|TV))\]",           # [한국경제]
    
    # 본문 하단
    r"제공\s*[:=]?\s*([가-힣A-Za-z0-9]+)",                 # 제공: 연합뉴스
]

def extract_press_from_content(content: str) -> str | None:
    # 본문 하단 1000자에서 검색 (저작권 표시는 보통 하단에 위치)
    search_area = content[-1500:] if len(content) > 1500 else content
    
    for pattern in PRESS_PATTERNS:
        match = re.search(pattern, search_area)
        if match:
            press = match.group(1).strip()
            # 너무 짧거나 긴 것 필터링
            if 2 <= len(press) <= 20:
                return press
    return None
```

**3차: Jina 메타데이터 파싱**
```python
def extract_press_from_jina_output(raw_content: str) -> str | None:
    """
    Jina Reader 출력에서 언론사 추출
    Jina 출력 형식: "Title: ...\n\nURL Source: ...\n\nMarkdown Content:\n..."
    일부 사이트는 언론사 정보도 포함
    """
    lines = raw_content.split('\n')
    for line in lines[:10]:  # 상단 10줄만 검색
        if 'source' in line.lower() or '출처' in line:
            # "Source: 한국경제" 같은 패턴
            match = re.search(r'[:：]\s*([가-힣A-Za-z0-9]+)', line)
            if match:
                return match.group(1).strip()
    return None
```

---

### 2. 저자(Author) 추출

**1차: 정규식 패턴 매칭 (본문 상단)**
```python
import re

# 기자명 패턴 (우선순위 순)
AUTHOR_PATTERNS = [
    # 명시적 기자 표시
    r"\[([가-힣]{2,4})\s*기자\]",                    # [홍길동 기자]
    r"【([가-힣]{2,4})\s*기자】",                    # 【홍길동 기자】
    r"〈([가-힣]{2,4})\s*기자〉",                    # 〈홍길동 기자〉
    r"《([가-힣]{2,4})\s*기자》",                    # 《홍길동 기자》
    
    # 기자: 이름 형식
    r"(?:기자|특파원|취재)\s*[:=·]\s*([가-힣]{2,4})", # 기자: 홍길동
    r"(?:글|작성)\s*[:=·]\s*([가-힣]{2,4})",          # 글: 홍길동
    
    # 이름 + 기자 형식
    r"([가-힣]{2,4})\s*(?:기자|특파원|리포터)",       # 홍길동 기자
    
    # 영문 기자명
    r"By\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",             # By John Doe
    r"Reporter\s*[:=]?\s*([A-Za-z\s]+)",              # Reporter: John
]

def extract_author_from_content(content: str) -> str | None:
    # 본문 상단 2000자에서 검색 (기자명은 보통 상단에 위치)
    search_area = content[:2000]
    
    for pattern in AUTHOR_PATTERNS:
        match = re.search(pattern, search_area)
        if match:
            author = match.group(1).strip()
            # 유효성 검증: 2~10자 사이
            if 2 <= len(author) <= 10:
                return author
    return None
```

**2차: 본문 하단 검색**
```python
def extract_author_from_footer(content: str) -> str | None:
    """본문 끝부분에서 기자 정보 추출"""
    # 마지막 500자
    footer = content[-500:] if len(content) > 500 else content
    
    # 하단 기자명 패턴
    footer_patterns = [
        r"([가-힣]{2,4})\s*기자\s*$",                  # 홍길동 기자 (줄 끝)
        r"기자\s*[:=]\s*([가-힣]{2,4})",               # 기자: 홍길동
        r"([가-힣]{2,4})\s*기자\s*[\(\[]",             # 홍길동 기자(
    ]
    
    for pattern in footer_patterns:
        match = re.search(pattern, footer)
        if match:
            return match.group(1).strip()
    return None
```

**3차: 이메일 주소에서 추출**
```python
def extract_author_from_email(content: str) -> str | None:
    """
    기자 이메일 패턴에서 이름 추출
    예: hong@chosun.com → hong, gildong.hong@mk.co.kr → hong
    """
    email_pattern = r"([a-zA-Z]+(?:\.[a-zA-Z]+)?)\s*@\s*(?:chosun|joongang|donga|hankyung|mk|sedaily|yna|ytn|sbs|kbs|mbc)"
    match = re.search(email_pattern, content.lower())
    if match:
        # 이메일은 이름 확인용으로만 사용 (실제 한글명은 주변에서 찾음)
        email_area_start = max(0, match.start() - 50)
        email_area_end = min(len(content), match.end() + 10)
        nearby_text = content[email_area_start:email_area_end]
        
        # 이메일 근처에서 한글 이름 찾기
        name_match = re.search(r"([가-힣]{2,4})", nearby_text)
        if name_match:
            return name_match.group(1)
    return None
```

---

### 3. 키워드(Keywords) 추출

키워드는 의미 기반 추출이 필요하므로 Gemini AI를 사용합니다.

```python
def extract_keywords_with_ai(content: str) -> list[str]:
    prompt = """다음 뉴스 기사의 핵심 키워드를 5개 이내로 추출하세요.

추출 기준:
- 기업명, 인물명, 주요 이슈
- 산업/분야 관련 용어
- 핵심 사건/정책명

JSON 형식으로만 응답: {"keywords": ["키워드1", "키워드2", ...]}

=== 기사 ===
{content}
=== 기사 끝 ===
""".format(content=content[:8000])

    # Gemini API 호출
    # ...
```

---

### 4. 통합 메타데이터 추출 서비스

```python
# news/services/metadata_extractor.py

from django.conf import settings
import json
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class MetadataExtractorService:
    """
    뉴스 메타데이터(저자, 언론사, 키워드) 추출 서비스
    
    추출 전략:
    - 언론사/저자: 규칙 기반 추출 우선, AI는 최후 폴백
    - 키워드: AI 추출 (의미 분석 필요)
    """
    
    # URL 도메인 → 언론사 매핑
    PRESS_DOMAIN_MAP = {
        "www.chosun.com": "조선일보",
        "www.joongang.co.kr": "중앙일보",
        "www.donga.com": "동아일보",
        "www.hankyung.com": "한국경제",
        "www.mk.co.kr": "매일경제",
        "www.sedaily.com": "서울경제",
        "www.mt.co.kr": "머니투데이",
        "www.edaily.co.kr": "이데일리",
        "www.etnews.com": "전자신문",
        "www.yna.co.kr": "연합뉴스",
        "www.ytn.co.kr": "YTN",
        "news.sbs.co.kr": "SBS",
        "news.kbs.co.kr": "KBS",
        "imnews.imbc.com": "MBC",
        "www.hani.co.kr": "한겨레",
        "www.khan.co.kr": "경향신문",
        "biz.chosun.com": "조선비즈",
        "www.fnnews.com": "파이낸셜뉴스",
        "www.asiae.co.kr": "아시아경제",
        "www.newsis.com": "뉴시스",
        "news1.kr": "뉴스1",
        "www.jtbc.co.kr": "JTBC",
        # 네이버/다음은 원본 언론사 별도 추출 필요
    }
    
    # 언론사 추출 정규식
    PRESS_PATTERNS = [
        r"ⓒ\s*([가-힣A-Za-z0-9]+(?:\s*[가-힣A-Za-z0-9]+)?)",
        r"©\s*([가-힣A-Za-z0-9]+(?:\s*[가-힣A-Za-z0-9]+)?)",
        r"\[([가-힣]+(?:일보|신문|경제|뉴스|TV))\]",
        r"출처\s*[:=]\s*([가-힣A-Za-z0-9]+)",
    ]
    
    # 저자 추출 정규식 (우선순위 순)
    AUTHOR_PATTERNS = [
        r"\[([가-힣]{2,4})\s*기자\]",
        r"【([가-힣]{2,4})\s*기자】",
        r"(?:기자|특파원)\s*[:=·]\s*([가-힣]{2,4})",
        r"([가-힣]{2,4})\s*(?:기자|특파원)",
        r"By\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
    ]
    
    def __init__(self):
        self._gemini_client = None  # Lazy initialization
    
    @property
    def gemini_client(self):
        """Gemini 클라이언트 지연 초기화 (필요할 때만)"""
        if self._gemini_client is None:
            from google import genai
            self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._gemini_client
    
    def extract_all(self, url: str, content: str) -> dict:
        """
        URL과 본문에서 모든 메타데이터 추출
        
        Returns:
            {
                "author": str | None,
                "press": str | None,
                "keywords": list[str]
            }
        """
        # 1. 언론사 추출 (규칙 기반)
        press = self._extract_press(url, content)
        
        # 2. 저자 추출 (규칙 기반)
        author = self._extract_author(content)
        
        # 3. 키워드 추출 (AI 사용)
        keywords = self._extract_keywords_ai(content)
        
        # 4. 저자/언론사가 모두 없으면 AI 폴백 (최후 수단)
        if not press or not author:
            logger.debug("Rule-based extraction incomplete, trying AI fallback")
            ai_result = self._extract_author_press_ai_fallback(content, need_author=not author, need_press=not press)
            if not author:
                author = ai_result.get("author")
            if not press:
                press = ai_result.get("press")
        
        return {
            "author": author,
            "press": press,
            "keywords": keywords,
        }
    
    def _extract_press(self, url: str, content: str) -> str | None:
        """규칙 기반 언론사 추출 (3단계)"""
        
        # 1차: URL 도메인 매핑
        press = self._extract_press_from_url(url)
        if press:
            logger.debug(f"Press extracted from URL: {press}")
            return press
        
        # 2차: 본문 정규식 (저작권 표시)
        press = self._extract_press_from_content(content)
        if press:
            logger.debug(f"Press extracted from content: {press}")
            return press
        
        # 3차: 못 찾음 (AI 폴백은 extract_all에서 처리)
        return None
    
    def _extract_press_from_url(self, url: str) -> str | None:
        """URL 도메인에서 언론사 추출"""
        try:
            domain = urlparse(url).netloc.lower()
            
            # 정확한 매칭
            if domain in self.PRESS_DOMAIN_MAP:
                return self.PRESS_DOMAIN_MAP[domain]
            
            # 서브도메인 매칭
            for key, value in self.PRESS_DOMAIN_MAP.items():
                if domain.endswith(key):
                    return value
        except Exception:
            pass
        return None
    
    def _extract_press_from_content(self, content: str) -> str | None:
        """본문에서 언론사 추출 (저작권/출처 표시)"""
        # 본문 하단 검색
        search_area = content[-1500:] if len(content) > 1500 else content
        
        for pattern in self.PRESS_PATTERNS:
            match = re.search(pattern, search_area)
            if match:
                press = match.group(1).strip()
                if 2 <= len(press) <= 20:
                    return press
        return None
    
    def _extract_author(self, content: str) -> str | None:
        """규칙 기반 저자 추출 (3단계)"""
        
        # 1차: 본문 상단 정규식
        author = self._extract_author_from_header(content)
        if author:
            logger.debug(f"Author extracted from header: {author}")
            return author
        
        # 2차: 본문 하단 검색
        author = self._extract_author_from_footer(content)
        if author:
            logger.debug(f"Author extracted from footer: {author}")
            return author
        
        # 3차: 이메일 패턴 근처
        author = self._extract_author_from_email(content)
        if author:
            logger.debug(f"Author extracted from email context: {author}")
            return author
        
        return None
    
    def _extract_author_from_header(self, content: str) -> str | None:
        """본문 상단에서 저자 추출"""
        search_area = content[:2000]
        
        for pattern in self.AUTHOR_PATTERNS:
            match = re.search(pattern, search_area)
            if match:
                author = match.group(1).strip()
                if 2 <= len(author) <= 10:
                    return author
        return None
    
    def _extract_author_from_footer(self, content: str) -> str | None:
        """본문 하단에서 저자 추출"""
        footer = content[-500:] if len(content) > 500 else content
        
        footer_patterns = [
            r"([가-힣]{2,4})\s*기자\s*$",
            r"기자\s*[:=]\s*([가-힣]{2,4})",
        ]
        
        for pattern in footer_patterns:
            match = re.search(pattern, footer, re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None
    
    def _extract_author_from_email(self, content: str) -> str | None:
        """이메일 근처에서 저자명 추출"""
        # 주요 언론사 도메인의 이메일 패턴
        email_pattern = r"([a-zA-Z]+(?:\.[a-zA-Z]+)?)\s*@\s*(?:chosun|joongang|donga|hankyung|mk|sedaily|yna|ytn|sbs|kbs|mbc|etnews|mt|edaily)"
        match = re.search(email_pattern, content.lower())
        
        if match:
            # 이메일 근처에서 한글 이름 찾기
            start = max(0, match.start() - 30)
            end = min(len(content), match.end() + 10)
            nearby = content[start:end]
            
            name_match = re.search(r"([가-힣]{2,4})", nearby)
            if name_match:
                return name_match.group(1)
        return None
    
    def _extract_keywords_ai(self, content: str) -> list[str]:
        """AI 기반 키워드 추출 (항상 사용)"""
        prompt = """다음 뉴스 기사의 핵심 키워드를 5개 이내로 추출하세요.

기준:
- 기업명, 인물명, 주요 이슈
- 산업/분야 관련 용어

JSON만 응답: {"keywords": ["키워드1", "키워드2"]}

=== 기사 ===
{content}
""".format(content=content[:8000])

        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
            )
            text = response.text.strip()
            
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                result = json.loads(text[start:end])
                return result.get("keywords", [])
        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")
        
        return []
    
    def _extract_author_press_ai_fallback(
        self, content: str, need_author: bool, need_press: bool
    ) -> dict:
        """
        저자/언론사 AI 폴백 추출 (최후 수단)
        
        규칙 기반 추출이 모두 실패했을 때만 호출됨
        """
        if not need_author and not need_press:
            return {}
        
        fields = []
        if need_author:
            fields.append("author: 기자/저자 이름 (없으면 null)")
        if need_press:
            fields.append("press: 언론사명 (없으면 null)")
        
        prompt = """다음 뉴스 기사에서 정보를 추출하세요.

추출할 정보:
{fields}

JSON만 응답 (필드가 없으면 null):
{{
    {json_fields}
}}

=== 기사 (상단 3000자) ===
{content}
""".format(
            fields="\n".join(f"- {f}" for f in fields),
            json_fields=", ".join(f'"{f.split(":")[0]}": ...' for f in fields),
            content=content[:3000]
        )

        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
            )
            text = response.text.strip()
            
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                result = json.loads(text[start:end])
                logger.debug(f"AI fallback result: {result}")
                return result
        except Exception as e:
            logger.warning(f"AI fallback extraction failed: {e}")
        
        return {}
```

---

## API 설계

### 1. 기업별 뉴스 조회 API

**Endpoint:** `GET /api/companies/{stock_code}/news/`

**Request:**
```http
GET /api/companies/005930/news/?page=1&page_size=20&press=한국경제
```

**Query Parameters:**
| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| page | int | N | 페이지 번호 (기본값: 1) |
| page_size | int | N | 페이지 크기 (기본값: 20, 최대: 100) |
| press | string | N | 언론사 필터 |
| keyword | string | N | 키워드 검색 |
| start_date | date | N | 시작일 (YYYY-MM-DD) |
| end_date | date | N | 종료일 (YYYY-MM-DD) |

**Response (200 OK):**
```json
{
    "total_count": 150,
    "total_pages": 8,
    "current_page": 1,
    "page_size": 20,
    "results": [
        {
            "news_id": 12345,
            "title": "삼성전자, AI 반도체 시장 공략 본격화",
            "summary": "삼성전자가 AI 반도체 시장 공략을 위해 대규모 투자를 발표했다...",
            "url": "https://www.hankyung.com/article/...",
            "author": "홍길동",
            "press": "한국경제",
            "keywords": ["삼성전자", "AI", "반도체", "투자"],
            "published_at": "2026-01-16T09:00:00+09:00",
            "created_at": "2026-01-16T10:30:00+09:00"
        }
    ]
}
```

### 2. 기업 뉴스 상세 조회 API

**Endpoint:** `GET /api/companies/{stock_code}/news/{news_id}/`

**Response (200 OK):**
```json
{
    "news_id": 12345,
    "title": "삼성전자, AI 반도체 시장 공략 본격화",
    "summary": "삼성전자가 AI 반도체 시장 공략을 위해 대규모 투자를 발표했다...",
    "content": "전체 본문 내용...",
    "url": "https://www.hankyung.com/article/...",
    "author": "홍길동",
    "press": "한국경제",
    "keywords": ["삼성전자", "AI", "반도체", "투자"],
    "published_at": "2026-01-16T09:00:00+09:00",
    "created_at": "2026-01-16T10:30:00+09:00",
    "updated_at": "2026-01-16T10:30:00+09:00"
}
```

### 3. View 구현

```python
# companies/views.py (추가)

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.core.paginator import Paginator
from drf_spectacular.utils import extend_schema, OpenApiParameter

from news.models import CompanyNews
from news.serializers import CompanyNewsSerializer, CompanyNewsDetailSerializer


@extend_schema(
    summary="기업 뉴스 목록 조회",
    description="특정 기업과 관련된 뉴스 목록을 조회합니다.",
    parameters=[
        OpenApiParameter(name="stock_code", type=str, location=OpenApiParameter.PATH),
        OpenApiParameter(name="page", type=int, required=False),
        OpenApiParameter(name="page_size", type=int, required=False),
        OpenApiParameter(name="press", type=str, required=False, description="언론사 필터"),
        OpenApiParameter(name="keyword", type=str, required=False, description="키워드 검색"),
        OpenApiParameter(name="start_date", type=str, required=False, description="시작일 (YYYY-MM-DD)"),
        OpenApiParameter(name="end_date", type=str, required=False, description="종료일 (YYYY-MM-DD)"),
    ],
    responses={200: CompanyNewsSerializer(many=True)},
    tags=["Company News"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def company_news_list(request, stock_code):
    """기업별 뉴스 목록 조회 API"""
    
    # 파라미터 파싱
    page = int(request.query_params.get("page", 1))
    page_size = min(int(request.query_params.get("page_size", 20)), 100)
    press = request.query_params.get("press")
    keyword = request.query_params.get("keyword")
    start_date = request.query_params.get("start_date")
    end_date = request.query_params.get("end_date")
    
    # 기본 쿼리셋
    queryset = CompanyNews.objects.filter(
        company_id=stock_code,
        is_deleted=False
    ).select_related("company")
    
    # 필터 적용
    if press:
        queryset = queryset.filter(press=press)
    if keyword:
        queryset = queryset.filter(keywords__contains=[keyword])
    if start_date:
        queryset = queryset.filter(published_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(published_at__date__lte=end_date)
    
    # 페이지네이션
    paginator = Paginator(queryset, page_size)
    news_page = paginator.page(page)
    
    serializer = CompanyNewsSerializer(news_page.object_list, many=True)
    
    return Response({
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page,
        "page_size": page_size,
        "results": serializer.data,
    })


@extend_schema(
    summary="기업 뉴스 상세 조회",
    description="특정 기업 뉴스의 상세 정보(본문 포함)를 조회합니다.",
    parameters=[
        OpenApiParameter(name="stock_code", type=str, location=OpenApiParameter.PATH),
        OpenApiParameter(name="news_id", type=int, location=OpenApiParameter.PATH),
    ],
    responses={200: CompanyNewsDetailSerializer, 404: None},
    tags=["Company News"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def company_news_detail(request, stock_code, news_id):
    """기업 뉴스 상세 조회 API"""
    
    try:
        news = CompanyNews.objects.get(
            news_id=news_id,
            company_id=stock_code,
            is_deleted=False
        )
    except CompanyNews.DoesNotExist:
        return Response(
            {"error": "News not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = CompanyNewsDetailSerializer(news)
    return Response(serializer.data)
```

### 4. Serializer 구현

```python
# news/serializers.py (추가)

class CompanyNewsSerializer(serializers.ModelSerializer):
    """기업 뉴스 목록용 Serializer (본문 제외)"""
    
    class Meta:
        model = CompanyNews
        fields = [
            "news_id",
            "title",
            "summary",
            "url",
            "author",
            "press",
            "keywords",
            "published_at",
            "created_at",
        ]


class CompanyNewsDetailSerializer(serializers.ModelSerializer):
    """기업 뉴스 상세용 Serializer (본문 포함)"""
    
    class Meta:
        model = CompanyNews
        fields = [
            "news_id",
            "title",
            "summary",
            "content",
            "url",
            "author",
            "press",
            "keywords",
            "published_at",
            "created_at",
            "updated_at",
        ]
```

---

## 뉴스 수집 파이프라인

### 1. 기업별 뉴스 크롤링 태스크

```python
# news/tasks/company_news.py

from celery import shared_task, chord, group
from typing import List
import logging

from companies.models import Company
from news.models import CompanyNews
from news.services.naver_api import NaverSearchService
from news.services.jina_api import JinaReaderService
from news.services.refiner import RefineService
from news.services.summarizer import SummarizeService
from news.services.metadata_extractor import MetadataExtractorService

logger = logging.getLogger(__name__)


@shared_task
def crawl_company_news_task(stock_code: str, max_articles: int = 10):
    """
    단일 기업의 뉴스 크롤링
    
    1. 회사명으로 Naver 뉴스 검색
    2. 각 기사 본문 추출 및 정제
    3. 요약 및 메타데이터 추출
    4. CompanyNews 저장
    """
    try:
        company = Company.objects.get(stock_code=stock_code)
    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
        return {"success": 0, "failed": 0}
    
    # Naver API로 회사명 검색
    naver_service = NaverSearchService()
    articles = naver_service.search(company.company_name, display_count=max_articles)
    
    success_count = 0
    failed_count = 0
    
    for article in articles:
        try:
            result = process_single_company_article(stock_code, article)
            if result:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error(f"Failed to process article: {e}")
            failed_count += 1
    
    logger.info(f"[{stock_code}] Crawled {success_count} articles, {failed_count} failed")
    return {"success": success_count, "failed": failed_count}


def process_single_company_article(stock_code: str, article: dict) -> bool:
    """단일 기사 처리 (동기)"""
    
    url = article.get("link")
    title = article.get("title")
    published_at = article.get("published_at")
    
    # 중복 체크
    if CompanyNews.objects.filter(company_id=stock_code, url=url).exists():
        logger.debug(f"Duplicate URL skipped: {url[:50]}...")
        return False
    
    # 본문 추출
    jina_service = JinaReaderService()
    raw_content = jina_service.extract_content(url)
    if not raw_content:
        return False
    
    # 본문 정제
    refiner = RefineService()
    refined_content = refiner.get_refined_body(raw_content)
    if not refined_content or len(refined_content.strip()) < 30:
        return False
    
    # 요약 생성
    summarizer = SummarizeService()
    summary_result = summarizer.get_summary_only(refined_content)
    summary = summary_result.get("summary", "")
    
    # 메타데이터 추출
    metadata_extractor = MetadataExtractorService()
    metadata = metadata_extractor.extract_all(url, refined_content)
    
    # 저장
    CompanyNews.objects.create(
        company_id=stock_code,
        title=title,
        url=url,
        summary=summary,
        content=refined_content,
        author=metadata.get("author"),
        press=metadata.get("press"),
        keywords=metadata.get("keywords", []),
        published_at=published_at,
    )
    
    return True


@shared_task
def crawl_all_companies_news_task(max_articles_per_company: int = 10):
    """
    모든 기업의 뉴스 크롤링 (배치)
    
    Celery Beat 스케줄러로 주기적 실행 가능
    """
    # 활성 기업 목록 조회
    companies = Company.objects.filter(is_deleted=False).values_list("stock_code", flat=True)
    
    logger.info(f"Starting company news crawl for {len(companies)} companies")
    
    # 병렬 크롤링 태스크 생성
    tasks = group(
        crawl_company_news_task.s(stock_code, max_articles_per_company)
        for stock_code in companies
    )
    
    # 실행
    result = tasks.apply_async()
    return {"scheduled_companies": len(companies)}


@shared_task
def crawl_top_companies_news_task(top_n: int = 100, max_articles: int = 10):
    """
    시가총액 상위 N개 기업의 뉴스 크롤링
    
    리소스 효율적 운영을 위해 주요 기업만 크롤링
    """
    # 시가총액 상위 기업 조회
    top_companies = Company.objects.filter(
        is_deleted=False
    ).order_by("-market_amount")[:top_n].values_list("stock_code", flat=True)
    
    logger.info(f"Crawling news for top {len(top_companies)} companies")
    
    tasks = group(
        crawl_company_news_task.s(stock_code, max_articles)
        for stock_code in top_companies
    )
    
    result = tasks.apply_async()
    return {"scheduled_companies": len(top_companies)}
```

### 2. Celery Beat 스케줄 설정

```python
# config/settings.py (추가)

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # 매일 오전 6시, 12시, 18시에 상위 100개 기업 뉴스 크롤링
    'crawl-top-companies-news': {
        'task': 'news.tasks.company_news.crawl_top_companies_news_task',
        'schedule': crontab(hour='6,12,18', minute=0),
        'args': (100, 10),  # top_n=100, max_articles=10
    },
    
    # 매주 일요일 새벽 3시에 전체 기업 뉴스 크롤링
    'crawl-all-companies-news-weekly': {
        'task': 'news.tasks.company_news.crawl_all_companies_news_task',
        'schedule': crontab(day_of_week='sunday', hour=3, minute=0),
        'args': (5,),  # max_articles_per_company=5
    },
}
```

---

## 구현 단계

### Phase 1: 모델 및 기본 API (필수)
1. `CompanyNews` 모델 생성 및 마이그레이션
2. Serializer 구현
3. 기업 뉴스 조회 API 구현 (`GET /companies/{stock_code}/news/`)
4. URL 라우팅 설정

### Phase 2: 메타데이터 추출 (필수)
1. `MetadataExtractorService` 구현
   - URL 기반 언론사 추출
   - 정규식 기반 저자 추출
   - Gemini AI 기반 키워드 추출
2. 기존 요약 서비스와 통합

### Phase 3: 뉴스 수집 파이프라인 (필수)
1. `crawl_company_news_task` 구현
2. 단일 기업 뉴스 크롤링 테스트
3. 배치 크롤링 태스크 구현

### Phase 4: 스케줄링 및 운영 (선택)
1. Celery Beat 스케줄 설정
2. 관리자 페이지 (Django Admin) 설정
3. 모니터링 설정

### Phase 5: 최적화 (선택)
1. OpenSearch 벡터 저장 (기업 뉴스 검색용)
2. 캐싱 적용 (Redis)
3. 중복 뉴스 클러스터링

---

## 파일 구조

```
news/
├── models.py                    # CompanyNews 모델 추가
├── serializers.py               # CompanyNewsSerializer 추가
├── services/
│   ├── metadata_extractor.py    # 신규: 메타데이터 추출 서비스
│   └── ...
├── tasks/
│   ├── company_news.py          # 신규: 기업 뉴스 크롤링 태스크
│   └── ...

companies/
├── views.py                     # company_news_list, company_news_detail 추가
├── urls.py                      # 라우팅 추가
```

---

## 테스트 방법

### 1. 모델 테스트
```bash
python manage.py makemigrations news
python manage.py migrate
python manage.py shell

>>> from news.models import CompanyNews
>>> from companies.models import Company
>>> company = Company.objects.first()
>>> CompanyNews.objects.create(
...     company=company,
...     title="테스트 뉴스",
...     url="https://example.com/test",
...     summary="테스트 요약",
...     press="테스트 언론사",
...     keywords=["테스트", "키워드"]
... )
```

### 2. API 테스트
```bash
# 뉴스 목록 조회
curl http://localhost:8000/api/companies/005930/news/

# 뉴스 상세 조회
curl http://localhost:8000/api/companies/005930/news/1/

# 필터 적용
curl "http://localhost:8000/api/companies/005930/news/?press=한국경제&page_size=10"
```

### 3. 크롤링 태스크 테스트
```bash
python manage.py shell

>>> from news.tasks.company_news import crawl_company_news_task
>>> result = crawl_company_news_task.delay("005930")
>>> result.get()
```

---

## 주의사항

1. **API Rate Limit**
   - Naver API: 초당 10회, 일일 25,000회
   - Gemini API: 무료 티어 제한 확인 (키워드 추출에만 사용)
   - 기업 수에 따라 적절한 배치 크기 조절

2. **중복 처리**
   - `(stock_code, url)` 조합으로 Unique 제약
   - 크롤링 시 중복 체크 필수

3. **저장 용량**
   - 본문(content) 저장 시 디스크 용량 고려
   - 필요시 압축 또는 OpenSearch만 저장

4. **메타데이터 추출 전략**
   - **저자/언론사**: 규칙 기반(정규식, URL 매핑) 우선, AI는 최후 폴백
   - **키워드**: Gemini AI 사용 (의미 분석 필요)
   - `PRESS_DOMAIN_MAP` 지속적 확장 필요
   - 정규식 패턴 커버리지 모니터링 및 개선

5. **Gemini 비용 최적화**
   - 저자/언론사는 규칙 기반 추출 성공 시 AI 호출 안 함
   - AI 폴백은 규칙 기반이 모두 실패한 경우에만 호출
   - 키워드 추출만 항상 AI 사용

6. **키워드 품질**
   - Gemini 추출 키워드 품질 모니터링
   - 필요시 키워드 정제 로직 추가

---

## 참고 문서

- [뉴스 크롤링 및 요약 시스템](./뉴스-크롤링-및-요약-시스템.md)
- [Naver Search API](https://developers.naver.com/docs/serviceapi/search/news/news.md)
- [Gemini API](https://ai.google.dev/docs)
