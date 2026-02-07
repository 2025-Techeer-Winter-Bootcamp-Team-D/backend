# news/services/refiner.py
"""
뉴스 본문 정제 서비스

Gemini API를 사용하여 뉴스 및 보고서 본문에서 불필요한 요소 제거
"""

import re
import logging

from services.base import GeminiGenerativeClient

logger = logging.getLogger(__name__)


class RefineService(GeminiGenerativeClient):
    """
    AI(Gemini) 정제 서비스
    """

    def __init__(self):
        super().__init__(model_name="gemini-2.5-flash-lite")

    def _preprocess_text(self, raw_data: str, is_news: bool = True) -> str:
        """
        텍스트 전처리 (공통 로직)

        Args:
            raw_data: 원본 텍스트
            is_news: 뉴스 여부 (True면 Markdown Content 추출)

        Returns:
            전처리된 텍스트
        """
        local_text = raw_data

        # 뉴스: "Markdown Content:" 이후의 내용만 추출
        if is_news and "Markdown Content:" in raw_data:
            parts = raw_data.split("Markdown Content:", 1)
            if len(parts) == 2:
                local_text = parts[1].strip()

        # 메타데이터가 없는 경우 전체 내용 사용
        if not local_text:
            local_text = raw_data

        # HTML 태그 제거
        local_text = re.sub(r"<[^>]+>", "", local_text)

        # 이미지 참조 텍스트 정리
        local_text = re.sub(r"Image\s+\d+:\s*[^\n]*", "", local_text)

        # 입력 길이 제한
        return self.truncate_text(local_text, max_length=50000)

    def get_refined_body(self, raw_data: str) -> str:
        """
        Markdown에서 메타데이터 제거 후 Gemini 정제를 통해 완벽한 본문 추출

        프롬프트 인젝션 방지를 위해:
        - 입력 텍스트를 명확한 구분자로 분리
        - 입력 길이 제한
        - safety_settings 적용

        Args:
            raw_data: Jina Reader의 Markdown 출력

        Returns:
            정제된 뉴스 본문
        """
        local_text = self._preprocess_text(raw_data, is_news=True)

        prompt = """당신은 데이터 정제 전문가입니다. 아래에 제공된 텍스트에서 뉴스 기사 본문과 직접적인
관련이 없는 모든 요소(광고, 추천, 메뉴)를 제거하세요.

주의사항:
- 기사 내용을 요약하거나 변형하지 마십시오. 원문 텍스트를 그대로 유지하세요.
- 기사 제목과 본문 내용(본문 이미지 포함)만 남기십시오.
- 아래 "=== 입력 데이터 시작 ==="와 "=== 입력 데이터 끝 ===" 사이의 텍스트만 처리하세요.
- 결과는 설명 없이 **정제된 본문 텍스트만** 반환하세요.
- 본문이 없으면 빈 문자열("")을 반환하세요.
- 과도한 공백/연속 줄바꿈은 한 번씩으로 정리하세요.

=== 입력 데이터 시작 ===
{input_text}
=== 입력 데이터 끝 ===

위 입력 데이터에서 뉴스 기사 본문만 추출하여 반환하세요.""".format(
            input_text=local_text
        )

        try:
            return self.generate_content(prompt, use_safety_settings=True)
        except Exception as e:
            if self.is_quota_error(e):
                logger.warning("Gemini API 쿼터 초과: 로컬 정제본 사용")
            else:
                logger.error(f"Gemini Refinement failed: {e}")
            return local_text  # AI 실패 시 로컬 정제본이라도 반환

    def get_refined_report_body(self, raw_data: str) -> str:
        """
        보고서 본문 정제 (보고서 전용 프롬프트)

        뉴스 기사와 달리 보고서는 구조화된 문서이므로,
        광고나 메뉴가 아닌 보고서 본문 내용을 보존하면서 정제합니다.

        Args:
            raw_data: 보고서 원문 텍스트 (XML에서 추출된 텍스트)

        Returns:
            정제된 보고서 본문 텍스트
        """
        local_text = self._preprocess_text(raw_data, is_news=False)

        prompt = """당신은 금융 보고서 정제 전문가입니다. 아래에 제공된 텍스트에서 보고서 본문과 직접적인
관련이 없는 요소(광고, 메뉴, 네비게이션)만 제거하세요.

주의사항:
- 보고서 내용을 요약하거나 변형하지 마십시오. 원문 텍스트를 그대로 유지하세요.
- 보고서의 모든 섹션, 표, 수치 데이터를 보존하세요.
- 목차, 본문, 표, 각주 등 보고서의 구조적 요소는 모두 유지하세요.
- 아래 "=== 입력 데이터 시작 ==="와 "=== 입력 데이터 끝 ===" 사이의 텍스트만 처리하세요.
- 결과는 설명 없이 **정제된 보고서 본문 텍스트만** 반환하세요.
- 본문이 없으면 빈 문자열("")을 반환하세요.
- 과도한 공백/연속 줄바꿈은 한 번씩으로 정리하세요.

=== 입력 데이터 시작 ===
{input_text}
=== 입력 데이터 끝 ===

위 입력 데이터에서 보고서 본문만 추출하여 반환하세요.""".format(
            input_text=local_text
        )

        try:
            return self.generate_content(prompt, use_safety_settings=True)
        except Exception as e:
            if self.is_quota_error(e):
                logger.warning("Gemini API 쿼터 초과: 로컬 정제본 사용")
            else:
                logger.error(f"Gemini 보고서 정제 실패: {e}")
            return local_text  # AI 실패 시 로컬 정제본이라도 반환
