import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# 태스크를 명시적으로 import하여 등록 보장
try:
    import core.tasks.price_sync  # noqa: F401
    import core.tasks.yfinance_sync  # noqa: F401
except ImportError:
    pass
