#!/usr/bin/env python
"""
키워드 빈도 추출 성능 테스트 스크립트

테스트 항목:
1. 다양한 파라미터 조합 테스트 (size, days, min_doc_count)
2. 응답 시간 측정
3. 데이터 처리량 측정
4. 동시 요청 테스트
5. 에러 핸들링 테스트
"""

import os
import sys
import django
from pathlib import Path
import time
import statistics
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

# 프로젝트 루트 디렉토리를 Python path에 추가
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from news.services.opensearch import OpenSearchService
from django.utils import timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KeywordFrequencyPerformanceTest:
    """키워드 빈도 추출 성능 테스트 클래스"""

    def __init__(self):
        self.opensearch = OpenSearchService()
        self.results: List[Dict[str, Any]] = []

    def test_single_request(
        self,
        size: int = 15,
        days: int = 7,
        min_doc_count: int = 2,
        exclude_keywords: List[str] = None,
    ) -> Dict[str, Any]:
        """단일 요청 성능 테스트"""
        published_after = timezone.now() - timedelta(days=days)

        start_time = time.time()
        try:
            keywords = self.opensearch.get_top_keywords(
                size=size,
                published_after=published_after,
                exclude_keywords=exclude_keywords,
                min_doc_count=min_doc_count,
            )
            elapsed_time = time.time() - start_time

            return {
                "success": True,
                "elapsed_time": elapsed_time,
                "keyword_count": len(keywords),
                "size": size,
                "days": days,
                "min_doc_count": min_doc_count,
                "keywords": keywords[:5],  # 처음 5개만 저장
            }
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Error in test_single_request: {e}")
            return {
                "success": False,
                "elapsed_time": elapsed_time,
                "error": str(e),
                "size": size,
                "days": days,
                "min_doc_count": min_doc_count,
            }

    def test_parameter_combinations(self) -> Dict[str, Any]:
        """다양한 파라미터 조합 테스트"""
        logger.info("=" * 60)
        logger.info("파라미터 조합 테스트 시작")
        logger.info("=" * 60)

        test_cases = [
            {"size": 10, "days": 1, "min_doc_count": 1},
            {"size": 15, "days": 7, "min_doc_count": 2},
            {"size": 20, "days": 7, "min_doc_count": 2},
            {"size": 30, "days": 7, "min_doc_count": 2},
            {"size": 50, "days": 7, "min_doc_count": 2},
            {"size": 15, "days": 1, "min_doc_count": 2},
            {"size": 15, "days": 3, "min_doc_count": 2},
            {"size": 15, "days": 14, "min_doc_count": 2},
            {"size": 15, "days": 30, "min_doc_count": 2},
            {"size": 15, "days": 7, "min_doc_count": 1},
            {"size": 15, "days": 7, "min_doc_count": 3},
            {"size": 15, "days": 7, "min_doc_count": 5},
            {"size": 15, "days": 7, "min_doc_count": 10},
        ]

        results = []
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n[{i}/{len(test_cases)}] 테스트: {test_case}")
            result = self.test_single_request(**test_case)
            results.append(result)

            if result["success"]:
                logger.info(
                    f"  ✓ 성공: {result['elapsed_time']:.3f}초, "
                    f"키워드 수: {result['keyword_count']}"
                )
            else:
                logger.error(f"  ✗ 실패: {result.get('error', 'Unknown error')}")

        return {
            "test_type": "parameter_combinations",
            "total_tests": len(test_cases),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results,
        }

    def test_concurrent_requests(
        self, num_requests: int = 10, size: int = 15, days: int = 7
    ) -> Dict[str, Any]:
        """동시 요청 성능 테스트"""
        logger.info("=" * 60)
        logger.info(f"동시 요청 테스트 시작 (요청 수: {num_requests})")
        logger.info("=" * 60)

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [
                executor.submit(
                    self.test_single_request, size=size, days=days, min_doc_count=2
                )
                for _ in range(num_requests)
            ]

            results = []
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                results.append(result)

                if result["success"]:
                    logger.info(
                        f"  [{i}/{num_requests}] 완료: {result['elapsed_time']:.3f}초"
                    )
                else:
                    logger.error(
                        f"  [{i}/{num_requests}] 실패: {result.get('error', 'Unknown')}"
                    )

        total_time = time.time() - start_time
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        elapsed_times = [r["elapsed_time"] for r in successful]

        return {
            "test_type": "concurrent_requests",
            "num_requests": num_requests,
            "total_time": total_time,
            "successful": len(successful),
            "failed": len(failed),
            "avg_elapsed_time": statistics.mean(elapsed_times) if elapsed_times else 0,
            "median_elapsed_time": (
                statistics.median(elapsed_times) if elapsed_times else 0
            ),
            "min_elapsed_time": min(elapsed_times) if elapsed_times else 0,
            "max_elapsed_time": max(elapsed_times) if elapsed_times else 0,
            "std_elapsed_time": (
                statistics.stdev(elapsed_times) if len(elapsed_times) > 1 else 0
            ),
            "requests_per_second": num_requests / total_time if total_time > 0 else 0,
            "results": results,
        }

    def test_repeated_requests(
        self, num_requests: int = 20, size: int = 15, days: int = 7
    ) -> Dict[str, Any]:
        """반복 요청 성능 테스트 (순차 실행)"""
        logger.info("=" * 60)
        logger.info(f"반복 요청 테스트 시작 (요청 수: {num_requests})")
        logger.info("=" * 60)

        start_time = time.time()
        results = []

        for i in range(1, num_requests + 1):
            result = self.test_single_request(size=size, days=days, min_doc_count=2)
            results.append(result)

            if result["success"]:
                logger.info(
                    f"  [{i}/{num_requests}] 완료: {result['elapsed_time']:.3f}초"
                )
            else:
                logger.error(
                    f"  [{i}/{num_requests}] 실패: {result.get('error', 'Unknown')}"
                )

        total_time = time.time() - start_time
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        elapsed_times = [r["elapsed_time"] for r in successful]

        return {
            "test_type": "repeated_requests",
            "num_requests": num_requests,
            "total_time": total_time,
            "successful": len(successful),
            "failed": len(failed),
            "avg_elapsed_time": statistics.mean(elapsed_times) if elapsed_times else 0,
            "median_elapsed_time": (
                statistics.median(elapsed_times) if elapsed_times else 0
            ),
            "min_elapsed_time": min(elapsed_times) if elapsed_times else 0,
            "max_elapsed_time": max(elapsed_times) if elapsed_times else 0,
            "std_elapsed_time": (
                statistics.stdev(elapsed_times) if len(elapsed_times) > 1 else 0
            ),
            "requests_per_second": num_requests / total_time if total_time > 0 else 0,
            "results": results,
        }

    def test_with_exclude_keywords(self) -> Dict[str, Any]:
        """제외 키워드 기능 테스트"""
        logger.info("=" * 60)
        logger.info("제외 키워드 기능 테스트 시작")
        logger.info("=" * 60)

        test_cases = [
            {"exclude_keywords": None},
            {"exclude_keywords": ["주식", "투자"]},
            {"exclude_keywords": ["주식", "투자", "시장", "경제", "증권"]},
            {
                "exclude_keywords": [
                    "주식",
                    "투자",
                    "시장",
                    "경제",
                    "증권",
                    "기업",
                    "회사",
                    "삼성",
                ]
            },
        ]

        results = []
        for i, test_case in enumerate(test_cases, 1):
            logger.info(
                f"\n[{i}/{len(test_cases)}] 제외 키워드: {test_case['exclude_keywords']}"
            )
            result = self.test_single_request(
                size=15, days=7, min_doc_count=2, **test_case
            )
            results.append(result)

            if result["success"]:
                logger.info(
                    f"  ✓ 성공: {result['elapsed_time']:.3f}초, "
                    f"키워드 수: {result['keyword_count']}"
                )
                if result.get("keywords"):
                    logger.info(
                        f"  상위 키워드: {[k['keyword'] for k in result['keywords'][:3]]}"
                    )

        return {
            "test_type": "exclude_keywords",
            "total_tests": len(test_cases),
            "successful": sum(1 for r in results if r["success"]),
            "failed": sum(1 for r in results if not r["success"]),
            "results": results,
        }

    def print_summary(self, test_results: List[Dict[str, Any]]) -> None:
        """테스트 결과 요약 출력"""
        logger.info("\n" + "=" * 60)
        logger.info("성능 테스트 결과 요약")
        logger.info("=" * 60)

        for test_result in test_results:
            test_type = test_result.get("test_type", "unknown")
            logger.info(f"\n[{test_type}]")

            if test_type == "parameter_combinations":
                logger.info(f"  전체 테스트: {test_result['total_tests']}")
                logger.info(f"  성공: {test_result['successful']}")
                logger.info(f"  실패: {test_result['failed']}")

                # 성공한 테스트의 평균 응답 시간
                successful = [r for r in test_result["results"] if r["success"]]
                if successful:
                    avg_time = statistics.mean([r["elapsed_time"] for r in successful])
                    logger.info(f"  평균 응답 시간: {avg_time:.3f}초")

            elif test_type in ["concurrent_requests", "repeated_requests"]:
                logger.info(f"  전체 요청 수: {test_result['num_requests']}")
                logger.info(f"  성공: {test_result['successful']}")
                logger.info(f"  실패: {test_result['failed']}")
                logger.info(f"  총 실행 시간: {test_result['total_time']:.3f}초")
                logger.info(
                    f"  평균 응답 시간: {test_result['avg_elapsed_time']:.3f}초"
                )
                logger.info(
                    f"  중간값 응답 시간: {test_result['median_elapsed_time']:.3f}초"
                )
                logger.info(
                    f"  최소 응답 시간: {test_result['min_elapsed_time']:.3f}초"
                )
                logger.info(
                    f"  최대 응답 시간: {test_result['max_elapsed_time']:.3f}초"
                )
                if test_result["std_elapsed_time"] > 0:
                    logger.info(f"  표준편차: {test_result['std_elapsed_time']:.3f}초")
                logger.info(
                    f"  초당 요청 수: {test_result['requests_per_second']:.2f} req/s"
                )

            elif test_type == "exclude_keywords":
                logger.info(f"  전체 테스트: {test_result['total_tests']}")
                logger.info(f"  성공: {test_result['successful']}")
                logger.info(f"  실패: {test_result['failed']}")

        logger.info("\n" + "=" * 60)

    def run_all_tests(self) -> None:
        """모든 테스트 실행"""
        logger.info("키워드 빈도 추출 성능 테스트 시작")
        logger.info("=" * 60)

        test_results = []

        # 1. 파라미터 조합 테스트
        try:
            result = self.test_parameter_combinations()
            test_results.append(result)
        except Exception as e:
            logger.error(f"파라미터 조합 테스트 실패: {e}")

        # 2. 반복 요청 테스트 (순차 실행)
        try:
            result = self.test_repeated_requests(num_requests=10)
            test_results.append(result)
        except Exception as e:
            logger.error(f"반복 요청 테스트 실패: {e}")

        # 3. 동시 요청 테스트
        try:
            result = self.test_concurrent_requests(num_requests=5)
            test_results.append(result)
        except Exception as e:
            logger.error(f"동시 요청 테스트 실패: {e}")

        # 4. 제외 키워드 기능 테스트
        try:
            result = self.test_with_exclude_keywords()
            test_results.append(result)
        except Exception as e:
            logger.error(f"제외 키워드 테스트 실패: {e}")

        # 결과 요약 출력
        self.print_summary(test_results)


if __name__ == "__main__":
    tester = KeywordFrequencyPerformanceTest()
    tester.run_all_tests()
