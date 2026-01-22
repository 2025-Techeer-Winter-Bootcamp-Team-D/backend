"""
OpenSearch 서비스

뉴스 본문의 벡터 임베딩을 OpenSearch에 저장하고 검색하는 서비스입니다.
"""

from opensearchpy import OpenSearch, helpers
from django.conf import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class OpenSearchService:
    """
    OpenSearch 벡터 저장 및 검색 서비스

    - 인덱스 생성/관리
    - 벡터 임베딩 저장
    - 벡터 유사도 검색
    """

    # 뉴스 인덱스 이름
    NEWS_INDEX_NAME = "news_vectors"

    # 벡터 차원 (Gemini text-embedding-004)
    VECTOR_DIMENSION = 768

    def __init__(self):
        """OpenSearch 클라이언트 초기화"""
        # settings.py에서 OpenSearch 설정 가져오기
        host = settings.OPENSEARCH_HOST

        # "host:port" 형식을 파싱
        if ":" in host:
            host_parts = host.split(":")
            host_name = host_parts[0]
            port = int(host_parts[1])
        else:
            host_name = host
            port = 9200

        # OpenSearch 클라이언트 생성
        http_auth = None
        if settings.OPENSEARCH_PASSWORD:
            http_auth = (settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD)

        self.client = OpenSearch(
            hosts=[{"host": host_name, "port": port}],
            http_compress=True,  # gzip 압축 사용
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

        # 인덱스가 없으면 생성
        self._ensure_index_exists()

    def _ensure_index_exists(self):
        """
        인덱스가 존재하는지 확인하고, 없으면 생성합니다.

        OpenSearch 인덱스 매핑:
        - news_id: PostgreSQL의 news_id와 매핑
        - title: 검색용 제목
        - content: 전체 본문 텍스트
        - content_vector: 벡터 임베딩 (768차원)
        - published_at: 날짜 필터링용
        """
        if not self.client.indices.exists(index=self.NEWS_INDEX_NAME):
            logger.info(f"Creating OpenSearch index: {self.NEWS_INDEX_NAME}")

            # 인덱스 매핑 정의
            index_body = {
                "settings": {
                    "index": {
                        "knn": True,  # k-NN 검색 활성화
                        "knn.algo_param.ef_search": 100,  # 검색 성능 파라미터
                    },
                    "analysis": {
                        "tokenizer": {
                            "nori_tokenizer": {
                                "type": "nori_tokenizer",
                                "decompound_mode": "mixed",  # 복합어 분해 모드
                            }
                        },
                        "filter": {
                            "nori_posfilter": {
                                "type": "nori_part_of_speech",
                                "stoptags": [
                                    # 조사 (Particles)
                                    "JKS",
                                    "JKC",
                                    "JKG",
                                    "JKO",
                                    "JKB",
                                    "JKV",
                                    "JKQ",
                                    "JX",
                                    "JC",
                                    # 어미 (Endings)
                                    "EP",
                                    "EF",
                                    "EC",
                                    "ETN",
                                    "ETM",
                                    # 기호 (Symbols) - SS, SO 제외 (버전별 지원 여부 상이)
                                    "SF",
                                    "SP",
                                    "SE",
                                    # 접미사 (Suffixes)
                                    "XSN",
                                    "XSA",
                                    "XSV",
                                ],
                            }
                        },
                        "analyzer": {
                            "nori_analyzer": {
                                "type": "custom",
                                "tokenizer": "nori_tokenizer",
                                "filter": [
                                    "nori_readingform",  # 한자를 한글로 변환
                                    "nori_posfilter",  # 불용어 품사 제거
                                    "lowercase",  # 영문 소문자 변환
                                ],
                            }
                        },
                    },
                },
                "mappings": {
                    "properties": {
                        "news_id": {"type": "long"},
                        "title": {
                            "type": "text",
                            "analyzer": "nori_analyzer",
                        },
                        "content": {
                            "type": "text",
                            "analyzer": "nori_analyzer",
                        },
                        "content_vector": {
                            "type": "knn_vector",
                            "dimension": self.VECTOR_DIMENSION,
                            "method": {
                                "name": "hnsw",  # Hierarchical Navigable Small World
                                "space_type": "cosinesimil",  # 코사인 유사도
                                "engine": "lucene",  # 검색 엔진 (OpenSearch 3.0+에서는 lucene 사용)
                                "parameters": {
                                    "ef_construction": 128,  # 인덱스 생성 시 성능
                                    "m": 24,  # 각 노드의 최대 연결 수
                                },
                            },
                        },
                        "published_at": {
                            "type": "date",
                        },
                    }
                },
            }

            try:
                self.client.indices.create(index=self.NEWS_INDEX_NAME, body=index_body)
                logger.info(f"Successfully created index: {self.NEWS_INDEX_NAME}")
            except Exception as e:
                logger.error(f"Failed to create index: {str(e)}")
                raise
        else:
            logger.debug(f"Index already exists: {self.NEWS_INDEX_NAME}")

    def save_news_vector(
        self, news_id, title, content, content_vector, published_at=None
    ):
        """
        뉴스 벡터를 OpenSearch에 저장합니다.

        Args:
            news_id: PostgreSQL의 news_id
            title: 뉴스 제목
            content: 뉴스 본문 텍스트
            content_vector: 벡터 임베딩 (768차원 리스트)
            published_at: 발행일 (datetime 또는 None)

        Returns:
            bool: 저장 성공 여부
        """
        if not content_vector or len(content_vector) != self.VECTOR_DIMENSION:
            logger.error(
                f"Invalid vector dimension: {len(content_vector) if content_vector else 0}, "
                f"expected {self.VECTOR_DIMENSION}"
            )
            return False

        # 문서 생성
        doc = {
            "news_id": news_id,
            "title": title,
            "content": content,
            "content_vector": content_vector,
        }

        # published_at이 있으면 추가
        if published_at:
            if isinstance(published_at, datetime):
                doc["published_at"] = published_at.isoformat()
            else:
                doc["published_at"] = published_at

        try:
            # OpenSearch에 저장 (ID는 news_id 사용)
            response = self.client.index(
                index=self.NEWS_INDEX_NAME,
                id=news_id,  # news_id를 문서 ID로 사용
                body=doc,
                refresh=True,  # 즉시 검색 가능하도록 refresh
            )

            if response.get("result") in ["created", "updated"]:
                logger.debug(f"Saved news vector to OpenSearch: news_id={news_id}")
                return True
            else:
                logger.warning(
                    f"Unexpected response from OpenSearch: {response.get('result')}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to save news vector to OpenSearch: {str(e)}")
            return False

    def save_news_vectors_batch(self, news_documents):
        """
        여러 뉴스 벡터를 배치로 저장합니다.

        Args:
            news_documents: 뉴스 문서 리스트. 각 항목은 다음 키를 포함:
                - news_id: int
                - title: str
                - content: str
                - content_vector: list (768차원)
                - published_at: datetime (선택적)

        Returns:
            tuple: (성공 개수, 실패 개수)
        """
        if not news_documents:
            return 0, 0

        actions = []
        for doc in news_documents:
            news_id = doc.get("news_id")
            content_vector = doc.get("content_vector")

            # 벡터 차원 검증
            if not content_vector or len(content_vector) != self.VECTOR_DIMENSION:
                logger.warning(f"Skipping news_id={news_id}: invalid vector dimension")
                continue

            # OpenSearch 문서 형식으로 변환
            action = {
                "_index": self.NEWS_INDEX_NAME,
                "_id": news_id,
                "_source": {
                    "news_id": news_id,
                    "title": doc.get("title", ""),
                    "content": doc.get("content", ""),
                    "content_vector": content_vector,
                },
            }

            # published_at 추가
            if doc.get("published_at"):
                published_at = doc["published_at"]
                if isinstance(published_at, datetime):
                    action["_source"]["published_at"] = published_at.isoformat()
                else:
                    action["_source"]["published_at"] = published_at

            actions.append(action)

        if not actions:
            return 0, 0

        try:
            # Bulk API로 일괄 저장
            success_count = 0
            failed_count = 0

            for ok, response in helpers.streaming_bulk(
                self.client, actions, refresh=True
            ):
                if ok:
                    success_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"Failed to index document: {response}")

            logger.info(
                f"Bulk indexed {success_count} documents, {failed_count} failed"
            )
            return success_count, failed_count

        except Exception as e:
            logger.error(f"Failed to bulk index documents: {str(e)}")
            return 0, len(actions)

    def search_similar_news(
        self, query_vector, size=10, min_score=None, published_after=None
    ):
        """
        벡터 유사도 검색을 수행합니다.

        Args:
            query_vector: 검색 쿼리 벡터 (768차원 리스트)
            size: 반환할 결과 개수 (기본값: 10)
            min_score: 최소 유사도 점수 (선택적)
            published_after: 이 날짜 이후의 뉴스만 검색 (datetime, 선택적)

        Returns:
            list: 검색 결과 리스트. 각 항목은 다음을 포함:
                - news_id: int
                - title: str
                - content: str
                - score: float (유사도 점수)
                - published_at: str (ISO 형식)
        """
        if not query_vector or len(query_vector) != self.VECTOR_DIMENSION:
            logger.error(
                f"Invalid query vector dimension: {len(query_vector) if query_vector else 0}, "
                f"expected {self.VECTOR_DIMENSION}"
            )
            return []

        # 쿼리 구성
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
            "_source": ["news_id", "title", "content", "published_at"],
        }

        # 필터 추가 (published_after)
        if published_after:
            if isinstance(published_after, datetime):
                published_after_str = published_after.isoformat()
            else:
                published_after_str = published_after

            query["query"] = {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "content_vector": {
                                    "vector": query_vector,
                                    "k": size,
                                }
                            }
                        }
                    ],
                    "filter": [
                        {
                            "range": {
                                "published_at": {
                                    "gte": published_after_str,
                                }
                            }
                        }
                    ],
                }
            }

        try:
            response = self.client.search(index=self.NEWS_INDEX_NAME, body=query)

            results = []
            for hit in response.get("hits", {}).get("hits", []):
                score = hit.get("_score", 0.0)

                # min_score 필터링
                if min_score is not None and score < min_score:
                    continue

                source = hit.get("_source", {})
                results.append(
                    {
                        "news_id": source.get("news_id"),
                        "title": source.get("title", ""),
                        "content": source.get("content", ""),
                        "score": score,
                        "published_at": source.get("published_at"),
                    }
                )

            logger.debug(f"Found {len(results)} similar news articles")
            return results

        except Exception as e:
            logger.error(f"Failed to search similar news: {str(e)}")
            return []

    def delete_news(self, news_id):
        """
        OpenSearch에서 뉴스를 삭제합니다.

        Args:
            news_id: 삭제할 뉴스 ID

        Returns:
            bool: 삭제 성공 여부
        """
        try:
            response = self.client.delete(
                index=self.NEWS_INDEX_NAME, id=news_id, refresh=True
            )

            if response.get("result") in ["deleted", "not_found"]:
                logger.debug(f"Deleted news from OpenSearch: news_id={news_id}")
                return True
            else:
                logger.warning(
                    f"Unexpected response from OpenSearch: {response.get('result')}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to delete news from OpenSearch: {str(e)}")
            return False

    def get_news(self, news_id):
        """
        OpenSearch에서 특정 뉴스를 조회합니다.

        Args:
            news_id: 조회할 뉴스 ID

        Returns:
            dict: 뉴스 문서 (없으면 None)
        """
        try:
            response = self.client.get(index=self.NEWS_INDEX_NAME, id=news_id)

            if response.get("found"):
                return response.get("_source")
            else:
                return None

        except Exception as e:
            logger.error(f"Failed to get news from OpenSearch: {str(e)}")
            return None

    def search_news_by_keyword(
        self,
        keyword,
        size=20,
        min_score=None,
        published_after=None,
    ):
        """
        키워드 기반 텍스트 검색을 수행합니다.

        기업명 등 키워드로 관련 뉴스를 검색합니다.
        title 필드에 2배 가중치를 부여합니다.

        Args:
            keyword: 검색 키워드 (예: "삼성전자")
            size: 반환할 결과 개수 (기본값: 20)
            min_score: 최소 관련성 점수 (선택적)
            published_after: 이 날짜 이후의 뉴스만 검색 (datetime, 선택적)

        Returns:
            list: 검색 결과 리스트. 각 항목은 다음을 포함:
                - news_id: int
                - title: str
                - score: float (관련성 점수)
                - published_at: str (ISO 형식)
        """
        if not keyword or not keyword.strip():
            logger.warning("Empty keyword provided for search")
            return []

        # 기본 쿼리: multi_match로 title과 content 검색
        must_query = {
            "multi_match": {
                "query": keyword.strip(),
                "fields": ["title^2", "content"],  # title에 2배 가중치
                "type": "best_fields",
            }
        }

        # 쿼리 구성
        if published_after:
            if isinstance(published_after, datetime):
                published_after_str = published_after.isoformat()
            else:
                published_after_str = published_after

            query = {
                "size": size,
                "query": {
                    "bool": {
                        "must": [must_query],
                        "filter": [
                            {
                                "range": {
                                    "published_at": {
                                        "gte": published_after_str,
                                    }
                                }
                            }
                        ],
                    }
                },
                "_source": ["news_id", "title", "published_at"],
            }
        else:
            query = {
                "size": size,
                "query": must_query,
                "_source": ["news_id", "title", "published_at"],
            }

        try:
            response = self.client.search(index=self.NEWS_INDEX_NAME, body=query)

            results = []
            for hit in response.get("hits", {}).get("hits", []):
                score = hit.get("_score", 0.0)

                # min_score 필터링
                if min_score is not None and score < min_score:
                    continue

                source = hit.get("_source", {})
                results.append(
                    {
                        "news_id": source.get("news_id"),
                        "title": source.get("title", ""),
                        "score": score,
                        "published_at": source.get("published_at"),
                    }
                )

            logger.info(f"Found {len(results)} news articles for keyword: {keyword}")
            return results

        except Exception as e:
            logger.error(f"Failed to search news by keyword: {str(e)}")
            return []
