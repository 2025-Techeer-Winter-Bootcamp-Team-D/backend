from django.db import models


class StockTick(models.Model):
    """실시간 주가 체결 데이터 (TimescaleDB Hypertable)

    주의: 이 모델은 TimescaleDB hypertable로 마이그레이션에서 직접 생성되지 않습니다.
    복합 primary key (symbol, time)를 사용합니다.
    """

    symbol = models.CharField(max_length=10, db_column="symbol")  # KIS 내부 식별자
    stock_code = models.CharField(
        max_length=10, db_column="stock_code", null=True, blank=True
    )  # 실제 6자리 종목코드
    time = models.DateTimeField(db_column="time")
    price = models.DecimalField(max_digits=12, decimal_places=2, db_column="price")
    volume = models.BigIntegerField(db_column="volume")

    class Meta:
        db_table = "stock_ticks"
        ordering = ["-time"]
        # TimescaleDB hypertable은 파티셔닝 컬럼(time)이 primary key에 포함되어야 함
        # 복합 primary key (symbol, time)는 마이그레이션의 RunSQL로 생성
        unique_together = [["symbol", "time"]]
        managed = False

    def __str__(self):
        return f"{self.symbol} @ {self.time}: {self.price} (vol: {self.volume})"
