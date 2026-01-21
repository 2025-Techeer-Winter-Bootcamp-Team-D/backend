"""
통합 정보 추출 서비스
Gemini를 사용하여 보고서에서 구조화된 핵심 정보와 사업/수익 구성을 한 번에 추출합니다.
섹션별 파싱을 적용합니다.
"""

import json
import logging

from django.conf import settings
from google import genai

logger = logging.getLogger(__name__)


class ReportInfoExtractorService:
    """통합 정보 추출 서비스 (요약 + 사업/수익 구성)"""

    def __init__(self):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")

        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash-lite"

    def extract_info(
        self,
        refined_content: str,
        report_name: str,
        company_name: str,
        section_content: str = "",
        tables_markdown: str = "",
    ) -> dict:
        """
        정제된 본문에서 구조화된 정보와 사업/수익 구성을 한 번에 추출

        Args:
            refined_content: 정제된 보고서 본문 (전체 또는 섹션)
            report_name: 보고서명 (유형 판단용)
            company_name: 기업명
            section_content: 섹션별 추출된 내용 (선택사항)
            tables_markdown: Markdown 형식의 표 데이터 (선택사항)

        Returns:
            구조화된 추출 정보 (JSON)
        """
        # 컨텍스트 구성
        # 섹션별 추출된 내용이 있으면 우선 사용, 없으면 전체 내용 사용
        if section_content:
            main_content = section_content
        else:
            main_content = refined_content

        # 표 데이터가 있으면 추가
        if tables_markdown:
            context = f"""{main_content}

=== 표 데이터 (Markdown 형식) ===
{tables_markdown}
"""
        else:
            context = main_content

        # 입력 길이 제한
        max_input_length = 30000
        if len(context) > max_input_length:
            # 표 데이터는 우선 보존
            if tables_markdown and len(tables_markdown) < max_input_length:
                available_length = max_input_length - len(tables_markdown) - 100
                context = (
                    main_content[:available_length]
                    + f"\n\n=== 표 데이터 (Markdown 형식) ===\n{tables_markdown}"
                )
            else:
                context = context[:max_input_length]

        prompt = f"""다음 기업 보고서에서 핵심 정보를 구조화하여 추출하세요.

기업명: {company_name}
보고서명: {report_name}

요구사항:
1. 보고서 유형을 파악하고, 해당 유형에 맞는 핵심 정보를 추출
2. 한 줄 요약(one_line)은 50자 이내로 핵심만
3. key_info는 보고서 유형에 따라 중요도가 높은 항목 최대 5개만 추출:
   - 사업보고서: 매출액, 당기순이익, 주요사업, 향후전망, 위험요소 등 (중요도 높은 5개)
   - 반기보고서: 매출액, 당기순이익, 주요사업, 향후전망, 주요변동사항 등 (중요도 높은 5개)
   - 자기주식취득: 취득주식수, 금액, 기간, 목적, 결의일 등 (중요도 높은 5개)
   - 타법인주식취득: 투자대상, 금액, 목적, 기간, 결의일 등 (중요도 높은 5개)
   - 배당결정: 배당종류, 금액, 기준일, 배당성향, 결의일 등 (중요도 높은 5개)
   - 기타: 변동내용, 일자, 금액 등 핵심사항 (중요도 높은 5개)
   **중요: key_info는 반드시 최대 5개까지만 추출하고, 중요도가 높은 항목을 우선 선택하세요.**
4. 사업/수익 구성(revenue_composition) 추출:
   - **제조업**: 부문별 매출액, 제품군별 매출, 사업부문별 매출 등
   - **금융업**: 부문별 수익(이자수익, 수수료수익, 보험료수익, 운용수익 등), 자회사별 수익, 영업종류별 수익 등
   - **서비스업**: 서비스 유형별 매출, 플랫폼별 수익 등
   - **기타 업종**: 사업부문별 매출/수익, 주요 사업별 실적 등
   - **중요**: 보고서에 "매출", "수익", "영업수익", "이자수익", "수수료수익" 등
     어떤 용어를 사용하든 해당 부문별 데이터를 추출하세요.
   - 표나 본문에서 부문별/사업별 금액이 있으면 반드시 추출하세요.
5. primary_keyword는 이 보고서에서 가장 중요하다고 생각하는 키워드 하나를 추출
   (예: "신규사업 진출", "M&A", "배당 인상" 등)

응답 형식 (JSON만 출력):
{{
  "report_type": "보고서 유형명",
  "company_name": "{company_name}",
  "summary": {{
    "title": "보고서 제목",
    "date": "YYYY-MM-DD",
    "one_line": "50자 이내 한 줄 요약"
  }},
  "key_info": {{
    "항목1": "값1",
    "항목2": "값2"
  }},
  "primary_keyword": "가장 중요한 키워드 하나",
  "revenue_composition": [
    {{"segment": "사업부문명", "revenue": 금액(원), "ratio": 비율}}
  ]
}}

=== 보고서 본문 시작 ===
{context}
=== 보고서 본문 끝 ===

위 보고서의 핵심 정보를 JSON으로 응답하세요."""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            text = response.text.strip()

            # JSON 파싱
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_text = text[start:end]
                extracted_info = json.loads(json_text)

                # key_info가 5개를 초과하면 중요도가 높은 5개만 선택
                if "key_info" in extracted_info and isinstance(
                    extracted_info["key_info"], dict
                ):
                    key_info = extracted_info["key_info"]
                    if len(key_info) > 5:
                        logger.warning(
                            f"key_info가 5개를 초과 ({len(key_info)}개): "
                            f"중요도 높은 5개만 선택"
                        )
                        # 딕셔너리의 처음 5개 항목만 선택 (Python 3.7+에서는 삽입 순서 보장)
                        extracted_info["key_info"] = dict(list(key_info.items())[:5])

                return extracted_info

            return {"error": "JSON 파싱 실패"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            return {"error": f"JSON 파싱 오류: {str(e)}"}
        except Exception as e:
            logger.error(f"정보 추출 실패: {e}")
            return {"error": str(e)}
