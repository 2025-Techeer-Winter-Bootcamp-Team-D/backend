# companies/services/corp_code_parser.py
"""
DART 고유번호 목록 XML 파싱 서비스
"""
import xmltodict
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CorpCodeParser:
    """DART 고유번호 목록 XML 파서"""

    @staticmethod
    def parse_corp_code_xml(xml_content: str) -> List[Dict[str, Any]]:
        """
        DART 고유번호 목록 XML을 파싱하여 상장기업 정보 리스트 반환
        (stock_code가 있는 기업만 포함)

        Args:
            xml_content: XML 파일 내용

        Returns:
            상장기업 정보 딕셔너리 리스트 (stock_code가 있는 기업만)
            [
                {
                    'corp_code': '00126380',
                    'corp_name': '삼성전자',
                    'stock_code': '005930',
                    'modify_date': '20240101'
                },
                ...
            ]
        """
        try:
            # XML을 딕셔너리로 변환
            data = xmltodict.parse(xml_content)

            # DART XML 구조: <result><list><list>...</list></list></result>
            result = data.get("result", {})
            list_data = result.get("list", {})

            # list_data가 리스트인지 딕셔너리인지 확인
            if isinstance(list_data, dict):
                # 단일 항목인 경우 리스트로 변환
                list_data = [list_data]
            elif not isinstance(list_data, list):
                logger.warning("예상치 못한 XML 구조")
                return []

            companies = []
            for item in list_data:
                # item이 None이거나 딕셔너리가 아닌 경우 건너뛰기
                if not item or not isinstance(item, dict):
                    continue

                # 상장기업만 포함 (stock_code가 있는 기업만)
                # stock_code가 없으면 비상장기업이므로 건너뜀
                stock_code = item.get("stock_code") or item.get("stockCode") or ""
                if stock_code:
                    stock_code = str(stock_code).strip()
                    # 빈 문자열이 아닌 경우만 포함
                    if not stock_code:
                        continue
                else:
                    continue  # 종목코드가 없으면 비상장기업이므로 건너뜀

                corp_code = item.get("corp_code") or item.get("corpCode") or ""
                corp_name = item.get("corp_name") or item.get("corpName") or ""
                modify_date = item.get("modify_date") or item.get("modifyDate") or ""

                if stock_code:
                    companies.append(
                        {
                            "corp_code": str(corp_code).strip() if corp_code else "",
                            "corp_name": str(corp_name).strip() if corp_name else "",
                            "stock_code": stock_code,
                            "modify_date": (
                                str(modify_date).strip() if modify_date else ""
                            ),
                        }
                    )

            logger.info(f"파싱된 기업 수: {len(companies)}")
            return companies

        except Exception as e:
            logger.error(f"XML 파싱 실패: {e}")
            raise
