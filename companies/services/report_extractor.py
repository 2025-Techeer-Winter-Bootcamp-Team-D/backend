"""
보고서 본문 추출 서비스
OpenDartReader를 사용하여 DART에서 직접 보고서 원문을 추출합니다.
"""

import re
import logging

import OpenDartReader
from bs4 import BeautifulSoup
from django.conf import settings

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
            soup = BeautifulSoup(xml_text, "lxml-xml")

            # 모든 텍스트 추출 (태그 제거)
            text = soup.get_text(separator="\n", strip=True)

            # 연속된 공백/줄바꿈 정리
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r" {2,}", " ", text)

            return text.strip()

        except Exception as e:
            logger.error(f"XML 파싱 실패: {e}")
            return ""
