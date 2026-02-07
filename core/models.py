from django.db import models


class StockPrice(models.Model):
    """통합 주가 OHLCV 데이터 (추상 모델)

    yfinance 과거 데이터 + 실시간 Continuous Aggregate 데이터를 통합 저장합니다.
    1분봉, 15분봉, 1시간봉, 1일봉 테이블의 공통 스키마입니다.
    """

    bucket = models.DateTimeField(db_column="bucket")  # 시간 버킷
    stock_code = models.CharField(max_length=10, db_column="stock_code")
    open = models.DecimalField(
        max_digits=12, decimal_places=2, db_column="open", null=True
    )
    high = models.DecimalField(
        max_digits=12, decimal_places=2, db_column="high", null=True
    )
    low = models.DecimalField(
        max_digits=12, decimal_places=2, db_column="low", null=True
    )
    close = models.DecimalField(
        max_digits=12, decimal_places=2, db_column="close", null=True
    )
    volume = models.BigIntegerField(db_column="volume", default=0)
    amount = models.DecimalField(
        max_digits=20, decimal_places=2, db_column="amount", default=0
    )
    trade_count = models.IntegerField(db_column="trade_count", default=0)
    source = models.CharField(max_length=20, db_column="source", default="realtime")
    created_at = models.DateTimeField(db_column="created_at", auto_now_add=True)
    updated_at = models.DateTimeField(db_column="updated_at", auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-bucket"]

    def __str__(self):
        return f"{self.stock_code} @ {self.bucket}: O={self.open} H={self.high} L={self.low} C={self.close}"


class StockPrice1m(StockPrice):
    """1분봉 주가 데이터"""

    class Meta:
        db_table = "stock_prices_1m"
        ordering = ["-bucket"]
        unique_together = [["stock_code", "bucket"]]
        managed = False


class StockPrice15m(StockPrice):
    """15분봉 주가 데이터"""

    class Meta:
        db_table = "stock_prices_15m"
        ordering = ["-bucket"]
        unique_together = [["stock_code", "bucket"]]
        managed = False


class StockPrice1h(StockPrice):
    """1시간봉 주가 데이터"""

    class Meta:
        db_table = "stock_prices_1h"
        ordering = ["-bucket"]
        unique_together = [["stock_code", "bucket"]]
        managed = False


class StockPrice1d(StockPrice):
    """1일봉 주가 데이터"""

    class Meta:
        db_table = "stock_prices_1d"
        ordering = ["-bucket"]
        unique_together = [["stock_code", "bucket"]]
        managed = False


class StockTick(models.Model):
    """실시간 주가 체결 데이터 (TimescaleDB Hypertable)

    주의: 이 모델은 TimescaleDB hypertable로 마이그레이션에서 직접 생성됩니다.
    복합 primary key (stock_code, time)를 사용합니다.
    """

    stock_code = models.CharField(
        max_length=10, db_column="stock_code"
    )  # 실제 6자리 종목코드 (PK의 일부)
    symbol = models.CharField(
        max_length=10, db_column="symbol", null=True, blank=True
    )  # KIS 내부 식별자 (optional)
    time = models.DateTimeField(db_column="time")  # 체결 시간 (PK의 일부)
    price = models.DecimalField(max_digits=12, decimal_places=2, db_column="price")
    volume = models.BigIntegerField(db_column="volume")

    class Meta:
        db_table = "stock_ticks"
        ordering = ["-time"]
        # TimescaleDB hypertable은 파티셔닝 컬럼(time)이 primary key에 포함되어야 함
        # 복합 primary key (stock_code, time)는 마이그레이션의 RunSQL로 생성
        unique_together = [["stock_code", "time"]]
        managed = False

    def __str__(self):
        return f"{self.stock_code} @ {self.time}: {self.price} (vol: {self.volume})"
