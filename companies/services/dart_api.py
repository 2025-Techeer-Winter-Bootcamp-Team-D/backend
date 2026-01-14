import requests
from django.conf import settings
from typing import Optional, Dict, Any, BinaryIO
import logging
import zipfile
import io

logger = logging.getLogger(__name__)


class DartAPIClient:
    """DART OpenAPI 클라이언트"""

    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self):
        self.api_key = settings.DART_API_KEY
        if not self.api_key:
            raise ValueError("DART_API_KEY가 설정되지 않았습니다.")

    def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """API 요청 공통 메서드"""
        params["crtfc_key"] = self.api_key

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"DART API 요청 실패: {endpoint} - {e}")
            raise DartAPIError(f"DART API 요청 실패: {str(e)}")

        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"DART API 응답 JSON 파싱 실패: {endpoint} - {e}")
            raise DartAPIError(f"DART API 응답 파싱 실패: {str(e)}")

        # DART API 응답 상태 코드 확인
        status = data.get("status", "000")
        if status != "000":
            error_message = data.get("message", "알 수 없는 오류")
            logger.warning(f"DART API 오류: status={status}, message={error_message}")
            raise DartAPIError(f"DART API 오류 (status: {status}): {error_message}")

        return data

    def get_company_info(self, corp_code: str) -> Dict[str, Any]:
        """기업개황 조회"""
        return self._request("company.json", {"corp_code": corp_code})

    def get_financial_statements(
        self,
        corp_code: str,
        bsns_year: str,  # 사업연도 (예: "2024")
        reprt_code: str = "11011",  # 11011: 사업보고서
    ) -> Dict[str, Any]:
        """단일회사 전체 재무제표 조회"""
        params = {
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "CFS",  # CFS: 연결재무제표, OFS: 개별재무제표
        }
        return self._request("fnlttSinglAcntAll.json", params)

    def get_disclosure_list(
        self,
        corp_code: str,
        bgn_de: Optional[str] = None,  # 시작일 (YYYYMMDD)
        end_de: Optional[str] = None,  # 종료일 (YYYYMMDD)
        pblntf_ty: Optional[str] = None,  # 공시유형 (A, B, C, D, E, F, G, H, I, J)
        page_no: int = 1,
        page_count: int = 100,
    ) -> Dict[str, Any]:
        """공시검색 (보고서 목록 조회)"""
        params = {
            "corp_code": corp_code,
            "page_no": str(page_no),
            "page_count": str(page_count),
        }
        if bgn_de:
            params["bgn_de"] = bgn_de
        if end_de:
            params["end_de"] = end_de
        if pblntf_ty:
            params["pblntf_ty"] = pblntf_ty

        return self._request("list.json", params)

    def get_corp_code_list(self) -> bytes:
        """
        전체 기업 고유번호 목록 다운로드 (ZIP 파일)

        Returns:
            ZIP 파일의 바이너리 데이터

        Raises:
            DartAPIError: API 호출 실패 시
        """
        params = {"crtfc_key": self.api_key}
        url = f"{self.BASE_URL}/corpCode.xml"

        try:
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"DART API 요청 실패 (corpCode): {e}")
            raise DartAPIError(f"DART API 요청 실패: {str(e)}")

    def extract_corp_code_xml(self, zip_data: bytes) -> str:
        """
        ZIP 파일에서 XML 파일 추출

        Args:
            zip_data: ZIP 파일의 바이너리 데이터

        Returns:
            XML 파일 내용 (문자열)

        Raises:
            DartAPIError: ZIP 파싱 실패 시
        """
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zip_file:
                # ZIP 파일 내부의 XML 파일 찾기 (보통 CORPCODE.xml)
                file_list = zip_file.namelist()
                xml_file = None
                for file_name in file_list:
                    if file_name.endswith(".xml"):
                        xml_file = file_name
                        break

                if not xml_file:
                    raise DartAPIError("ZIP 파일에서 XML 파일을 찾을 수 없습니다.")

                # XML 파일 내용 읽기
                xml_content = zip_file.read(xml_file).decode("utf-8")
                return xml_content
        except zipfile.BadZipFile as e:
            logger.error(f"ZIP 파일 파싱 실패: {e}")
            raise DartAPIError(f"ZIP 파일 파싱 실패: {str(e)}")
        except Exception as e:
            logger.error(f"XML 추출 실패: {e}")
            raise DartAPIError(f"XML 추출 실패: {str(e)}")


class DartAPIError(Exception):
    """DART API 예외"""

    pass
