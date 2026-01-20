"""
보고서 섹션별 추출 서비스
DART XML/HTML에서 특정 섹션(예: [II. 사업의 내용]) 및 표(Table)를 추출하고
Markdown 형식으로 변환합니다.
"""

import re
import logging
from typing import Optional, List, Dict
from bs4 import BeautifulSoup, Tag, NavigableString

logger = logging.getLogger(__name__)


class ReportSectionExtractorService:
    """보고서 섹션별 추출 서비스"""

    # 사업보고서에서 추출할 주요 섹션 키워드 (접두어 없이 핵심 키워드만)
    BUSINESS_SECTION_KEYWORDS = [
        "사업의 내용",
    ]

    # 다음 주요 섹션을 찾기 위한 패턴 (로마숫자, 숫자, 한글 등)
    NEXT_SECTION_PATTERNS = [
        r"^[IVX]+\.\s*재무",  # III. 재무에 관한 사항
        r"^[IVX]+\.\s*주주",  # IV. 주주에 관한 사항
        r"^[IVX]+\.\s*임원",  # V. 임원에 관한 사항
        r"^\d+\.\s*재무",  # 3. 재무에 관한 사항
        r"^\d+\.\s*주주",  # 4. 주주에 관한 사항
        r"^[가-힣]\.\s*재무",  # 가. 재무에 관한 사항
        r"^[가-힣]\.\s*주주",  # 나. 주주에 관한 사항
    ]

    # 사업/수익 구성 관련 하위 섹션 키워드 (제조업, 금융업, 서비스업 등 모든 업계 포함)
    REVENUE_SUBSECTIONS = [
        # 제조업 중심
        "주요 제품 및 서비스",
        "매출 및 수주상황",
        "부문별 매출",
        "부문별 매출액",
        "사업부문별 매출",
        # 금융업 중심
        "영업종류별 현황",
        "수익별 현황",
        "연결 부문별 수익",
        "지배기업별 수익 현황",
        "자회사별 수익",
        "이자수익",
        "수수료수익",
        "보험료수익",
        "운용수익",
        # 공통
        "영업실적",
        "사업부문별 현황",
        "부문별 실적",
        "사업부문 현황",
        "부문별 영업실적",
        "사업부문별 영업실적",
        "사업부문별 요약 재무 현황",
        "부문별 요약 재무 현황",
        "사업부문별 재무 현황",
        "부문별 현황",
        "사업 현황",
        "주요 사업",
        "사업 내용",
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

        # "사업의 내용" 섹션 제목 찾기 (유연한 정규식)
        section_start_elem = self._find_section_title(
            soup, self.BUSINESS_SECTION_KEYWORDS
        )

        if not section_start_elem:
            logger.warning("사업의 내용 섹션을 찾을 수 없습니다. 전체 내용 사용")
            return self._extract_all_content(soup)

        logger.info(f"사업의 내용 섹션 발견: {section_start_elem.get_text(strip=True)}")

        # 섹션 시작 요소부터 다음 주요 섹션까지 수집
        collected_nodes = self._collect_nodes_until_next_section(section_start_elem)

        # 수집된 노드에서 REVENUE_SUBSECTIONS 키워드가 포함된 부분과 테이블 추출
        revenue_sections_found = set()
        processed_elements = set()  # 중복 처리 방지

        # 먼저 REVENUE_SUBSECTIONS 키워드가 포함된 요소 찾기
        for node in collected_nodes:
            if not isinstance(node, Tag):
                continue

            node_text = node.get_text(strip=True)
            if not node_text:
                continue

            # REVENUE_SUBSECTIONS 키워드 확인
            for keyword in self.REVENUE_SUBSECTIONS:
                if keyword in node_text and id(node) not in processed_elements:
                    revenue_sections_found.add(keyword)
                    processed_elements.add(id(node))

                    # 해당 요소와 그 형제 요소들에서 텍스트와 테이블 추출
                    # 부모 요소를 찾아서 더 넓은 범위로 추출
                    parent = node.parent
                    if parent:
                        # 텍스트 추출
                        subsection_text = self._extract_text_from_element(parent)
                        if subsection_text and len(subsection_text.strip()) >= 50:
                            main_content_parts.append(subsection_text)
                            processed_elements.add(id(parent))

                        # 테이블 추출 (부모 요소와 그 형제 요소들 포함)
                        tables = self._extract_tables_from_element(parent)
                        for table in tables:
                            if id(table) not in processed_elements:
                                table_markdown = self._table_to_markdown(table)
                                if table_markdown and len(table_markdown) > 100:
                                    table_parts.append(table_markdown)
                                    processed_elements.add(id(table))

                    # 노드 자체에서도 추출
                    subsection_text = self._extract_text_from_element(node)
                    if subsection_text and len(subsection_text.strip()) >= 50:
                        main_content_parts.append(subsection_text)

                    tables = self._extract_tables_from_element(node)
                    for table in tables:
                        if id(table) not in processed_elements:
                            table_markdown = self._table_to_markdown(table)
                            if table_markdown and len(table_markdown) > 100:
                                table_parts.append(table_markdown)
                                processed_elements.add(id(table))

                    # 다음 형제 요소들도 확인 (키워드가 포함된 섹션의 연속된 내용)
                    next_sibling = node.next_sibling
                    sibling_count = 0
                    while next_sibling and sibling_count < 10:  # 최대 10개 형제만 확인
                        if isinstance(next_sibling, Tag):
                            # 다음 주요 섹션이나 키워드가 나오면 중단
                            sibling_text = next_sibling.get_text(strip=True)
                            if any(
                                kw in sibling_text for kw in self.REVENUE_SUBSECTIONS
                            ):
                                break
                            if self._is_next_major_section(next_sibling):
                                break

                            # 텍스트와 테이블 추출
                            if id(next_sibling) not in processed_elements:
                                text = self._extract_text_from_element(next_sibling)
                                if text and len(text.strip()) >= 50:
                                    main_content_parts.append(text)
                                    processed_elements.add(id(next_sibling))

                                tables = self._extract_tables_from_element(next_sibling)
                                for table in tables:
                                    if id(table) not in processed_elements:
                                        table_markdown = self._table_to_markdown(table)
                                        if table_markdown and len(table_markdown) > 100:
                                            table_parts.append(table_markdown)
                                            processed_elements.add(id(table))
                        next_sibling = next_sibling.next_sibling
                        sibling_count += 1

                    break

        # REVENUE_SUBSECTIONS를 찾지 못한 경우 전체 섹션 내용 사용
        if not revenue_sections_found:
            logger.info("매출 관련 하위 섹션을 찾지 못해 전체 섹션 내용 사용")
            for node in collected_nodes:
                if isinstance(node, Tag) and id(node) not in processed_elements:
                    text = self._extract_text_from_element(node)
                    if text and len(text.strip()) >= 50:
                        main_content_parts.append(text)
                    tables = self._extract_tables_from_element(node)
                    for table in tables:
                        if id(table) not in processed_elements:
                            table_markdown = self._table_to_markdown(table)
                            if table_markdown and len(table_markdown) > 100:
                                table_parts.append(table_markdown)

        logger.info(
            f"매출 관련 하위 섹션 {len(revenue_sections_found)}개 발견: {revenue_sections_found}"
        )

        return {
            "main_content": "\n\n".join(main_content_parts),
            "tables": "\n\n".join(table_parts),
        }

    def _find_section_title(
        self, soup: BeautifulSoup, keywords: List[str]
    ) -> Optional[Tag]:
        """
        섹션 제목 찾기 (유연한 정규식 사용)

        "II. 사업의 내용", "2. 사업의 내용", "가. 사업의 내용" 등 다양한 형식 매칭
        """
        for keyword in keywords:
            # 키워드 앞에 올 수 있는 패턴들
            # 로마숫자: I, II, III, IV, V 등
            # 숫자: 1, 2, 3 등
            # 한글: 가, 나, 다 등
            # 기타: (1), (가), ① 등
            patterns = [
                rf"[IVX]+\.\s*{keyword}",  # II. 사업의 내용
                rf"\d+\.\s*{keyword}",  # 2. 사업의 내용
                rf"[가-힣]\.\s*{keyword}",  # 가. 사업의 내용
                rf"\([IVX]+\)\s*{keyword}",  # (II) 사업의 내용
                rf"\(\d+\)\s*{keyword}",  # (2) 사업의 내용
                rf"\([가-힣]\)\s*{keyword}",  # (가) 사업의 내용
                rf"[①②③④⑤]\s*{keyword}",  # ① 사업의 내용
                rf"{keyword}",  # 사업의 내용 (접두어 없음)
            ]

            for pattern in patterns:
                # 텍스트 노드에서 검색
                text_node = soup.find(string=re.compile(pattern, re.IGNORECASE))
                if text_node:
                    # 부모 태그 반환
                    parent = text_node.parent
                    if parent:
                        return parent

        return None

    def _collect_nodes_until_next_section(self, start_elem: Tag) -> List:
        """
        시작 요소부터 다음 주요 섹션이 나올 때까지의 모든 노드 수집

        next_sibling을 순회하며 "III. 재무에 관한 사항" 같은 다음 섹션을 찾으면 중단
        """
        collected = []
        current = start_elem

        # 시작 요소의 다음 형제부터 시작
        current = current.next_sibling

        while current is not None:
            # 다음 주요 섹션인지 확인
            if self._is_next_major_section(current):
                logger.info(
                    f"다음 주요 섹션 발견, 수집 중단: {self._get_text_preview(current)}"
                )
                break

            # 현재 노드 수집
            collected.append(current)

            # 다음 형제로 이동
            current = current.next_sibling

        return collected

    def _is_next_major_section(self, node) -> bool:
        """다음 주요 섹션인지 확인"""
        if not node:
            return False

        # 텍스트 추출
        text = ""
        if isinstance(node, NavigableString):
            text = str(node).strip()
        elif isinstance(node, Tag):
            text = node.get_text(strip=True)

        if not text:
            return False

        # 다음 주요 섹션 패턴 확인
        for pattern in self.NEXT_SECTION_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True

        return False

    def _get_text_preview(self, node, max_length: int = 50) -> str:
        """노드의 텍스트 미리보기"""
        if isinstance(node, NavigableString):
            text = str(node).strip()
        elif isinstance(node, Tag):
            text = node.get_text(strip=True)
        else:
            text = str(node)

        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

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
