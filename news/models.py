"""
뉴스 데이터 모델

크롤링된 뉴스 기사의 기본 정보와 요약을 저장합니다.
본문은 벡터 임베딩하여 OpenSearch에 저장됩니다.
"""

from django.db import models
from django.utils import timezone


class News(models.Model):
    """
    뉴스 기사 모델

    - title: 뉴스 제목
    - url: 원본 링크 (unique)
    - summary: Gemini로 생성된 요약문
    - published_at: 발행일
    - created_at: 생성 시간
    - updated_at: 수정 시간
    - is_deleted: 삭제 여부 (soft delete)

    본문(full_content)은 OpenSearch에 벡터 임베딩으로 저장됩니다.
    """

    news_id = models.BigAutoField(primary_key=True, verbose_name="뉴스 ID")

    title = models.CharField(max_length=255, verbose_name="제목")

    url = models.CharField(max_length=500, unique=True, verbose_name="링크")

    summary = models.TextField(null=True, blank=True, verbose_name="요약")

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
