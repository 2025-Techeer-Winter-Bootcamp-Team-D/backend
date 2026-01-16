"""
뉴스 메타데이터 추출 서비스

저자, 언론사, 키워드를 추출합니다.
- 저자/언론사: 규칙 기반 추출 우선, AI는 최후 폴백
- 키워드: AI 추출 (의미 분석 필요)
"""

import json
import logging
import re
from urllib.parse import urlparse

from django.conf import settings

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
        "www.etoday.co.kr": "이투데이",
        "www.thebell.co.kr": "더벨",
        # IT/전문지
        "www.etnews.com": "전자신문",
        "zdnet.co.kr": "ZDNet Korea",
        "www.bloter.net": "블로터",
        "www.techm.kr": "테크M",
        "www.ddaily.co.kr": "디지털데일리",
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
        "news.jtbc.co.kr": "JTBC",
        # 포털 (원본 언론사 별도 추출 필요)
        "news.naver.com": None,
        "news.daum.net": None,
    }

    # 언론사 추출 정규식
    PRESS_PATTERNS = [
        r"ⓒ\s*([가-힣A-Za-z0-9]+(?:\s*[가-힣A-Za-z0-9]+)?)",
        r"©\s*([가-힣A-Za-z0-9]+(?:\s*[가-힣A-Za-z0-9]+)?)",
        r"\[([가-힣]+(?:일보|신문|경제|뉴스|TV))\]",
        r"출처\s*[:=]\s*([가-힣A-Za-z0-9]+)",
        r"제공\s*[:=]?\s*([가-힣A-Za-z0-9]+)",
    ]

    # 저자 추출 정규식 (우선순위 순)
    AUTHOR_PATTERNS = [
        r"\[([가-힣]{2,4})\s*기자\]",
        r"【([가-힣]{2,4})\s*기자】",
        r"〈([가-힣]{2,4})\s*기자〉",
        r"《([가-힣]{2,4})\s*기자》",
        r"(?:기자|특파원)\s*[:=·]\s*([가-힣]{2,4})",
        r"(?:글|작성)\s*[:=·]\s*([가-힣]{2,4})",
        r"([가-힣]{2,4})\s*(?:기자|특파원|리포터)",
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

        Args:
            url: 뉴스 URL
            content: 정제된 뉴스 본문

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
            ai_result = self._extract_author_press_ai_fallback(
                content, need_author=not author, need_press=not press
            )
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
                if value and domain.endswith(key):
                    return value
        except Exception as e:
            logger.warning(
                f"URL에서 언론사 추출 실패: url={url}, error={e}",
                exc_info=True
            )
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
        # 주요 언론사 도메인의 이메일 패턴 (대소문자 구분 없이 검색)
        email_pattern = r"([a-zA-Z]+(?:\.[a-zA-Z]+)?)\s*@\s*(?:chosun|joongang|donga|hankyung|mk|sedaily|yna|ytn|sbs|kbs|mbc|etnews|mt|edaily)"
        # 원본 content에서 대소문자 구분 없이 검색 (IGNORECASE 플래그 사용)
        match = re.search(email_pattern, content, re.IGNORECASE)

        if match:
            # 이메일 근처에서 한글 이름 찾기 (원본 content의 인덱스 사용)
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

JSON만 응답: {{"keywords": ["키워드1", "키워드2"]}}

=== 기사 ===
{content}
""".format(
            content=content[:8000]
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
            content=content[:3000],
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
