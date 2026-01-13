import google.generativeai as genai
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # 최신 Gemini Embedding 모델 사용
        # text-embedding-004: 768차원, 다국어 지원
        self.model = "models/text-embedding-004"

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
                result = genai.embed_content(
                    model=self.model,
                    content=text,
                    task_type="retrieval_document",
                )
                # 응답 형식: {"embedding": [0.1, 0.2, ...]}
                if "embedding" in result:
                    embeddings.append(result["embedding"])
                else:
                    logger.warning(f"Unexpected embedding response format: {result}")
                    embeddings.append(None)

            return embeddings
        except Exception as e:
            logger.error(f"Batch Embedding failed: {str(e)}")
            # 부분 실패 시 None으로 채워서 반환 (길이 유지)
            return [None] * len(texts)
