# news/services/summarizer.py
"""
뉴스 요약 서비스

Gemini API를 사용하여 뉴스 본문 요약 및 감성 분석
"""

import json
import logging
from typing import Dict

from services.base import GeminiGenerativeClient

logger = logging.getLogger(__name__)


class SummarizeService(GeminiGenerativeClient):
    """
    정제된 본문을 기반으로 단순 요약만 수행
    """

    def __init__(self):
        super().__init__(model_name="gemini-2.5-flash-lite")

    def get_summary_only(self, perfect_text: str) -> Dict[str, str]:
        """
        본문을 3줄로 요약하고 감성분석을 수행하여 JSON으로 반환

        프롬프트 인젝션 방지를 위해:
        - 입력 텍스트를 명확한 구분자로 분리
        - 입력 길이 제한
        - safety_settings 적용

        Args:
            perfect_text: 정제된 뉴스 본문

        Returns:
            {"summary": "요약 내용", "sentiment": "positive|neutral|negative"}
        """
        # 입력 길이 제한 (프롬프트 인젝션 방지 및 토큰 절감)
        perfect_text = self.truncate_text(perfect_text, max_length=50000)

        # 프롬프트 인젝션 방지를 위해 입력 텍스트를 명확한 구분자로 분리
        prompt = """다음 뉴스 본문을 읽고 핵심 내용을 3줄 이내로 요약하고, 이 뉴스의 감성을 분석하여
JSON 형식으로 응답하세요.
추가적인 분석이나 의견은 배제하십시오.

응답 형식:
{{
    "summary": "3줄 이내 요약 내용",
    "sentiment": "positive" 또는 "neutral" 또는 "negative"
}}

감성 분석 기준:
- positive: 긍정적 전망, 호재, 상승, 성장, 긍정적 기업 소식
- neutral: 중립적 보도, 사실 전달, 변동 없음
- negative: 부정적 전망, 악재, 하락, 우려, 부정적 기업 소식

아래 "=== 본문 시작 ==="와 "=== 본문 끝 ===" 사이의 텍스트만 요약하고 감성을 분석하세요.

=== 본문 시작 ===
{input_text}
=== 본문 끝 ===

위 본문을 요약하고 감성을 분석하여 JSON 형식으로 응답하세요.""".format(
            input_text=perfect_text
        )

        try:
            text = self.generate_content(prompt, use_safety_settings=True)

            # JSON 형식으로 파싱 시도
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_text = text[start:end]
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

            # JSON 형식이 아니면 그냥 텍스트로 반환 (감성은 중립)
            return {"summary": text, "sentiment": "neutral"}
        except Exception as e:
            if self.is_quota_error(e):
                logger.warning("Gemini API 쿼터 초과: 요약 생성 불가")
                return {
                    "summary": "Gemini API 토큰 부족으로 요약 생성 실패",
                    "sentiment": "neutral",
                }
            else:
                logger.error(f"Summarization failed: {e}")
                return {"summary": "요약 생성 실패", "sentiment": "neutral"}
