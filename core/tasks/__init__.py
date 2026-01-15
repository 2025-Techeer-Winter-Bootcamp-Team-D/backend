# Core tasks
# 태스크를 명시적으로 import하여 Celery가 자동으로 발견할 수 있도록 함
from . import price_sync  # noqa: F401
from . import yfinance_sync  # noqa: F401
