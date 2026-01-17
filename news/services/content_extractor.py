"""
Trafilatura 기반 뉴스 본문 추출 서비스

Jina Reader API 대체용으로, 로컬에서 실행되어 API 비용이 발생하지 않습니다.
"""

import logging
import trafilatura

logger = logging.getLogger(__name__)


class ContentExtractorService:
    """
    Trafilatura 기반 본문 추출 서비스

    JinaReaderService와 동일한 인터페이스를 제공하여 쉽게 교체 가능합니다.
    """

    def __init__(self):
        # Trafilatura 설정
        self.config = trafilatura.settings.use_config()
        # 타임아웃 설정 (30초)
        self.config.set("DEFAULT", "DOWNLOAD_TIMEOUT", "30")

    def extract_content(self, url: str) -> str | None:
        """
        URL로부터 본문 추출

        Args:
            url: 뉴스 기사 원문 링크

        Returns:
            정제된 본문 텍스트 (실패 시 None)
        """
        try:
            # URL에서 HTML 다운로드
            downloaded = trafilatura.fetch_url(url, config=self.config)

            if not downloaded:
                logger.warning(f"[ContentExtractor] 다운로드 실패: {url}")
                return None

            # 본문 추출
            content = trafilatura.extract(
                downloaded,
                include_comments=False,  # 댓글 제외
                include_tables=True,     # 테이블 포함
                no_fallback=False,       # 폴백 허용
                config=self.config,
            )

            if not content or len(content.strip()) < 100:
                logger.warning(f"[ContentExtractor] 추출된 본문이 너무 짧거나 비어있음: {url}")
                return None

            return content

        except Exception as e:
            logger.error(f"[ContentExtractor] 본문 추출 오류: {url} - {str(e)}")
            return None

    def extract_with_metadata(self, url: str) -> dict | None:
        """
        URL로부터 본문과 메타데이터 함께 추출

        Args:
            url: 뉴스 기사 원문 링크

        Returns:
            본문과 메타데이터가 포함된 딕셔너리 (실패 시 None)
            {
                'content': str,      # 본문
                'title': str,        # 제목
                'author': str,       # 저자
                'date': str,         # 발행일
                'sitename': str,     # 사이트명
            }
        """
        try:
            downloaded = trafilatura.fetch_url(url, config=self.config)

            if not downloaded:
                logger.warning(f"[ContentExtractor] 다운로드 실패: {url}")
                return None

            # 메타데이터 포함하여 추출
            metadata = trafilatura.extract_metadata(downloaded)
            content = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                config=self.config,
            )

            if not content or len(content.strip()) < 100:
                logger.warning(f"[ContentExtractor] 추출된 본문이 너무 짧거나 비어있음: {url}")
                return None

            return {
                'content': content,
                'title': metadata.title if metadata else None,
                'author': metadata.author if metadata else None,
                'date': metadata.date if metadata else None,
                'sitename': metadata.sitename if metadata else None,
            }

        except Exception as e:
            logger.error(f"[ContentExtractor] 본문 추출 오류: {url} - {str(e)}")
            return None


# JinaReaderService 호환 별칭 (기존 코드 호환성)
JinaReaderService = ContentExtractorService
