from django.urls import path
from .views import (
    sync_stock_history,
    sync_multiple_stocks_history,
    sync_realtime_prices,
)

urlpatterns = [
    # Stock Data Sync (공개 API)
    path(
        "stocks/<str:stock_code>/sync-history/",
        sync_stock_history,
        name="sync_stock_history",
    ),
    # Admin - Stock Data Sync
    path(
        "admin/stocks/sync-history/",
        sync_multiple_stocks_history,
        name="sync_multiple_stocks_history",
    ),
    path(
        "admin/stocks/sync-realtime/",
        sync_realtime_prices,
        name="sync_realtime_prices",
    ),
]
