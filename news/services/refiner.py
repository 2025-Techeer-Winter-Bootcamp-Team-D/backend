from google import genai
from django.conf import settings
import logging
import re

logger = logging.getLogger(__name__)


class RefineService:
    """
    AI(Gemini) 정제 서비스
    """

    def __init__(self):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            error_msg = "GEMINI_API_KEY is missing or empty. Please set GEMINI_API_KEY in environment variables."
            logger.error(error_msg)
            raise ValueError(error_msg)

        self.client = genai.Client(api_key=api_key)

        # 모델 이름 (가성비 좋은 모델 우선: Flash 모델이 빠르고 저렴)
        self.model_name = "gemini-2.5-flash-lite"
        logger.info(f"Gemini 클라이언트 초기화 성공: {self.model_name}")

    def get_refined_body(self, raw_data):
        """
        Markdown에서 메타데이터 제거 후 Gemini 정제를 통해 완벽한 본문 추출

        프롬프트 인젝션 방지를 위해:
        - 입력 텍스트를 명확한 구분자로 분리
        - 입력 길이 제한
        - safety_settings 적용
        """
        # 1. Markdown 메타데이터 제거 (raw_data는 Jina Reader의 Markdown 출력)
        # 형식: "Title: ...\n\nURL Source: ...\n\nPublished Time: ...\n\nMarkdown Content:\n실제내용"
        local_text = raw_data

        # "Markdown Content:" 이후의 내용만 추출
        if "Markdown Content:" in raw_data:
            parts = raw_data.split("Markdown Content:", 1)
            if len(parts) == 2:
                local_text = parts[1].strip()

        # 메타데이터가 없는 경우 전체 내용 사용
        if not local_text:
            local_text = raw_data

        # 2. HTML 태그 제거 (Markdown에 남아있을 수 있는 HTML 태그)
        # <tag>, </tag>, <tag/>, <tag attr="value"> 등 모든 형태 제거
        local_text = re.sub(r"<[^>]+>", "", local_text)

        # 3. 이미지 참조 텍스트 정리 (예: "Image 2: 로그인", "Image 3: 아이콘" 등)
        local_text = re.sub(r"Image\s+\d+:\s*[^\n]*", "", local_text)

        # 입력 길이 제한 (프롬프트 인젝션 방지 및 토큰 절감)
        # 뉴스: ~10,000자, 보고서: ~50,000자 허용
        max_input_length = 50000
        if len(local_text) > max_input_length:
            local_text = local_text[:max_input_length]
            logger.warning(f"입력 텍스트가 {max_input_length}자를 초과하여 잘랐습니다.")

        # 2. Gemini 2차 정제 (데이터 순도 보장용)
        # 프롬프트 인젝션 방지를 위해 입력 텍스트를 명확한 구분자로 분리
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
            # safety_settings를 적용하여 안전한 응답만 허용
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
            ]

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "safety_settings": safety_settings,
                },
            )
            return response.text.strip()
        except Exception as e:
            error_message = str(e)
            # 쿼터 초과(429) 에러 명시적 처리
            if "429" in error_message or "quota" in error_message.lower():
                logger.warning("Gemini API 쿼터 초과: 로컬 정제본 사용")
            else:
                logger.error(f"Gemini Refinement failed: {error_message}")
            return local_text  # AI 실패 시 로컬 정제본이라도 반환

    def get_refined_report_body(self, raw_data):
        """
        보고서 본문 정제 (보고서 전용 프롬프트)
        
        뉴스 기사와 달리 보고서는 구조화된 문서이므로,
        광고나 메뉴가 아닌 보고서 본문 내용을 보존하면서 정제합니다.

        Args:
            raw_data: 보고서 원문 텍스트 (XML에서 추출된 텍스트)

        Returns:
            정제된 보고서 본문 텍스트
        """
        local_text = raw_data

        # HTML 태그 제거
        local_text = re.sub(r"<[^>]+>", "", local_text)

        # 이미지 참조 텍스트 정리
        local_text = re.sub(r"Image\s+\d+:\s*[^\n]*", "", local_text)

        # 입력 길이 제한
        max_input_length = 50000
        if len(local_text) > max_input_length:
            local_text = local_text[:max_input_length]
            logger.warning(f"입력 텍스트가 {max_input_length}자를 초과하여 잘랐습니다.")

        # 보고서 정제용 프롬프트
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
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
            ]

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "safety_settings": safety_settings,
                },
            )
            return response.text.strip()
        except Exception as e:
            error_message = str(e)
            if "429" in error_message or "quota" in error_message.lower():
                logger.warning("Gemini API 쿼터 초과: 로컬 정제본 사용")
            else:
                logger.error(f"Gemini 보고서 정제 실패: {error_message}")
            return local_text  # AI 실패 시 로컬 정제본이라도 반환
