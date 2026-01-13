import trafilatura
import google.generativeai as genai
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class RefineService:
    """
    로컬(Trafilatura) + AI(Gemini) 하이브리드 정제 서비스
    """

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # 모델 이름 시도 (가성비 좋은 모델 우선: Flash 모델이 빠르고 저렴)
        # gemini-2.5-flash: 최신 Flash 모델, 빠르고 저렴하며 품질도 좋음
        # gemini-flash-latest: 항상 최신 Flash 버전 (자동 업데이트)
        model_names = [
            "models/gemini-2.5-flash-lite",
            "gemini-2.5-flash-lite",
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

    def get_refined_body(self, raw_data):
        """
        1차 로컬 정제 후 2차 Gemini 정제를 통해 완벽한 본문 추출
        """
        # 1. 로컬 1차 정제 (토큰 절감용)
        local_text = trafilatura.extract(raw_data, include_comments=False)
        if not local_text:
            local_text = raw_data[:5000]

        # 2. Gemini 2차 정제 (데이터 순도 보장용)
        prompt = f"""
        당신은 데이터 정제 전문가입니다. 다음 텍스트에서 뉴스 기사 본문과 직접적인 관련이 없는 모든 요소(광고, 추천, 메뉴)를 제거하세요.
        
        주의사항:
        - 기사 내용을 요약하거나 변형하지 마십시오. 원문 텍스트를 그대로 유지하세요.
        - 기사 제목과 본문 내용(본문 이미지 포함)만 남기십시오.

        입력 데이터:
        {local_text}
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini Refinement failed: {str(e)}")
            return local_text  # AI 실패 시 로컬 정제본이라도 반환
