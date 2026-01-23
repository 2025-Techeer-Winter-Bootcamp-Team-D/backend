# companies/tests/e2e/test_phase1_infrastructure.py

"""
Phase 1: 인프라 검증 테스트
- PostgreSQL (TimescaleDB)
- Redis
- RabbitMQ
- OpenSearch
"""

import time
import logging
from typing import Dict, Any
from django.db import connection
from django.core.cache import cache
from opensearchpy import OpenSearch
from config.settings import (
    OPENSEARCH_HOST,
    OPENSEARCH_USE_SSL,
    OPENSEARCH_VERIFY_CERTS,
    OPENSEARCH_USERNAME,
    OPENSEARCH_PASSWORD,
    CELERY_BROKER_URL,
)
import pika

logger = logging.getLogger(__name__)


class Phase1InfrastructureTest:
    """Phase 1: 인프라 검증 테스트"""

    @staticmethod
    def run() -> Dict[str, Any]:
        """Phase 1 전체 테스트 실행"""
        start_time = time.time()
        results = {
            "status": "success",
            "duration": 0,
            "checks": {}
        }

        try:
            # PostgreSQL 검증
            results["checks"]["postgresql"] = Phase1InfrastructureTest._check_postgresql()

            # Redis 검증
            results["checks"]["redis"] = Phase1InfrastructureTest._check_redis()

            # RabbitMQ 검증
            results["checks"]["rabbitmq"] = Phase1InfrastructureTest._check_rabbitmq()

            # OpenSearch 검증
            results["checks"]["opensearch"] = Phase1InfrastructureTest._check_opensearch()

        except Exception as e:
            logger.error(f"Phase 1 실행 중 오류 발생: {str(e)}")
            results["status"] = "error"
            results["error"] = str(e)

        results["duration"] = round(time.time() - start_time, 2)
        return results

    @staticmethod
    def _check_postgresql() -> Dict[str, Any]:
        """PostgreSQL (TimescaleDB) 연결 확인"""
        start_time = time.time()
        try:
            with connection.cursor() as cursor:
                # 간단한 쿼리 실행
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

                # TimescaleDB 확장 확인
                cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
                timescale = cursor.fetchone()

                if result and result[0] == 1:
                    return {
                        "status": "ok",
                        "duration": round(time.time() - start_time, 2),
                        "timescaledb_installed": bool(timescale)
                    }
                else:
                    return {
                        "status": "error",
                        "duration": round(time.time() - start_time, 2),
                        "error": "Query returned unexpected result"
                    }
        except Exception as e:
            logger.error(f"PostgreSQL 연결 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }

    @staticmethod
    def _check_redis() -> Dict[str, Any]:
        """Redis 연결 확인"""
        start_time = time.time()
        try:
            # PING 명령 실행
            cache.set("e2e_test_key", "test_value", timeout=10)
            value = cache.get("e2e_test_key")
            cache.delete("e2e_test_key")

            if value == "test_value":
                return {
                    "status": "ok",
                    "duration": round(time.time() - start_time, 2)
                }
            else:
                return {
                    "status": "error",
                    "duration": round(time.time() - start_time, 2),
                    "error": "Redis SET/GET test failed"
                }
        except Exception as e:
            logger.error(f"Redis 연결 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }

    @staticmethod
    def _check_rabbitmq() -> Dict[str, Any]:
        """RabbitMQ 연결 확인"""
        start_time = time.time()
        connection = None
        try:
            # RabbitMQ 연결 파라미터 파싱
            params = pika.URLParameters(CELERY_BROKER_URL)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            # 테스트용 큐 생성 및 삭제
            test_queue = "e2e_test_queue"
            channel.queue_declare(queue=test_queue, auto_delete=True)

            # 메시지 publish/consume 테스트
            test_message = "e2e_test_message"
            channel.basic_publish(
                exchange='',
                routing_key=test_queue,
                body=test_message
            )

            # 메시지 수신
            method_frame, header_frame, body = channel.basic_get(queue=test_queue)

            if body and body.decode() == test_message:
                # ACK 전송 및 큐 삭제
                channel.basic_ack(method_frame.delivery_tag)
                channel.queue_delete(queue=test_queue)

                return {
                    "status": "ok",
                    "duration": round(time.time() - start_time, 2)
                }
            else:
                return {
                    "status": "error",
                    "duration": round(time.time() - start_time, 2),
                    "error": "Message publish/consume test failed"
                }

        except Exception as e:
            logger.error(f"RabbitMQ 연결 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }
        finally:
            if connection and not connection.is_closed:
                connection.close()

    @staticmethod
    def _check_opensearch() -> Dict[str, Any]:
        """OpenSearch 연결 확인"""
        start_time = time.time()
        try:
            # OpenSearch 클라이언트 생성
            auth = None
            if OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD:
                auth = (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

            client = OpenSearch(
                hosts=[OPENSEARCH_HOST],
                http_auth=auth,
                use_ssl=OPENSEARCH_USE_SSL,
                verify_certs=OPENSEARCH_VERIFY_CERTS,
                ssl_show_warn=False
            )

            # 클러스터 상태 조회
            cluster_health = client.cluster.health()

            # 간단한 검색 쿼리 테스트 (존재하지 않는 인덱스도 OK)
            _ = client.search(
                index="_all",
                body={"query": {"match_all": {}}, "size": 0}
            )

            return {
                "status": "ok",
                "duration": round(time.time() - start_time, 2),
                "cluster_status": cluster_health.get("status"),
                "cluster_name": cluster_health.get("cluster_name")
            }

        except Exception as e:
            logger.error(f"OpenSearch 연결 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }
