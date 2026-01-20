"""
보고서 섹션별 추출 서비스
DART XML/HTML에서 특정 섹션(예: [II. 사업의 내용]) 및 표(Table)를 추출하고
Markdown 형식으로 변환합니다.
"""

import re
import logging
from typing import Optional, List, Dict
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class ReportSectionExtractorService:
    """보고서 섹션별 추출 서비스"""

    # 사업보고서에서 추출할 주요 섹션 키워드
    BUSINESS_SECTIONS = [
        "II. 사업의 내용",
        "II 사업의 내용",
        "2. 사업의 내용",
        "사업의 내용",
    ]

    # 매출 관련 하위 섹션 키워드
    REVENUE_SUBSECTIONS = [
        "주요 제품 및 서비스",
        "매출 및 수주상황",
        "영업실적",
        "영업종류별 현황",
        "수익별 현황",
        "사업부문별 현황",
        "부문별 매출",
    ]

    def extract_sections_with_tables(
        self, xml_content: str, report_name: str
    ) -> Dict[str, str]:
        """
        XML에서 특정 섹션과 표를 추출하여 Markdown 형식으로 변환

        Args:
            xml_content: DART XML 원문
            report_name: 보고서명 (유형 판단용)

        Returns:
            {
                "main_content": "주요 섹션 내용 (Markdown)",
                "tables": "표 데이터 (Markdown 테이블 형식)"
            }
        """
        try:
            soup = BeautifulSoup(xml_content, "lxml-xml")

            # 사업보고서/반기보고서인 경우 섹션별 추출
            if "사업보고서" in report_name or "반기보고서" in report_name:
                return self._extract_business_sections(soup, report_name)
            else:
                # 기타 보고서는 전체 내용 사용
                return self._extract_all_content(soup)

        except Exception as e:
            logger.error(f"섹션 추출 실패: {e}", exc_info=True)
            return {"main_content": "", "tables": ""}

    def _extract_business_sections(
        self, soup: BeautifulSoup, report_name: str
    ) -> Dict[str, str]:
        """사업보고서/반기보고서에서 사업 관련 섹션 추출"""
        main_content_parts = []
        table_parts = []

        # [II. 사업의 내용] 섹션 찾기
        business_section = None
        for section_keyword in self.BUSINESS_SECTIONS:
            # 섹션 제목 찾기 (다양한 형식 고려)
            # XML 내에서 텍스트 노드 검색
            section_elem = soup.find(
                string=re.compile(
                    rf"^\s*{re.escape(section_keyword)}", re.IGNORECASE | re.MULTILINE
                )
            )
            if section_elem:
                # 부모 요소 찾기
                parent = section_elem.parent
                if parent:
                    business_section = parent
                    logger.info(f"사업의 내용 섹션 발견: {section_keyword}")
                    break

        if not business_section:
            logger.warning("사업의 내용 섹션을 찾을 수 없습니다. 전체 내용 사용")
            return self._extract_all_content(soup)

        # 섹션 내에서 표가 포함된 하위 섹션 찾기
        for subsection_keyword in self.REVENUE_SUBSECTIONS:
            subsection_elem = business_section.find(
                string=re.compile(
                    rf"^\s*{re.escape(subsection_keyword)}",
                    re.IGNORECASE | re.MULTILINE,
                )
            )

            if subsection_elem:
                subsection_parent = subsection_elem.parent
                if subsection_parent:
                    # 하위 섹션 내용 추출
                    subsection_text = self._extract_text_from_element(subsection_parent)
                    if subsection_text:
                        main_content_parts.append(subsection_text)

                    # 하위 섹션 내 표 추출
                    tables = self._extract_tables_from_element(subsection_parent)
                    for table in tables:
                        table_markdown = self._table_to_markdown(table)
                        if table_markdown:
                            table_parts.append(table_markdown)

        # 표가 없는 경우 전체 섹션 내용 사용
        if not table_parts and not main_content_parts:
            section_text = self._extract_text_from_element(business_section)
            if section_text:
                main_content_parts.append(section_text)

            # 섹션 내 모든 표 추출
            tables = self._extract_tables_from_element(business_section)
            for table in tables:
                table_markdown = self._table_to_markdown(table)
                if table_markdown:
                    table_parts.append(table_markdown)

        return {
            "main_content": "\n\n".join(main_content_parts),
            "tables": "\n\n".join(table_parts),
        }

    def _extract_all_content(self, soup: BeautifulSoup) -> Dict[str, str]:
        """전체 내용 추출 (섹션별 추출 실패 시)"""
        main_content = soup.get_text(separator="\n", strip=True)
        tables = self._extract_tables_from_element(soup)
        table_markdowns = [self._table_to_markdown(table) for table in tables if table]

        return {
            "main_content": main_content,
            "tables": "\n\n".join(table_markdowns),
        }

    def _extract_text_from_element(self, element: Tag) -> str:
        """요소에서 텍스트 추출 (표 제외)"""
        if not element:
            return ""

        # 표 제거 후 텍스트 추출
        element_copy = BeautifulSoup(str(element), "lxml-xml")
        for table in element_copy.find_all("table"):
            table.decompose()

        text = element_copy.get_text(separator="\n", strip=True)
        # 연속된 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        return text.strip()

    def _extract_tables_from_element(self, element: Tag) -> List[Tag]:
        """요소에서 모든 표 추출"""
        if not element:
            return []

        tables = element.find_all("table")
        return [table for table in tables if table]

    def _table_to_markdown(self, table: Tag) -> Optional[str]:
        """
        HTML/XML 테이블을 Markdown 형식으로 변환

        Args:
            table: BeautifulSoup Table 요소

        Returns:
            Markdown 형식의 테이블 문자열
        """
        if not table:
            return None

        try:
            rows = []
            thead = table.find("thead")
            tbody = table.find("tbody") or table

            # 헤더 추출
            if thead:
                header_row = thead.find("tr")
                if header_row:
                    headers = [
                        self._clean_cell_text(cell.get_text(strip=True))
                        for cell in header_row.find_all(["th", "td"])
                    ]
                    if headers:
                        rows.append(headers)
                        # 구분선 추가
                        rows.append(["---"] * len(headers))

            # 본문 행 추출
            for tr in tbody.find_all("tr"):
                cells = [
                    self._clean_cell_text(cell.get_text(strip=True))
                    for cell in tr.find_all(["td", "th"])
                ]
                if cells:
                    rows.append(cells)

            if not rows:
                return None

            # Markdown 테이블 형식으로 변환
            markdown_lines = []
            for row in rows:
                if row == ["---"] * len(rows[0]) if rows else False:
                    # 구분선 행
                    markdown_lines.append("|" + "|".join(row) + "|")
                else:
                    # 데이터 행
                    markdown_lines.append("|" + "|".join(row) + "|")

            return "\n".join(markdown_lines)

        except Exception as e:
            logger.warning(f"테이블 Markdown 변환 실패: {e}")
            # 변환 실패 시 일반 텍스트로 추출
            return table.get_text(separator=" | ", strip=True)

    def _clean_cell_text(self, text: str) -> str:
        """셀 텍스트 정제"""
        if not text:
            return ""

        # 줄바꿈 제거 및 공백 정리
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        # Markdown 파이프 문자 이스케이프
        text = text.replace("|", "\\|")

        return text
