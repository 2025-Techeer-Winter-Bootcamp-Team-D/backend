"""
뉴스 Embedding 재생성 및 OpenSearch 저장 Management Command

DB의 content 필드를 이용해서 embedding부터 다시 생성하고 OpenSearch에 저장합니다.
크롤링이나 요약은 다시 하지 않습니다.

사용법:
    # 특정 뉴스 ID 재시도
    python manage.py retry_news_embedding --news-id 123

    # 여러 뉴스 ID 재시도
    python manage.py retry_news_embedding --news-id 123 124 125

    # content가 있지만 OpenSearch에 없는 뉴스 모두 재시도
    python manage.py retry_news_embedding --missing-only

    # 특정 기업의 뉴스만 재시도
    python manage.py retry_news_embedding --stock-code 005930 --missing-only

    # 최근 N일 이내 뉴스만 재시도
    python manage.py retry_news_embedding --days 7 --missing-only
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from news.models import News, CompanyNews
from news.services.embedding import EmbeddingService
from news.services.opensearch import OpenSearchService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "DB의 content 필드를 이용해서 embedding부터 다시 생성하고 OpenSearch에 저장합니다. "
        "크롤링이나 요약은 다시 하지 않습니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--news-id",
            type=int,
            nargs="+",
            help="재시도할 뉴스 ID (여러 개 지정 가능)",
        )
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="content가 있지만 OpenSearch에 없는 뉴스만 재시도",
        )
        parser.add_argument(
            "--stock-code",
            type=str,
            help="특정 기업의 뉴스만 재시도 (종목코드)",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="최근 N일 이내 뉴스만 재시도",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제로 재시도하지 않고 대상 뉴스만 출력",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="최대 처리할 뉴스 수 (기본값: 무제한)",
        )

    def handle(self, *args, **options):
        news_ids = options.get("news_id")
        missing_only = options.get("missing_only", False)
        stock_code = options.get("stock_code")
        days = options.get("days")
        dry_run = options.get("dry_run", False)
        limit = options.get("limit")

        # 쿼리셋 구성
        queryset = News.objects.filter(is_deleted=False)

        if news_ids:
            # 특정 뉴스 ID로 필터링
            queryset = queryset.filter(news_id__in=news_ids)
        elif missing_only:
            # content가 있지만 OpenSearch에 없는 뉴스
            # (OpenSearch에 있는지 확인하는 것은 실제 저장 시점에 확인)
            queryset = queryset.filter(content__isnull=False).exclude(content="")
        else:
            # content가 있는 모든 뉴스
            queryset = queryset.filter(content__isnull=False).exclude(content="")

        if stock_code:
            # 특정 기업의 뉴스만 필터링
            company_news_ids = CompanyNews.objects.filter(
                company_id=stock_code
            ).values_list("news_id", flat=True)
            queryset = queryset.filter(news_id__in=company_news_ids)

        if days:
            # 최근 N일 이내 뉴스만
            cutoff_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(created_at__gte=cutoff_date)

        # content가 있는 뉴스만 필터링
        queryset = queryset.filter(content__isnull=False).exclude(content="")

        if limit:
            queryset = queryset[:limit]

        count = queryset.count()
        self.stdout.write(f"대상 뉴스 수: {count}개")

        if count == 0:
            self.stdout.write(self.style.WARNING("재시도할 뉴스가 없습니다."))
            return

        if dry_run:
            self.stdout.write("\n[DRY-RUN] 재시도 대상 뉴스:")
            for news in queryset[:10]:  # 최대 10개만 출력
                self.stdout.write(
                    f"  - ID: {news.news_id}, "
                    f"제목: {news.title[:50]}, "
                    f"언론사: {news.press or 'N/A'}, "
                    f"발행일: {news.published_at or 'N/A'}"
                )
            if count > 10:
                self.stdout.write(f"  ... 외 {count - 10}개")
            return

        # Embedding 서비스 및 OpenSearch 서비스 초기화
        embedding_service = EmbeddingService()
        opensearch_service = OpenSearchService()

        # 재시도 실행
        success_count = 0
        fail_count = 0

        for news in queryset:
            try:
                # content 유효성 검증
                if not news.content or len(news.content.strip()) < 10:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠ 건너뜀: ID {news.news_id} - content가 너무 짧거나 없음"
                        )
                    )
                    continue

                # Embedding 생성
                self.stdout.write(
                    f"임베딩 생성 중: ID {news.news_id} - {news.title[:50]}..."
                )
                embedding = embedding_service.create_embedding(news.content)

                if not embedding:
                    fail_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ 임베딩 생성 실패: ID {news.news_id} - {news.title[:50]}"
                        )
                    )
                    logger.error(
                        f"임베딩 생성 실패: news_id={news.news_id}, title={news.title[:50]}"
                    )
                    continue

                # OpenSearch에 저장
                success = opensearch_service.save_news_vector(
                    news_id=news.news_id,
                    title=news.title,
                    content=news.content,
                    content_vector=embedding,
                    published_at=news.published_at,
                )

                if success:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ 성공: ID {news.news_id} - {news.title[:50]}"
                        )
                    )
                else:
                    fail_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ OpenSearch 저장 실패: ID {news.news_id} - {news.title[:50]}"
                        )
                    )
                    logger.error(
                        f"OpenSearch 저장 실패: news_id={news.news_id}, title={news.title[:50]}"
                    )

            except Exception as e:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f"✗ 오류: ID {news.news_id} - {e}"))
                logger.error(
                    f"뉴스 embedding 재시도 오류: news_id={news.news_id} - {e}",
                    exc_info=True,
                )

        # 결과 요약
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"재시도 완료: 성공 {success_count}개, 실패 {fail_count}개"
            )
        )
