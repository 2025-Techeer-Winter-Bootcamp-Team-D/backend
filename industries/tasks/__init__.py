# industries/tasks/__init__.py
"""
산업 관련 Celery 태스크 패키지
"""

from . import index_sync  # noqa: F401

__all__ = [
    "index_sync",
]
