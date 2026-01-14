from google import genai
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            error_msg = "GEMINI_API_KEY is missing or empty. Please set GEMINI_API_KEY in environment variables."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 새 google.genai SDK 사용
        self.client = genai.Client(api_key=api_key)

        # 최신 Gemini Embedding 모델 사용
        # text-embedding-004: 768차원, 다국어 지원
        self.model_name = "text-embedding-004"
        logger.info(f"Gemini 클라이언트 초기화 성공: {self.model_name}")

    def create_embedding(self, text: str) -> list[float] | None:
        """
        단일 텍스트의 임베딩 생성

        Args:
            text: 임베딩할 텍스트

        Returns:
            768차원 임베딩 벡터 (실패 시 None)
        """
        if not text:
            return None

        # 텍스트 길이 제한 (임베딩 모델 최대 입력)
        max_length = 10000
        if len(text) > max_length:
            text = text[:max_length]

        try:
            result = self.client.models.embed_content(
                model=self.model_name,
                contents=text,
                config={
                    "task_type": "RETRIEVAL_DOCUMENT",
                },
            )
            if hasattr(result, "embeddings") and len(result.embeddings) > 0:
                return list(result.embeddings[0].values)
            else:
                logger.warning(f"Unexpected embedding response format: {result}")
                return None
        except Exception as e:
            error_message = str(e)
            if "429" in error_message or "quota" in error_message.lower():
                logger.warning("Gemini API 쿼터 초과: 임베딩 생략")
            else:
                logger.error(f"Embedding failed: {error_message}")
            return None

    def get_embeddings_batch(self, texts: list):
        """
        공식 문서의 batchEmbedContents를 활용한 일괄 처리

        참고: Gemini Embedding API는 단일 텍스트만 지원하므로
        배치 처리는 반복문으로 구현
        """
        if not texts:
            return []

        embeddings = []
        try:
            # Gemini Embedding API는 한 번에 하나의 텍스트만 처리 가능
            # 배치 처리를 위해 반복문 사용
            for text in texts:
                try:
                    result = self.client.models.embed_content(
                        model=self.model_name,
                        contents=text,
                        config={
                            "task_type": "RETRIEVAL_DOCUMENT",
                        },
                    )
                    # 응답 형식: result.embeddings[0].values
                    if hasattr(result, "embeddings") and len(result.embeddings) > 0:
                        embeddings.append(result.embeddings[0].values)
                    else:
                        logger.warning(
                            f"Unexpected embedding response format: {result}"
                        )
                        embeddings.append(None)
                except Exception as e:
                    error_message = str(e)
                    # 쿼터 초과(429) 에러 명시적 처리
                    if "429" in error_message or "quota" in error_message.lower():
                        logger.warning(f"Gemini API 쿼터 초과: 임베딩 생략")
                    else:
                        logger.error(
                            f"Single embedding failed for text: {text[:50]}... - {error_message}"
                        )
                    embeddings.append(None)

            return embeddings
        except Exception as e:
            logger.exception("Batch Embedding failed")
            # 부분 실패 시 기존 결과를 보존하고 나머지만 None으로 채움
            while len(embeddings) < len(texts):
                embeddings.append(None)
            return embeddings
