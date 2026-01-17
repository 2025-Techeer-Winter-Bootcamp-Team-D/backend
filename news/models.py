"""
뉴스 데이터 모델

크롤링된 뉴스 기사의 기본 정보와 요약을 저장합니다.
본문은 벡터 임베딩하여 OpenSearch에 저장됩니다.
"""

from django.db import models
from django.utils import timezone


class CompanyNews(models.Model):
    """
    기업-뉴스 매핑 테이블

    - Company ↔ News 다대다 관계를 위한 매핑 테이블
    - 동일 뉴스가 여러 기업에 연결될 수 있음
    """

    id = models.BigAutoField(primary_key=True, verbose_name="ID")

    # 기업 연결 (Company.stock_code FK)
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="company_news",
        db_column="stock_code",
        verbose_name="기업",
    )

    # 뉴스 연결 (News FK)
    news = models.ForeignKey(
        "News",
        on_delete=models.CASCADE,
        related_name="company_mappings",
        verbose_name="뉴스",
    )

    # 날짜 정보
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 시간")

    class Meta:
        db_table = "company_news"
        ordering = ["-created_at"]
        verbose_name = "기업 뉴스 매핑"
        verbose_name_plural = "기업 뉴스 매핑 목록"
        indexes = [
            models.Index(fields=["company", "-created_at"]),
        ]
        constraints = [
            # 동일 기업-뉴스 매핑 중복 방지
            models.UniqueConstraint(
                fields=["company", "news"], name="unique_company_news_mapping"
            )
        ]

    def __str__(self):
        return f"[{self.company_id}] -> News {self.news_id}"


class News(models.Model):
    """
    뉴스 기사 모델

    - title: 뉴스 제목
    - url: 원본 링크 (unique)
    - summary: Gemini로 생성된 요약문
    - content: 정제된 본문
    - author: 저자/기자
    - press: 언론사
    - keywords: 키워드 목록
    - published_at: 발행일
    - created_at: 생성 시간
    - updated_at: 수정 시간
    - is_deleted: 삭제 여부 (soft delete)
    """

    news_id = models.BigAutoField(primary_key=True, verbose_name="뉴스 ID")

    title = models.CharField(max_length=500, verbose_name="제목")

    url = models.CharField(max_length=1000, unique=True, verbose_name="링크")

    summary = models.TextField(null=True, blank=True, verbose_name="요약")

    # 메타데이터 필드 추가
    content = models.TextField(null=True, blank=True, verbose_name="정제된 본문")

    author = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="저자/기자"
    )

    press = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="언론사"
    )

    keywords = models.JSONField(default=list, blank=True, verbose_name="키워드 목록")

    published_at = models.DateTimeField(null=True, blank=True, verbose_name="발행일")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 시간")

    updated_at = models.DateTimeField(
        auto_now=True, null=True, verbose_name="수정 시간"
    )

    is_deleted = models.BooleanField(default=False, verbose_name="삭제 여부")

    class Meta:
        db_table = "news"
        ordering = ["-published_at", "-created_at"]
        verbose_name = "뉴스"
        verbose_name_plural = "뉴스 목록"
        indexes = [
            models.Index(fields=["-published_at", "is_deleted"]),
            models.Index(fields=["is_deleted", "-created_at"]),
            models.Index(fields=["press", "-published_at"]),
        ]

    def __str__(self):
        return f"[{self.news_id}] {self.title[:50]}"

    def soft_delete(self):
        """소프트 삭제"""
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])

    def restore(self):
        """삭제 취소"""
        self.is_deleted = False
        self.save(update_fields=["is_deleted", "updated_at"])


class CrawlJob(models.Model):
    """
    크롤링 작업 추적 모델

    크롤링 작업의 상태와 통계를 관리합니다.
    """

    STATUS_CHOICES = [
        ("pending", "대기 중"),
        ("running", "실행 중"),
        ("completed", "완료"),
        ("failed", "실패"),
    ]

    keywords = models.JSONField(
        help_text="검색 키워드 리스트", verbose_name="검색 키워드"
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="상태"
    )

    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Celery 작업 ID",
    )

    total_articles = models.IntegerField(default=0, verbose_name="총 기사 수")

    successful_articles = models.IntegerField(default=0, verbose_name="성공한 기사 수")

    failed_articles = models.IntegerField(default=0, verbose_name="실패한 기사 수")

    error_message = models.TextField(null=True, blank=True, verbose_name="오류 메시지")

    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name="생성 시간"
    )

    started_at = models.DateTimeField(null=True, blank=True, verbose_name="시작 시간")

    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="완료 시간")

    class Meta:
        db_table = "crawl_jobs"
        ordering = ["-created_at"]
        verbose_name = "크롤링 작업"
        verbose_name_plural = "크롤링 작업 목록"
        indexes = [
            models.Index(fields=["-created_at", "status"]),
        ]

    def __str__(self):
        return f"CrawlJob {self.id} - {self.status} ({', '.join(self.keywords)})"

    def mark_as_running(self):
        """작업을 실행 중으로 표시"""
        self.status = "running"
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_as_completed(self):
        """작업을 완료로 표시"""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

    def mark_as_failed(self, error_message):
        """작업을 실패로 표시"""
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at"])


class KeywordFrequency(models.Model):
    """
    키워드 빈도수 모델

    AI 추출 키워드의 빈도수를 관리합니다.
    뉴스 저장 시 자동으로 빈도수를 업데이트하며,
    키워드 조회 시 이 테이블에서 집계합니다.
    """

    keyword_id = models.BigAutoField(primary_key=True, verbose_name="키워드 ID")

    keyword = models.CharField(
        max_length=200, unique=True, db_index=True, verbose_name="키워드"
    )

    frequency = models.IntegerField(default=0, verbose_name="전체 빈도수")
    """전체 빈도수: 키워드가 등장한 총 횟수"""

    doc_count = models.IntegerField(default=0, verbose_name="문서 수")
    """문서 수: 키워드가 등장한 뉴스 기사 수"""

    first_seen_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="최초 등장일"
    )
    """키워드가 처음 등장한 날짜"""

    last_seen_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="최종 등장일"
    )
    """키워드가 마지막으로 등장한 날짜"""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 시간")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 시간")

    class Meta:
        db_table = "keyword_frequencies"
        ordering = ["-frequency", "-doc_count"]
        verbose_name = "키워드 빈도수"
        verbose_name_plural = "키워드 빈도수 목록"
        indexes = [
            models.Index(fields=["-frequency", "-doc_count"]),
            models.Index(fields=["-last_seen_at"]),
            models.Index(fields=["keyword"]),
        ]

    def __str__(self):
        return f"{self.keyword} (빈도: {self.frequency}, 문서: {self.doc_count})"
