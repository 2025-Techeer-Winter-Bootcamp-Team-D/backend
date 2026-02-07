"""
보고서 기업 유형 분류 서비스
Gemini를 사용하여 기업이 제조업, 금융지주사, 개별 금융사인지 분류합니다.
"""

import json
import logging

from services.base import GeminiGenerativeClient

logger = logging.getLogger(__name__)


class ReportClassifierService(GeminiGenerativeClient):
    """보고서 기업 유형 분류 서비스"""

    COMPANY_TYPES = {
        "manufacturing": "제조업",
        "financial_holding": "금융지주사",
        "financial_individual": "개별 금융사",
        "service": "서비스업",
        "other": "기타",
    }

    def __init__(self):
        super().__init__(model_name="gemini-2.5-flash-lite")

    def classify_company_type(
        self, company_name: str, report_name: str, content_sample: str
    ) -> str:
        """
        기업 유형 분류

        Args:
            company_name: 기업명
            report_name: 보고서명
            content_sample: 보고서 내용 샘플 (최대 5000자)

        Returns:
            기업 유형 코드 (manufacturing, financial_holding, financial_individual, service, other)
        """
        # 내용 샘플 길이 제한
        content_sample = self.truncate_text(content_sample, max_length=5000)

        prompt = f"""다음 기업의 보고서 정보를 바탕으로 기업 유형을 분류하세요.

기업명: {company_name}
보고서명: {report_name}

기업 유형 분류 기준:
1. **제조업 (manufacturing)**: 제품을 생산하는 기업 (예: 삼성전자, 현대차, LG화학 등)
2. **금융지주사 (financial_holding)**: 금융회사를 지배하는 지주회사 (예: KB금융지주, 신한지주 등)
3. **개별 금융사 (financial_individual)**: 은행, 증권, 보험 등 개별 금융회사 (예: KB국민은행, 신한은행 등)
4. **서비스업 (service)**: 서비스를 제공하는 기업 (예: 네이버, 카카오, 배달의민족 등)
5. **기타 (other)**: 위에 해당하지 않는 기업

보고서 내용 샘플:
{content_sample}

응답 형식 (JSON만 출력):
{{
  "company_type": "manufacturing" 또는 "financial_holding" 또는 "financial_individual" 또는 "service" 또는 "other",
  "reason": "분류 이유 (한 줄)"
}}

위 정보를 바탕으로 기업 유형을 분류하여 JSON으로 응답하세요."""

        try:
            text = self.generate_content(prompt, use_safety_settings=False)

            # JSON 파싱
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_text = text[start:end]
                result = json.loads(json_text)

                company_type = result.get("company_type", "other")
                reason = result.get("reason", "")

                # 유효한 타입인지 확인
                if company_type not in self.COMPANY_TYPES:
                    logger.warning(
                        f"유효하지 않은 기업 유형: {company_type}, 기본값 'other' 사용"
                    )
                    company_type = "other"

                logger.info(
                    f"기업 유형 분류 완료: {company_name} → {company_type} ({reason})"
                )
                return company_type

            logger.warning("JSON 파싱 실패, 기본값 'other' 사용")
            return "other"

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            return "other"
        except Exception as e:
            logger.error(f"기업 유형 분류 실패: {e}")
            return "other"
