# companies/services/logo.py
"""
기업 로고 이미지 URL 서비스
Logo.dev API를 활용하여 기업 로고 이미지 URL을 생성
"""
from typing import Optional
from urllib.parse import urlparse
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class LogoService:
    """기업 로고 URL 생성 서비스"""

    BASE_URL = "https://img.logo.dev"

    def __init__(self, token: Optional[str] = None):
        """
        Args:
            token: Logo.dev publishable key. 없으면 settings에서 가져옴
        """
        self.token = token or settings.LOGO_DEV_PUB_KEY
        if not self.token:
            logger.warning("LOGO_DEV_PUB_KEY가 설정되지 않았습니다.")

    def get_logo_url(
        self,
        homepage_url: Optional[str] = None,
        domain: Optional[str] = None,
        size: int = 128,
        format: str = "png",
    ) -> Optional[str]:
        """
        홈페이지 URL 또는 도메인으로 로고 이미지 URL 생성

        Args:
            homepage_url: 기업 홈페이지 URL (예: "https://www.samsung.com")
            domain: 도메인 직접 지정 (예: "samsung.com")
            size: 이미지 크기 (픽셀, 기본 128)
            format: 이미지 포맷 ("png" 또는 "jpg")

        Returns:
            로고 이미지 URL 또는 None
        """
        if not self.token:
            return None

        # 도메인 추출
        target_domain = domain
        if not target_domain and homepage_url:
            target_domain = self._extract_domain(homepage_url)

        if not target_domain:
            return None

        # Logo.dev URL 생성
        return (
            f"{self.BASE_URL}/{target_domain}"
            f"?token={self.token}&size={size}&format={format}"
        )

    def _extract_domain(self, url: str) -> Optional[str]:
        """
        URL에서 도메인 추출

        Args:
            url: 전체 URL

        Returns:
            도메인 (www. 제거됨)
        """
        if not url:
            return None

        try:
            # URL에 스키마가 없으면 추가
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split("/")[0]

            # www. 접두사 제거
            if domain.startswith("www."):
                domain = domain[4:]

            return domain if domain else None
        except Exception as e:
            logger.warning(f"도메인 추출 실패 ({url}): {e}")
            return None

    def get_logo_url_for_company(self, company) -> Optional[str]:
        """
        Company 모델 인스턴스에서 로고 URL 생성

        Args:
            company: Company 모델 인스턴스

        Returns:
            로고 이미지 URL 또는 None
        """
        # 이미 logo_url이 설정되어 있으면 그대로 반환
        if company.logo_url:
            return company.logo_url

        # homepage_url로 로고 URL 생성
        if company.homepage_url:
            return self.get_logo_url(homepage_url=company.homepage_url)

        return None


# 싱글톤 인스턴스
_logo_service: Optional[LogoService] = None


def get_logo_service() -> LogoService:
    """LogoService 싱글톤 인스턴스 반환"""
    global _logo_service
    if _logo_service is None:
        _logo_service = LogoService()
    return _logo_service


def get_logo_url(
    homepage_url: Optional[str] = None,
    domain: Optional[str] = None,
    size: int = 128,
    format: str = "png",
) -> Optional[str]:
    """
    로고 URL 생성 헬퍼 함수

    Args:
        homepage_url: 기업 홈페이지 URL
        domain: 도메인 직접 지정
        size: 이미지 크기 (픽셀)
        format: 이미지 포맷

    Returns:
        로고 이미지 URL 또는 None
    """
    return get_logo_service().get_logo_url(
        homepage_url=homepage_url,
        domain=domain,
        size=size,
        format=format,
    )
