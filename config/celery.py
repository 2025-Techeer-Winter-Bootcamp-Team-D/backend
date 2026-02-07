import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# 태스크를 명시적으로 import하여 등록 보장
# Django 앱이 로드된 후에 import하도록 지연 (순환 import 방지)
# companies.tasks는 companies/tasks/__init__.py에서 자동으로 import되므로
# autodiscover_tasks()가 자동으로 찾습니다.
try:
    import core.tasks.price_sync  # noqa: F401
    import core.tasks.yfinance_sync  # noqa: F401
    # industries.tasks와 companies.tasks는 __init__.py에서 import되어 autodiscover_tasks()로 자동 등록됨
except ImportError:
    pass
