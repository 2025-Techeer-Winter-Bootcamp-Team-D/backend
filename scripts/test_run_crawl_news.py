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

from news.tasks.workflows import scheduled_crawl_news

keywords = ["경제", "증권"]
result = scheduled_crawl_news.delay(keywords, max_articles_per_keyword=2)
print(f"Task ID: {result.id}")
