import google.generativeai as genai
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)


class SummarizeService:
    """
    정제된 본문을 기반으로 단순 요약만 수행
    """

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # 모델 이름 시도 (가성비 좋은 모델 우선: Flash 모델이 빠르고 저렴)
        # gemini-2.5-flash: 최신 Flash 모델, 빠르고 저렴하며 품질도 좋음
        # gemini-flash-latest: 항상 최신 Flash 버전 (자동 업데이트)
        model_names = [
            "models/gemini-2.5-flash-lite",
            "gemini-2.5-flash-lite",  # models/ 접두사 없는 버전
        ]
        self.model = None
        for model_name in model_names:
            try:
                self.model = genai.GenerativeModel(model_name)
                logger.info(f"Gemini 모델 초기화 성공: {model_name}")
                break
            except Exception as e:
                logger.debug(f"모델 {model_name} 초기화 실패: {str(e)}")
                continue

        if self.model is None:
            # 사용 가능한 모델 목록에서 찾기
            try:
                available_models = genai.list_models()
                for model in available_models:
                    if "generateContent" in model.supported_generation_methods:
                        model_name = model.name.replace("models/", "")
                        self.model = genai.GenerativeModel(model_name)
                        logger.info(f"사용 가능한 모델로 초기화: {model_name}")
                        break
            except Exception as e:
                logger.error(f"모델 목록 조회 실패: {str(e)}")

        if self.model is None:
            raise ValueError("사용 가능한 Gemini 모델을 찾을 수 없습니다.")

    def get_summary_only(self, perfect_text):
        """
        본문을 3줄로 요약하여 JSON으로 반환
        """
        prompt = f"""
        다음 뉴스 본문을 읽고 핵심 내용을 3줄 이내로 요약하여 JSON 형식으로 응답하세요.
        추가적인 분석이나 의견은 배제하십시오.

        형식:
        {{
            "summary": "3줄 이내 요약 내용"
        }}

        본문:
        {perfect_text}
        """
        try:
            # response_mime_type은 최신 API에서만 지원되므로 일반 텍스트로 요청 후 파싱
            response = self.model.generate_content(prompt)
            text = response.text.strip()

            # JSON 형식으로 파싱 시도
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_text = text[start:end]
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

            # JSON 형식이 아니면 그냥 텍스트로 반환
            return {"summary": text}
        except Exception as e:
            logger.error(f"Summarization failed: {str(e)}")
            return {"summary": "요약 생성 실패"}
