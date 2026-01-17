#!/usr/bin/env python
"""
키워드 빈도 추출 품질 테스트 스크립트

추출된 키워드가 실제로 의미 있는지 테스트합니다:
1. 키워드가 실제 뉴스 내용과 관련이 있는지 검증
2. 불용어 필터링이 제대로 작동하는지 확인
3. 의미 없는 키워드(숫자, 짧은 단어 등)가 제외되는지 확인
4. 샘플 뉴스와 키워드 매칭 테스트
5. 키워드의 빈도수와 문서 수의 합리성 확인
"""

import os
import sys
import django
from pathlib import Path
import re
from typing import Dict, List, Any, Tuple
from datetime import timedelta

# 프로젝트 루트 디렉토리를 Python path에 추가
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from news.services.opensearch import OpenSearchService
from news.models import News
from django.utils import timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KeywordQualityTest:
    """키워드 품질 테스트 클래스"""

    def __init__(self):
        self.opensearch = OpenSearchService()
        self.results: List[Dict[str, Any]] = []

    def get_sample_news(self, days: int = 7, limit: int = 10) -> List[News]:
        """샘플 뉴스 조회"""
        published_after = timezone.now() - timedelta(days=days)
        return list(
            News.objects.filter(
                published_at__gte=published_after,
                is_deleted=False,
                content__isnull=False,
            )
            .exclude(content="")
            .order_by("-published_at")[:limit]
        )

    def check_keyword_in_content(
        self, keyword: str, news_list: List[News]
    ) -> Tuple[int, List[str]]:
        """키워드가 실제 뉴스 내용에 포함되어 있는지 확인"""
        matched_count = 0
        matched_news_titles = []

        for news in news_list:
            if news.content and keyword in news.content:
                matched_count += 1
                matched_news_titles.append(news.title[:50])

        return matched_count, matched_news_titles

    def analyze_keyword_quality(
        self, keywords: List[Dict[str, Any]], sample_news: List[News]
    ) -> Dict[str, Any]:
        """키워드 품질 분석"""
        analysis = {
            "total_keywords": len(keywords),
            "valid_keywords": [],
            "invalid_keywords": [],
            "meaningless_keywords": [],
            "stopwords_found": [],
            "statistics": {
                "avg_doc_count": 0,
                "min_doc_count": 0,
                "max_doc_count": 0,
            },
        }

        if not keywords:
            return analysis

        # 통계 계산
        doc_counts = [kw["doc_count"] for kw in keywords]
        analysis["statistics"] = {
            "avg_doc_count": sum(doc_counts) / len(doc_counts),
            "min_doc_count": min(doc_counts),
            "max_doc_count": max(doc_counts),
        }

        # 불용어 리스트 (키워드 추출 로직과 동일)
        stopwords = {
            "이",
            "가",
            "을",
            "를",
            "의",
            "에",
            "에서",
            "으로",
            "로",
            "와",
            "과",
            "도",
            "만",
            "은",
            "는",
            "까지",
            "부터",
            "보다",
            "처럼",
            "같이",
            "만큼",
            "하고",
            "며",
            "지만",
            "나",
            "너",
            "우리",
            "당신",
            "그",
            "그녀",
            "이것",
            "그것",
            "저것",
            "것",
            "수",
            "등",
            "더",
            "또",
            "및",
            "또는",
            "혹은",
            "대한",
            "관한",
            "위한",
            "따른",
            "의한",
            "해당",
            "각",
            "여러",
            "것을",
            "있는",
        }

        # 각 키워드 분석
        for kw_data in keywords:
            keyword = kw_data.get("keyword", "")
            doc_count = kw_data.get("doc_count", 0)

            # 빈 키워드 체크
            if not keyword or len(keyword.strip()) == 0:
                analysis["invalid_keywords"].append(
                    {"keyword": keyword, "reason": "empty_keyword"}
                )
                continue

            # 불용어 체크
            if keyword.lower() in stopwords:
                analysis["stopwords_found"].append(
                    {"keyword": keyword, "doc_count": doc_count}
                )
                continue

            # 숫자 체크
            if keyword.isdigit() or re.match(r"^\d{1,4}$", keyword):
                analysis["meaningless_keywords"].append(
                    {"keyword": keyword, "reason": "numeric", "doc_count": doc_count}
                )
                continue

            # 길이 체크 (너무 짧은 키워드)
            if len(keyword) <= 1:
                analysis["meaningless_keywords"].append(
                    {"keyword": keyword, "reason": "too_short", "doc_count": doc_count}
                )
                continue

            # 실제 뉴스 내용과 매칭 확인
            matched_count, matched_titles = self.check_keyword_in_content(
                keyword, sample_news
            )

            # 키워드 품질 평가
            if matched_count > 0:
                # 실제 뉴스 내용에 포함된 경우
                analysis["valid_keywords"].append(
                    {
                        "keyword": keyword,
                        "doc_count": doc_count,
                        "matched_in_sample": matched_count,
                        "matched_news_titles": matched_titles[:3],  # 처음 3개만
                    }
                )
            else:
                # 샘플 뉴스에 포함되지 않았지만 doc_count가 있는 경우
                # (다른 뉴스에 포함되어 있을 수 있음)
                if doc_count >= 2:
                    analysis["valid_keywords"].append(
                        {
                            "keyword": keyword,
                            "doc_count": doc_count,
                            "matched_in_sample": 0,
                            "note": "not_in_sample_but_has_doc_count",
                        }
                    )
                else:
                    analysis["invalid_keywords"].append(
                        {
                            "keyword": keyword,
                            "reason": "low_doc_count_and_not_in_sample",
                            "doc_count": doc_count,
                        }
                    )

        return analysis

    def test_keyword_meaningfulness(
        self, size: int = 20, days: int = 7, min_doc_count: int = 2
    ) -> Dict[str, Any]:
        """키워드 의미성 테스트"""
        logger.info("=" * 60)
        logger.info(f"키워드 의미성 테스트 시작 (size={size}, days={days})")
        logger.info("=" * 60)

        # 샘플 뉴스 조회
        sample_news = self.get_sample_news(days=days, limit=20)
        logger.info(f"샘플 뉴스 {len(sample_news)}개 조회 완료")

        if not sample_news:
            logger.warning("샘플 뉴스가 없습니다. 테스트를 종료합니다.")
            return {"error": "no_sample_news"}

        # 키워드 추출
        published_after = timezone.now() - timedelta(days=days)
        keywords = self.opensearch.get_top_keywords(
            size=size,
            published_after=published_after,
            min_doc_count=min_doc_count,
        )

        logger.info(f"추출된 키워드: {len(keywords)}개")
        for kw in keywords[:10]:
            logger.info(f"  - {kw['keyword']} (doc_count: {kw['doc_count']})")

        # 품질 분석
        analysis = self.analyze_keyword_quality(keywords, sample_news)

        # 결과 출력
        logger.info("\n" + "-" * 60)
        logger.info("키워드 품질 분석 결과")
        logger.info("-" * 60)
        logger.info(f"전체 키워드 수: {analysis['total_keywords']}")
        logger.info(f"유효한 키워드 수: {len(analysis['valid_keywords'])}")
        logger.info(f"무효한 키워드 수: {len(analysis['invalid_keywords'])}")
        logger.info(f"의미 없는 키워드 수: {len(analysis['meaningless_keywords'])}")
        logger.info(f"불용어 발견 수: {len(analysis['stopwords_found'])}")

        logger.info("\n통계:")
        stats = analysis["statistics"]
        logger.info(f"  평균 문서 수: {stats['avg_doc_count']:.2f}")
        logger.info(f"  최소 문서 수: {stats['min_doc_count']}")
        logger.info(f"  최대 문서 수: {stats['max_doc_count']}")

        if analysis["valid_keywords"]:
            logger.info("\n유효한 키워드 (상위 10개):")
            for kw in analysis["valid_keywords"][:10]:
                logger.info(
                    f"  - {kw['keyword']} (doc_count: {kw['doc_count']}, "
                    f"matched_in_sample: {kw.get('matched_in_sample', 0)})"
                )

        if analysis["invalid_keywords"]:
            logger.info("\n무효한 키워드:")
            for kw in analysis["invalid_keywords"][:10]:
                logger.info(f"  - {kw['keyword']} (이유: {kw['reason']})")

        if analysis["meaningless_keywords"]:
            logger.info("\n의미 없는 키워드:")
            for kw in analysis["meaningless_keywords"][:10]:
                logger.info(
                    f"  - {kw['keyword']} (이유: {kw['reason']}, "
                    f"doc_count: {kw.get('doc_count', 0)})"
                )

        if analysis["stopwords_found"]:
            logger.warning("\n⚠️  불용어가 발견되었습니다 (필터링 실패):")
            for kw in analysis["stopwords_found"]:
                logger.warning(f"  - {kw['keyword']} (doc_count: {kw['doc_count']})")

        return {
            "test_type": "keyword_meaningfulness",
            "parameters": {"size": size, "days": days, "min_doc_count": min_doc_count},
            "sample_news_count": len(sample_news),
            "analysis": analysis,
        }

    def test_keyword_relevance(self, days: int = 7) -> Dict[str, Any]:
        """키워드와 뉴스 내용의 관련성 테스트"""
        logger.info("=" * 60)
        logger.info("키워드-뉴스 관련성 테스트 시작")
        logger.info("=" * 60)

        # 샘플 뉴스 조회
        sample_news = self.get_sample_news(days=days, limit=30)
        logger.info(f"샘플 뉴스 {len(sample_news)}개 조회 완료")

        if len(sample_news) < 5:
            logger.warning("샘플 뉴스가 부족합니다. 테스트를 종료합니다.")
            return {"error": "insufficient_sample_news"}

        # 키워드 추출
        published_after = timezone.now() - timedelta(days=days)
        keywords = self.opensearch.get_top_keywords(
            size=30, published_after=published_after, min_doc_count=2
        )

        # 각 키워드에 대해 관련 뉴스 찾기
        relevance_results = []
        for kw_data in keywords[:15]:  # 상위 15개만 테스트
            keyword = kw_data.get("keyword", "")
            doc_count = kw_data.get("doc_count", 0)

            matched_count, matched_titles = self.check_keyword_in_content(
                keyword, sample_news
            )

            relevance_score = (
                matched_count / len(sample_news) if sample_news else 0
            ) * 100

            relevance_results.append(
                {
                    "keyword": keyword,
                    "doc_count": doc_count,
                    "matched_in_sample": matched_count,
                    "relevance_score": relevance_score,
                    "matched_news_titles": matched_titles[:3],
                }
            )

        # 관련성 점수 기준 정렬
        relevance_results.sort(
            key=lambda x: (x["relevance_score"], x["doc_count"]), reverse=True
        )

        # 결과 출력
        logger.info("\n키워드-뉴스 관련성 결과:")
        logger.info("-" * 60)
        for i, result in enumerate(relevance_results[:10], 1):
            logger.info(
                f"\n{i}. {result['keyword']} "
                f"(doc_count: {result['doc_count']}, "
                f"relevance: {result['relevance_score']:.1f}%)"
            )
            if result["matched_news_titles"]:
                logger.info("  관련 뉴스:")
                for title in result["matched_news_titles"]:
                    logger.info(f"    - {title}")

        # 통계
        avg_relevance = (
            sum(r["relevance_score"] for r in relevance_results)
            / len(relevance_results)
            if relevance_results
            else 0
        )
        logger.info(f"\n평균 관련성 점수: {avg_relevance:.1f}%")

        return {
            "test_type": "keyword_relevance",
            "parameters": {"days": days},
            "sample_news_count": len(sample_news),
            "avg_relevance_score": avg_relevance,
            "results": relevance_results,
        }

    def test_stopwords_filtering(self) -> Dict[str, Any]:
        """불용어 필터링 테스트"""
        logger.info("=" * 60)
        logger.info("불용어 필터링 테스트 시작")
        logger.info("=" * 60)

        # 키워드 추출
        published_after = timezone.now() - timedelta(days=7)
        keywords = self.opensearch.get_top_keywords(
            size=50, published_after=published_after, min_doc_count=1
        )

        # 불용어 리스트
        stopwords = {
            "이",
            "가",
            "을",
            "를",
            "의",
            "에",
            "에서",
            "으로",
            "로",
            "와",
            "과",
            "도",
            "만",
            "은",
            "는",
            "까지",
            "부터",
            "보다",
            "처럼",
            "같이",
            "만큼",
            "하고",
            "며",
            "지만",
            "나",
            "너",
            "우리",
            "당신",
            "그",
            "그녀",
            "이것",
            "그것",
            "저것",
            "것",
            "수",
            "등",
            "더",
            "또",
            "및",
            "또는",
            "혹은",
            "대한",
            "관한",
            "위한",
            "따른",
            "의한",
            "해당",
            "각",
            "여러",
            "것을",
            "있는",
        }

        # 불용어 필터링 체크
        found_stopwords = []
        for kw_data in keywords:
            keyword = kw_data.get("keyword", "")
            if keyword.lower() in stopwords:
                found_stopwords.append(
                    {"keyword": keyword, "doc_count": kw_data.get("doc_count", 0)}
                )

        if found_stopwords:
            logger.warning(f"⚠️  불용어 {len(found_stopwords)}개 발견:")
            for sw in found_stopwords:
                logger.warning(f"  - {sw['keyword']} (doc_count: {sw['doc_count']})")
        else:
            logger.info("✓ 불용어 필터링이 정상적으로 작동합니다.")

        return {
            "test_type": "stopwords_filtering",
            "total_keywords": len(keywords),
            "found_stopwords_count": len(found_stopwords),
            "found_stopwords": found_stopwords,
            "filtering_working": len(found_stopwords) == 0,
        }

    def print_summary(self, test_results: List[Dict[str, Any]]) -> None:
        """테스트 결과 요약 출력"""
        logger.info("\n" + "=" * 60)
        logger.info("키워드 품질 테스트 결과 요약")
        logger.info("=" * 60)

        for test_result in test_results:
            test_type = test_result.get("test_type", "unknown")
            logger.info(f"\n[{test_type}]")

            if test_type == "keyword_meaningfulness":
                analysis = test_result.get("analysis", {})
                logger.info(f"  전체 키워드 수: {analysis.get('total_keywords', 0)}")
                logger.info(
                    f"  유효한 키워드 수: {len(analysis.get('valid_keywords', []))}"
                )
                logger.info(
                    f"  무효한 키워드 수: {len(analysis.get('invalid_keywords', []))}"
                )
                logger.info(
                    f"  의미 없는 키워드 수: {len(analysis.get('meaningless_keywords', []))}"
                )
                logger.info(
                    f"  불용어 발견 수: {len(analysis.get('stopwords_found', []))}"
                )

                valid_count = len(analysis.get("valid_keywords", []))
                total_count = analysis.get("total_keywords", 0)
                if total_count > 0:
                    quality_score = (valid_count / total_count) * 100
                    logger.info(f"  품질 점수: {quality_score:.1f}%")

            elif test_type == "keyword_relevance":
                logger.info(
                    f"  평균 관련성 점수: {test_result.get('avg_relevance_score', 0):.1f}%"
                )
                logger.info(
                    f"  샘플 뉴스 수: {test_result.get('sample_news_count', 0)}"
                )

            elif test_type == "stopwords_filtering":
                is_working = test_result.get("filtering_working", False)
                logger.info(f"  불용어 필터링: {'✓ 정상' if is_working else '✗ 실패'}")
                logger.info(
                    f"  발견된 불용어 수: {test_result.get('found_stopwords_count', 0)}"
                )

        logger.info("\n" + "=" * 60)

    def run_all_tests(self) -> None:
        """모든 테스트 실행"""
        logger.info("키워드 품질 테스트 시작")
        logger.info("=" * 60)

        test_results = []

        # 1. 키워드 의미성 테스트
        try:
            result = self.test_keyword_meaningfulness(size=20, days=7, min_doc_count=2)
            if "error" not in result:
                test_results.append(result)
        except Exception as e:
            logger.error(f"키워드 의미성 테스트 실패: {e}")

        # 2. 키워드-뉴스 관련성 테스트
        try:
            result = self.test_keyword_relevance(days=7)
            if "error" not in result:
                test_results.append(result)
        except Exception as e:
            logger.error(f"키워드-뉴스 관련성 테스트 실패: {e}")

        # 3. 불용어 필터링 테스트
        try:
            result = self.test_stopwords_filtering()
            test_results.append(result)
        except Exception as e:
            logger.error(f"불용어 필터링 테스트 실패: {e}")

        # 결과 요약 출력
        self.print_summary(test_results)


if __name__ == "__main__":
    tester = KeywordQualityTest()
    tester.run_all_tests()
