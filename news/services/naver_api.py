import requests
from django.conf import settings
from dateutil import parser
import re
import logging

logger = logging.getLogger(__name__)


class NaverSearchService:
    """
    Naver News 검색 API 서비스
    """

    SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"

    def __init__(self):
        self.client_id = settings.NAVER_CLIENT_ID
        self.client_secret = settings.NAVER_CLIENT_SECRET

        if not self.client_id or not self.client_secret:
            error_msg = (
                "Naver API credentials are missing or empty. "
                "Please set NAVER_CLIENT_ID and NAVER_CLIENT_SECRET in environment variables."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    def search(self, query, display_count=10, sort="sim"):
        """
        뉴스 검색 수행
        :param query: 검색어
        :param display_count: 가져올 기사 개수 (max 100)
        :param sort: 정렬 방식 (sim: 유사도순, date: 날짜순)
        """
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {"query": query, "display": display_count, "sort": sort}

        try:
            response = requests.get(
                self.SEARCH_URL, headers=headers, params=params, timeout=5
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_items(data.get("items", []))
        except requests.exceptions.RequestException as e:
            logger.error(f"Naver API request failed: {str(e)}")
            return []

    def _parse_items(self, items):
        """데이터 정제 및 파싱"""
        parsed_list = []
        for item in items:
            parsed_item = {
                "title": self._clean_html(item.get("title")),
                "link": item.get("link"),  # 본문 추출을 위해 원본 링크 유지
                "description": self._clean_html(item.get("description")),
                "published_at": self._parse_date(item.get("pubDate")),
            }
            parsed_list.append(parsed_item)
        return parsed_list

    def _clean_html(self, text):
        """HTML 태그 제거 및 엔티티 변환"""
        if not text:
            return ""
        # <b> 등 태그 제거
        clean_text = re.sub(r"<.*?>", "", text)
        # 기본 엔티티 변환 (더 세밀한 처리가 필요하면 html.unescape 사용)
        clean_text = (
            clean_text.replace("&quot;", '"')
            .replace("&apos;", "'")
            .replace("&amp;", "&")
        )
        return clean_text

    def _parse_date(self, date_str):
        """
        Naver의 RFC 822 날짜 형식을 Python datetime으로 변환
        
        Args:
            date_str: RFC 822 형식의 날짜 문자열
            
        Returns:
            datetime 객체 (파싱 성공 시) 또는 None (파싱 실패 시)
        """
        if not date_str:
            return None
            
        try:
            # Naver pubDate 예시: "Tue, 13 Jan 2026 09:00:00 +0900"
            return parser.parse(date_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"날짜 파싱 실패: {date_str} - {str(e)}")
            return None
