# services/base/api_client.py
"""
외부 API 클라이언트 베이스 클래스

DART API, Naver API 등에서 공통으로 사용되는 HTTP 요청 처리 로직
"""

import logging
from typing import Dict, Optional, Any

import requests
from requests.exceptions import RequestException, HTTPError, Timeout

logger = logging.getLogger(__name__)


class ExternalAPIClient:
    """외부 API 클라이언트 베이스 클래스"""

    base_url: str = ""
    timeout: int = 30
    default_headers: Optional[Dict[str, str]] = None

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        HTTP 요청 수행

        Args:
            method: HTTP 메서드 (GET, POST, etc.)
            endpoint: API 엔드포인트
            params: URL 쿼리 파라미터
            data: 요청 바디 (JSON)
            headers: 추가 헤더
            timeout: 타임아웃 (초)

        Returns:
            API 응답 (JSON)

        Raises:
            RequestException: 요청 실패 시
        """
        url = f"{self.base_url}{endpoint}"
        request_headers = {**(self.default_headers or {}), **(headers or {})}
        request_timeout = timeout or self.timeout

        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=request_headers,
                timeout=request_timeout,
            )
            response.raise_for_status()
            return response.json()
        except HTTPError as e:
            logger.error(f"HTTP 오류: {url} - {e.response.status_code}")
            raise
        except Timeout:
            logger.error(f"요청 타임아웃: {url}")
            raise
        except RequestException as e:
            logger.error(f"API 요청 실패: {url} - {e}")
            raise

    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """GET 요청"""
        return self._request("GET", endpoint, params=params, **kwargs)

    def post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """POST 요청"""
        return self._request("POST", endpoint, data=data, **kwargs)

    def put(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """PUT 요청"""
        return self._request("PUT", endpoint, data=data, **kwargs)

    def delete(
        self,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """DELETE 요청"""
        return self._request("DELETE", endpoint, **kwargs)
