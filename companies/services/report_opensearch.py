"""
보고서 OpenSearch 서비스
보고서 벡터를 OpenSearch에 저장하고 검색합니다.
"""

import logging
from datetime import datetime

from django.conf import settings
from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)


class ReportOpenSearchService:
    """보고서 OpenSearch 서비스"""

    REPORTS_INDEX_NAME = "report_vectors"
    VECTOR_DIMENSION = 768

    def __init__(self):
        host = settings.OPENSEARCH_HOST
        if ":" in host:
            host_parts = host.split(":")
            host_name = host_parts[0]
            port = int(host_parts[1])
        else:
            host_name = host
            port = 9200

        http_auth = None
        if settings.OPENSEARCH_PASSWORD:
            http_auth = (settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD)

        self.client = OpenSearch(
            hosts=[{"host": host_name, "port": port}],
            http_compress=True,
            use_ssl=settings.OPENSEARCH_USE_SSL,
            verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
            ssl_show_warn=False,
            http_auth=http_auth,  # 인증 정보
            maxsize=25,  # 연결 풀 크기 (동시 요청 처리 성능 개선)
            timeout=30,  # 요청 타임아웃 (초)
            max_retries=3,  # 재시도 횟수
            retry_on_timeout=True,  # 타임아웃 시 재시도
            retry_on_status=[502, 503, 504],  # 특정 HTTP 상태 코드에서 재시도
        )

        self._ensure_index_exists()

    def _ensure_index_exists(self):
        """인덱스가 없으면 생성"""
        try:
            if not self.client.indices.exists(index=self.REPORTS_INDEX_NAME):
                index_body = {
                    "settings": {
                        "index": {
                            "knn": True,
                            "knn.algo_param.ef_search": 100,
                        }
                    },
                    "mappings": {
                        "properties": {
                            "report_id": {"type": "long"},
                            "company_stock_code": {"type": "keyword"},
                            "company_name": {"type": "text"},
                            "report_name": {"type": "text"},
                            "report_type": {"type": "keyword"},
                            "content": {"type": "text"},
                            "summary": {"type": "text"},
                            "content_vector": {
                                "type": "knn_vector",
                                "dimension": self.VECTOR_DIMENSION,
                                "method": {
                                    "name": "hnsw",
                                    "space_type": "cosinesimil",
                                    "engine": "lucene",
                                    "parameters": {
                                        "ef_construction": 128,
                                        "m": 24,
                                    },
                                },
                            },
                            "submitted_at": {"type": "date"},
                        }
                    },
                }
                self.client.indices.create(
                    index=self.REPORTS_INDEX_NAME, body=index_body
                )
                logger.info(f"Created index: {self.REPORTS_INDEX_NAME}")
        except Exception as e:
            logger.error(f"인덱스 생성/확인 실패: {e}")

    def save_report_vector(
        self,
        report_id: int,
        company_stock_code: str,
        company_name: str,
        report_name: str,
        report_type: str,
        content: str,
        summary: str,
        content_vector: list[float],
        submitted_at=None,
    ) -> bool:
        """보고서 벡터 저장"""
        if not content_vector or len(content_vector) != self.VECTOR_DIMENSION:
            logger.error(
                f"Invalid vector dimension: {len(content_vector) if content_vector else 0}"
            )
            return False

        doc = {
            "report_id": report_id,
            "company_stock_code": company_stock_code,
            "company_name": company_name,
            "report_name": report_name,
            "report_type": report_type,
            "content": content,
            "summary": summary,
            "content_vector": content_vector,
        }

        if submitted_at:
            doc["submitted_at"] = (
                submitted_at.isoformat()
                if isinstance(submitted_at, datetime)
                else submitted_at
            )

        try:
            response = self.client.index(
                index=self.REPORTS_INDEX_NAME,
                id=report_id,
                body=doc,
                refresh=True,
            )
            return response.get("result") in ["created", "updated"]
        except Exception as e:
            logger.error(f"Failed to save report vector: {e}")
            return False

    def search_similar_reports(
        self,
        query_vector: list[float],
        size: int = 10,
        company_stock_code: str | None = None,
    ) -> list[dict]:
        """유사 보고서 검색"""
        if not query_vector or len(query_vector) != self.VECTOR_DIMENSION:
            return []

        query = {
            "size": size,
            "query": {
                "knn": {
                    "content_vector": {
                        "vector": query_vector,
                        "k": size,
                    }
                }
            },
            "_source": [
                "report_id",
                "company_stock_code",
                "company_name",
                "report_name",
                "summary",
                "submitted_at",
            ],
        }

        # 특정 기업 필터
        if company_stock_code:
            query["query"] = {
                "bool": {
                    "must": [
                        {"knn": {"content_vector": {"vector": query_vector, "k": size}}}
                    ],
                    "filter": [{"term": {"company_stock_code": company_stock_code}}],
                }
            }

        try:
            response = self.client.search(index=self.REPORTS_INDEX_NAME, body=query)
            return [
                {**hit["_source"], "score": hit["_score"]}
                for hit in response.get("hits", {}).get("hits", [])
            ]
        except Exception as e:
            logger.error(f"Failed to search reports: {e}")
            return []

    def delete_report(self, report_id: int) -> bool:
        """보고서 벡터 삭제"""
        try:
            response = self.client.delete(
                index=self.REPORTS_INDEX_NAME,
                id=report_id,
                refresh=True,
            )
            return response.get("result") == "deleted"
        except Exception as e:
            logger.error(f"Failed to delete report: {e}")
            return False

    def get_report_count(self) -> int:
        """저장된 보고서 수 조회"""
        try:
            response = self.client.count(index=self.REPORTS_INDEX_NAME)
            return response.get("count", 0)
        except Exception as e:
            logger.error(f"Failed to get report count: {e}")
            return 0
