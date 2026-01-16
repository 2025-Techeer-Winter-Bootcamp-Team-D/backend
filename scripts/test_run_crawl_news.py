# scripts/test_run_crawl_news.py
import os
import sys
import django
from pathlib import Path

# 프로젝트 루트 디렉토리를 Python path에 추가
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from news.tasks.workflows import start_search_phase
from news.models import CrawlJob
from django.utils import timezone

# CrawlJob 생성
job = CrawlJob.objects.create(
    status="pending",
    keywords=["경제", "증권"],
    max_articles_per_keyword=2,
)

# Celery 태스크 실행
task = start_search_phase.delay(
    keywords=["경제", "증권"],
    max_articles_per_keyword=2,
    job_id=job.id,
)
print(f"Task ID: {task.id}, Job ID: {job.id}")
