# news/services/embedding.py
"""
뉴스 임베딩 서비스

Gemini Embedding API를 사용하여 뉴스 텍스트의 벡터 임베딩 생성
"""

import logging

from services.base import GeminiEmbeddingClient

logger = logging.getLogger(__name__)


class EmbeddingService(GeminiEmbeddingClient):
    """뉴스 텍스트 임베딩 서비스"""

    def __init__(self):
        super().__init__(model_name="text-embedding-004")
