# Companies tasks
# 태스크를 명시적으로 import하여 Celery가 자동으로 발견할 수 있도록 함
from . import financial_metrics  # noqa: F401
from . import dart_sync  # noqa: F401
from . import report_processing  # noqa: F401
from . import rankings  # noqa: F401
from . import kis_market_amount  # noqa: F401
