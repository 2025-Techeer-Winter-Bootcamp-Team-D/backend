import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class JinaReaderService:
    """
    jina.ai Reader API 서비스
    URL에서 본문 텍스트(Markdown)를 추출합니다.
    """

    BASE_URL = "https://r.jina.ai/"

    def __init__(self):
        # 유료 티어 사용 시 API 키가 필요할 수 있으나, 기본은 무료로 동작합니다.
        self.api_key = getattr(settings, "JINA_API_KEY", None)

    def extract_content(self, url):
        """
        URL로부터 본문 추출
        :param url: 뉴스 기사 원문 링크
        :return: 정제된 본문 텍스트 (실패 시 None)
        """
        target_url = f"{self.BASE_URL}{url}"
        headers = {
            # "Accept": "text/plain" # 일반 텍스트가 필요할 경우
            "X-With-Generated-Alt": "true"  # 이미지 alt 텍스트 포함 옵션
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            # 뉴스 사이트는 로딩이 느릴 수 있으므로 timeout을 넉넉히 30초로 설정
            response = requests.get(target_url, headers=headers, timeout=30)
            response.raise_for_status()

            content = response.text
            if not content or len(content.strip()) < 100:
                logger.warning(f"Extracted content from {url} is too short or empty.")
                return None

            return content
        except requests.exceptions.Timeout:
            logger.error(f"Jina Reader timeout for URL: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Jina Reader request failed: {str(e)}")
            return None
