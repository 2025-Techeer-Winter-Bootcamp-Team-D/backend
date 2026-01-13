"""
뉴스 크롤링 Celery 태스크

OpenSearch 통합 및 클러스터링 기반 중복 제거를 포함한 전체 파이프라인을 구현합니다.
"""

from celery import shared_task
from django.utils import timezone
from django.db import transaction
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from news.models import News, CrawlJob
from news.services.naver_api import NaverSearchService
from news.services.jina_api import JinaReaderService
from news.services.refiner import RefineService
from news.services.summarizer import SummarizeService
from news.services.embedding import EmbeddingService
from news.services.opensearch import OpenSearchService
from news.utils.clustering import NewsClusteringService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def crawl_news_task(self, job_id, keywords, max_articles_per_keyword=10):
    """
    뉴스 크롤링 및 요약 Celery 태스크

    전체 파이프라인:
    1. CrawlJob을 running으로 업데이트
    2. 키워드별 병렬 검색 (ThreadPoolExecutor 사용):
       - 모든 키워드에 대해 Naver API 검색을 병렬로 실행
       - 최대 4개 스레드로 동시 검색 (API 레이트 리밋 고려)
    3. 각 키워드의 검색 결과 처리 (순차 처리 - DB 일관성 유지):
       - 각 기사별:
         * URL 중복 체크 (News.url unique 제약)
         * jina.ai로 본문 추출
         * RefineService로 본문 정제
         * 요약 생성 및 벡터 임베딩
         * PostgreSQL 저장
    4. 클러스터링 및 중복 제거:
       - 모든 임베딩 수집
       - DBSCAN 클러스터링 실행
       - 중복 제거 (대표 기사 선택)
       - 유지할 뉴스만 OpenSearch에 저장
    5. CrawlJob을 completed/failed로 업데이트

    Args:
        job_id: CrawlJob의 ID
        keywords: 검색 키워드 리스트
        max_articles_per_keyword: 키워드당 최대 기사 수 (기본값: 10)
    """
    try:
        # 1. CrawlJob 조회 및 상태 업데이트
        crawl_job = CrawlJob.objects.get(id=job_id)
        crawl_job.mark_as_running()

        logger.info(
            f"[CrawlJob {job_id}] 크롤링 시작: 키워드={keywords}, "
            f"최대 기사 수={max_articles_per_keyword}"
        )

        # 서비스 초기화
        naver_service = NaverSearchService()
        jina_service = JinaReaderService()
        refiner_service = RefineService()
        summarizer_service = SummarizeService()
        embedding_service = EmbeddingService()
        opensearch_service = OpenSearchService()
        clustering_service = NewsClusteringService(eps=0.1, min_samples=2)

        # 전체 처리 데이터 수집용
        all_news_data = (
            []
        )  # 뉴스 정보 (title, url, summary, published_at, content, embedding)
        all_embeddings = []  # 임베딩 벡터 리스트 (클러스터링용)

        total_articles = 0
        successful_articles = 0
        failed_articles = 0

        # 2. 키워드별 검색 결과 수집 (병렬 처리)
        def search_keyword(keyword: str) -> tuple[str, List[Dict[str, Any]]]:
            """키워드별 뉴스 검색 (병렬 처리용)"""
            logger.info(f"[CrawlJob {job_id}] 키워드 '{keyword}' 검색 시작")
            try:
                search_results = naver_service.search(
                    query=keyword, display_count=max_articles_per_keyword, sort="date"
                )
                if search_results:
                    logger.info(
                        f"[CrawlJob {job_id}] 키워드 '{keyword}': {len(search_results)}개 기사 발견"
                    )
                else:
                    logger.warning(
                        f"[CrawlJob {job_id}] 키워드 '{keyword}' 검색 결과 없음"
                    )
                return keyword, search_results or []
            except Exception as e:
                logger.error(
                    f"[CrawlJob {job_id}] 키워드 '{keyword}' 검색 중 오류: {str(e)}",
                    exc_info=True,
                )
                return keyword, []

        # 병렬로 모든 키워드 검색 실행
        logger.info(
            f"[CrawlJob {job_id}] 키워드 병렬 검색 시작: {len(keywords)}개 키워드"
        )
        keyword_results: Dict[str, List[Dict[str, Any]]] = {}

        # ThreadPoolExecutor로 키워드 검색 병렬 처리
        max_workers = min(len(keywords), 4)  # 최대 4개 스레드
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_keyword = {
                executor.submit(search_keyword, keyword): keyword
                for keyword in keywords
            }

            for future in as_completed(future_to_keyword):
                keyword, results = future.result()
                keyword_results[keyword] = results

        logger.info(
            f"[CrawlJob {job_id}] 키워드 병렬 검색 완료: "
            f"총 {sum(len(results) for results in keyword_results.values())}개 기사 발견"
        )

        # 3. 각 키워드의 검색 결과 처리 (순차 처리 - DB 트랜잭션 일관성 유지)
        for keyword, search_results in keyword_results.items():
            if not search_results:
                continue

            # 각 기사별 처리
            for article in search_results:
                total_articles += 1

                try:
                    # URL 중복 체크
                    url = article.get("link")
                    if not url:
                        logger.warning(f"[CrawlJob {job_id}] URL이 없는 기사 건너뜀")
                        failed_articles += 1
                        continue

                    # 기존 뉴스 중복 체크 (삭제된 것 포함)
                    if News.objects.filter(url=url).exists():
                        logger.info(
                            f"[CrawlJob {job_id}] 중복 URL 건너뜀: {url[:50]}..."
                        )
                        # 중복은 실패가 아니라 건너뛰기로 처리 (통계에 포함하지 않음)
                        continue

                    # jina.ai로 본문 추출
                    logger.debug(f"[CrawlJob {job_id}] 본문 추출 중: {url[:50]}...")
                    raw_content = jina_service.extract_content(url)

                    if not raw_content:
                        logger.warning(
                            f"[CrawlJob {job_id}] 본문 추출 실패: {url[:50]}..."
                        )
                        failed_articles += 1
                        continue

                    # RefineService로 본문 정제
                    logger.debug(f"[CrawlJob {job_id}] 본문 정제 중: {url[:50]}...")
                    refined_content = refiner_service.get_refined_body(raw_content)

                    if not refined_content or len(refined_content.strip()) < 30:
                        logger.warning(
                            f"[CrawlJob {job_id}] 정제된 본문이 너무 짧음 (30자 미만): {url[:50]}..."
                        )
                        failed_articles += 1
                        continue

                    # 병렬 처리: 요약 생성 및 벡터 임베딩
                    logger.debug(f"[CrawlJob {job_id}] 요약 생성 중: {url[:50]}...")
                    summary_result = summarizer_service.get_summary_only(
                        refined_content
                    )
                    summary_text = summary_result.get("summary", "")

                    logger.debug(
                        f"[CrawlJob {job_id}] 벡터 임베딩 생성 중: {url[:50]}..."
                    )
                    embeddings = embedding_service.get_embeddings_batch(
                        [refined_content]
                    )

                    if not embeddings or embeddings[0] is None:
                        logger.warning(
                            f"[CrawlJob {job_id}] 벡터 임베딩 생성 실패: {url[:50]}..."
                        )
                        failed_articles += 1
                        continue

                    embedding_vector = embeddings[0]

                    # PostgreSQL에 뉴스 저장 (중복 체크 후)
                    try:
                        news, created = News.objects.get_or_create(
                            url=url,
                            defaults={
                                "title": article.get("title", ""),
                                "summary": summary_text,
                                "published_at": article.get("published_at"),
                            },
                        )

                        if not created:
                            # 이미 존재하는 경우 업데이트
                            logger.info(
                                f"[CrawlJob {job_id}] 기존 뉴스 업데이트: news_id={news.news_id}"
                            )
                            news.title = article.get("title", "")
                            news.summary = summary_text
                            news.published_at = article.get("published_at")
                            news.is_deleted = False  # 삭제된 경우 복구
                            news.save()
                        else:
                            logger.info(
                                f"[CrawlJob {job_id}] 뉴스 저장 완료: news_id={news.news_id}, "
                                f"title={news.title[:50]}..."
                            )
                    except Exception as db_error:
                        logger.error(
                            f"[CrawlJob {job_id}] 뉴스 저장 실패: {str(db_error)}"
                        )
                        failed_articles += 1
                        continue

                    # 클러스터링을 위한 데이터 수집
                    all_news_data.append(
                        {
                            "news_id": news.news_id,
                            "title": news.title,
                            "content": refined_content,
                            "content_vector": embedding_vector,  # OpenSearchService에서 기대하는 키 이름
                            "published_at": news.published_at,
                            "content_length": len(refined_content),
                        }
                    )
                    all_embeddings.append(embedding_vector)

                    successful_articles += 1

                except Exception as e:
                    logger.error(
                        f"[CrawlJob {job_id}] 기사 처리 중 오류 발생: {str(e)}",
                        exc_info=True,
                    )
                    failed_articles += 1
                    continue

        # 4. 클러스터링 및 중복 제거
        logger.info(
            f"[CrawlJob {job_id}] 클러스터링 시작: 총 {len(all_news_data)}개 기사"
        )

        if len(all_news_data) > 1:
            # DBSCAN 클러스터링 실행
            labels = clustering_service.cluster_news(all_embeddings)

            # 중복 제거 (대표 기사 선택)
            news_items = [
                {
                    "index": idx,
                    "published_at": item["published_at"],
                    "content_length": item["content_length"],
                }
                for idx, item in enumerate(all_news_data)
            ]

            keep_indices, duplicate_indices = clustering_service.deduplicate_by_cluster(
                labels, news_items, strategy="latest_longest"
            )

            logger.info(
                f"[CrawlJob {job_id}] 클러스터링 완료: "
                f"유지={len(keep_indices)}개, 제거={len(duplicate_indices)}개"
            )

            # 유지할 뉴스만 OpenSearch에 저장
            news_to_save = [
                all_news_data[idx] for idx in keep_indices if idx < len(all_news_data)
            ]

            if news_to_save:
                logger.info(
                    f"[CrawlJob {job_id}] OpenSearch 저장 시작: {len(news_to_save)}개 기사"
                )

                # 배치로 OpenSearch에 저장
                opensearch_service.save_news_vectors_batch(news_to_save)

                logger.info(
                    f"[CrawlJob {job_id}] OpenSearch 저장 완료: {len(news_to_save)}개 기사"
                )

            # 중복 뉴스는 PostgreSQL에서 소프트 삭제
            duplicate_news_ids = [
                all_news_data[idx]["news_id"]
                for idx in duplicate_indices
                if idx < len(all_news_data)
            ]

            if duplicate_news_ids:
                logger.info(
                    f"[CrawlJob {job_id}] 중복 뉴스 소프트 삭제: {len(duplicate_news_ids)}개"
                )
                News.objects.filter(news_id__in=duplicate_news_ids).update(
                    is_deleted=True, updated_at=timezone.now()
                )

        elif len(all_news_data) == 1:
            # 기사가 1개만 있으면 바로 OpenSearch에 저장
            logger.info(f"[CrawlJob {job_id}] 단일 기사 OpenSearch 저장")
            opensearch_service.save_news_vectors_batch(all_news_data)

        # 5. CrawlJob 통계 업데이트 및 완료 처리
        crawl_job.total_articles = total_articles
        crawl_job.successful_articles = successful_articles
        crawl_job.failed_articles = failed_articles
        crawl_job.save()  # 통계를 먼저 저장
        crawl_job.mark_as_completed()  # 상태만 업데이트

        logger.info(
            f"[CrawlJob {job_id}] 크롤링 완료: "
            f"총={total_articles}, 성공={successful_articles}, 실패={failed_articles}"
        )

    except CrawlJob.DoesNotExist:
        logger.error(f"[CrawlJob {job_id}] CrawlJob을 찾을 수 없습니다.")
        raise

    except Exception as e:
        logger.error(f"[CrawlJob {job_id}] 크롤링 태스크 실패: {str(e)}", exc_info=True)

        # CrawlJob 실패 처리
        try:
            crawl_job = CrawlJob.objects.get(id=job_id)
            crawl_job.mark_as_failed(str(e))
        except CrawlJob.DoesNotExist:
            pass

        # 재시도 로직
        raise self.retry(exc=e, countdown=60)  # 60초 후 재시도


@shared_task
def scheduled_crawl_news(keywords=None, max_articles_per_keyword=10):
    """
    Celery Beat 스케줄링용 래퍼 태스크

    CrawlJob을 자동으로 생성하고 crawl_news_task를 호출합니다.

    Args:
        keywords: 검색 키워드 리스트 (None이면 기본 키워드 사용)
        max_articles_per_keyword: 키워드당 최대 기사 수
    """
    if keywords is None:
        # 기본 키워드 (설정에서 변경 가능)
        keywords = ["AI", "반도체", "삼성전자", "SK하이닉스"]

    # CrawlJob 생성
    crawl_job = CrawlJob.objects.create(
        keywords=keywords,
        status="pending",
    )

    logger.info(
        f"[Scheduled Crawl] CrawlJob {crawl_job.id} 생성: "
        f"키워드={keywords}, 최대 기사 수={max_articles_per_keyword}"
    )

    # 실제 크롤링 태스크 호출
    crawl_news_task.delay(crawl_job.id, keywords, max_articles_per_keyword)

    return crawl_job.id
