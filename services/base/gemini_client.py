# services/base/gemini_client.py
"""
Gemini API 클라이언트 베이스 클래스

여러 서비스에서 공통으로 사용되는 Gemini 클라이언트 초기화 및 유틸리티
"""

import logging
from typing import List, Dict

from django.conf import settings
from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)


# 공통 안전 설정
DEFAULT_SAFETY_SETTINGS: List[Dict[str, str]] = [
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


class GeminiClientMixin:
    """Gemini API 클라이언트 공통 기능 Mixin"""

    model_name: str = "gemini-2.5-flash-lite"
    _client: genai.Client = None

    def _init_client(self) -> None:
        """Gemini 클라이언트 초기화"""
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            error_msg = (
                "GEMINI_API_KEY is missing or empty. "
                "Please set GEMINI_API_KEY in environment variables."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        self._client = genai.Client(api_key=api_key)
        logger.info(f"Gemini 클라이언트 초기화 성공: {self.model_name}")

    @property
    def client(self) -> genai.Client:
        """Gemini 클라이언트 반환 (lazy initialization)"""
        if self._client is None:
            self._init_client()
        return self._client

    @staticmethod
    def truncate_text(text: str, max_length: int = 50000) -> str:
        """
        텍스트 길이 제한

        Args:
            text: 원본 텍스트
            max_length: 최대 길이

        Returns:
            제한된 텍스트
        """
        if len(text) > max_length:
            logger.warning(f"텍스트가 {max_length}자를 초과하여 잘림")
            return text[:max_length]
        return text

    @staticmethod
    def is_quota_error(error: Exception) -> bool:
        """쿼터 초과 에러인지 확인"""
        error_message = str(error)
        return "429" in error_message or "quota" in error_message.lower()

    @property
    def safety_settings(self) -> List[Dict[str, str]]:
        """공통 안전 설정 반환"""
        return DEFAULT_SAFETY_SETTINGS


class GeminiGenerativeClient(GeminiClientMixin):
    """Gemini 생성 모델 클라이언트 (텍스트 생성용)"""

    model_name: str = "gemini-2.5-flash-lite"

    def __init__(self, model_name: str = None):
        if model_name:
            self.model_name = model_name
        self._init_client()

    def generate_content(
        self,
        prompt: str,
        use_safety_settings: bool = True,
    ) -> str:
        """
        콘텐츠 생성

        Args:
            prompt: 프롬프트 텍스트
            use_safety_settings: 안전 설정 사용 여부

        Returns:
            생성된 텍스트

        Raises:
            Exception: API 호출 실패 시
        """
        config = None
        if use_safety_settings:
            config = GenerateContentConfig(safety_settings=self.safety_settings)

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config,
        )
        return response.text.strip()


class GeminiEmbeddingClient(GeminiClientMixin):
    """Gemini 임베딩 모델 클라이언트"""

    model_name: str = "text-embedding-004"

    def __init__(self, model_name: str = None):
        if model_name:
            self.model_name = model_name
        self._init_client()

    def create_embedding(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[float] | None:
        """
        단일 텍스트의 임베딩 생성

        Args:
            text: 임베딩할 텍스트
            task_type: 임베딩 태스크 유형

        Returns:
            768차원 임베딩 벡터 (실패 시 None)
        """
        if not text:
            return None

        # 텍스트 길이 제한 (임베딩 모델 최대 입력)
        text = self.truncate_text(text, max_length=10000)

        try:
            result = self.client.models.embed_content(
                model=self.model_name,
                contents=text,
                config={"task_type": task_type},
            )
            if hasattr(result, "embeddings") and len(result.embeddings) > 0:
                return list(result.embeddings[0].values)
            else:
                logger.warning(f"Unexpected embedding response format: {result}")
                return None
        except Exception as e:
            if self.is_quota_error(e):
                logger.warning("Gemini API 쿼터 초과: 임베딩 생략")
            else:
                logger.error(f"Embedding failed: {e}")
            return None

    def get_embeddings_batch(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float] | None]:
        """
        여러 텍스트의 임베딩 일괄 생성

        Args:
            texts: 임베딩할 텍스트 리스트
            task_type: 임베딩 태스크 유형

        Returns:
            임베딩 벡터 리스트 (실패한 항목은 None)
        """
        if not texts:
            return []

        embeddings = []
        for text in texts:
            embedding = self.create_embedding(text, task_type)
            embeddings.append(embedding)

        return embeddings
