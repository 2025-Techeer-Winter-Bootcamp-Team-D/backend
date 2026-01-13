"""
뉴스 크롤링 Management Command

사용법:
    python manage.py crawl_news --keywords "AI" "반도체" --max-articles 10

또는:
    python manage.py crawl_news --keywords "AI" --max-articles 5
"""

from django.core.management.base import BaseCommand
from news.models import CrawlJob
from news.tasks.workflows import scheduled_crawl_news


class Command(BaseCommand):
    help = "뉴스를 크롤링하고 DB에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keywords",
            nargs="+",
            type=str,
            required=True,
            help="검색할 키워드 리스트 (예: --keywords AI 반도체)",
        )
        parser.add_argument(
            "--max-articles",
            type=int,
            default=10,
            help="키워드당 최대 기사 수 (기본값: 10)",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            help="Celery worker를 통해 비동기로 실행 (기본값: 동기 실행)",
        )

    def handle(self, *args, **options):
        keywords = options["keywords"]
        max_articles = options["max_articles"]
        async_mode = options["async"]

        self.stdout.write(
            self.style.SUCCESS(
                f"뉴스 크롤링 시작: 키워드={keywords}, 최대 기사 수={max_articles}"
            )
        )

        # CrawlJob은 scheduled_crawl_news 내부에서 생성됨
        # (Canvas 워크플로우 사용 시)

        if async_mode:
            # Celery worker를 통해 비동기 실행 (새로운 Canvas 워크플로우)
            self.stdout.write("Celery Canvas 워크플로우를 통해 비동기 실행 중...")
            task = scheduled_crawl_news.delay(keywords, max_articles)
            self.stdout.write(
                self.style.SUCCESS(f"태스크가 큐에 추가되었습니다. Task ID: {task.id}")
            )
            self.stdout.write("진행 상황을 확인하려면:")
            self.stdout.write("  1. Flower: http://localhost:5555")
            self.stdout.write("  2. Django Shell:")
            self.stdout.write(
                f"     from news.models import CrawlJob; "
                f"job = CrawlJob.objects.order_by('-created_at').first(); "
                f"print(f'상태: {{job.status}}, 성공: {{job.successful_articles}}, 실패: {{job.failed_articles}}')"
            )
        else:
            # 동기적으로 실행 (직접 실행)
            self.stdout.write("동기 실행 중... (완료될 때까지 대기)")
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  이 작업은 시간이 걸릴 수 있습니다 (각 기사당 약 10-30초)"
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  Canvas 워크플로우는 비동기 실행을 권장합니다 (--async 옵션 사용)"
                )
            )

            crawl_job = None
            try:
                # 동기 실행은 워크플로우를 직접 호출
                result = scheduled_crawl_news(keywords, max_articles)

                # 결과 확인 (result는 CrawlJob ID)
                if result:
                    crawl_job = CrawlJob.objects.get(id=result)
                    crawl_job.refresh_from_db()

                    self.stdout.write("")
                    self.stdout.write(self.style.SUCCESS("=" * 60))
                    self.stdout.write(self.style.SUCCESS("크롤링 완료"))
                    self.stdout.write(self.style.SUCCESS("=" * 60))
                    self.stdout.write(f"작업 ID: {crawl_job.id}")
                    self.stdout.write(f"작업 상태: {crawl_job.status}")
                    self.stdout.write(f"총 기사 수: {crawl_job.total_articles}")
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"성공한 기사 수: {crawl_job.successful_articles}"
                        )
                    )
                    self.stdout.write(
                        self.style.ERROR(f"실패한 기사 수: {crawl_job.failed_articles}")
                    )

                    if crawl_job.error_message:
                        self.stdout.write(
                            self.style.ERROR(f"오류 메시지: {crawl_job.error_message}")
                        )

                # 저장된 뉴스 확인
                from news.models import News

                news_count = News.objects.filter(is_deleted=False).count()
                self.stdout.write("")
                self.stdout.write(
                    self.style.SUCCESS(f"✅ 총 {news_count}개의 뉴스가 저장되었습니다.")
                )

                if news_count > 0:
                    self.stdout.write("")
                    self.stdout.write("최근 저장된 뉴스 5개:")
                    recent_news = News.objects.filter(is_deleted=False).order_by(
                        "-created_at"
                    )[:5]
                    for news in recent_news:
                        self.stdout.write(f"  - [{news.news_id}] {news.title[:50]}...")
                        self.stdout.write(f"    URL: {news.url[:60]}...")

            except Exception as e:
                self.stdout.write("")
                self.stdout.write(self.style.ERROR("=" * 60))
                self.stdout.write(self.style.ERROR("❌ 오류 발생"))
                self.stdout.write(self.style.ERROR("=" * 60))
                self.stdout.write(self.style.ERROR(f"오류 메시지: {str(e)}"))

                # CrawlJob 상태 확인
                try:
                    if crawl_job:
                        crawl_job.refresh_from_db()
                        self.stdout.write(f"CrawlJob 상태: {crawl_job.status}")
                        if crawl_job.error_message:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"CrawlJob 오류 메시지: {crawl_job.error_message}"
                                )
                            )
                except Exception:
                    # 오류 발생 시 무시
                    pass

                raise
