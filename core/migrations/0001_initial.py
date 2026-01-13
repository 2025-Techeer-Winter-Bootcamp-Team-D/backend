# Combined migration: Stock ticks table + Continuous Aggregates with stock_code
# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            # 데이터베이스 작업: TimescaleDB hypertable 생성 (stock_code 포함)
            database_operations=[
                # 1단계: stock_code를 포함한 테이블 생성
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS stock_ticks (
                        symbol VARCHAR(10) NOT NULL,
                        stock_code VARCHAR(10),
                        time TIMESTAMP NOT NULL,
                        price DECIMAL(12, 2) NOT NULL,
                        volume BIGINT NOT NULL,
                        PRIMARY KEY (symbol, time)
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS stock_ticks CASCADE;",
                ),
                # 2단계: TimescaleDB hypertable로 변환
                migrations.RunSQL(
                    sql="""
                    SELECT create_hypertable(
                        'stock_ticks',
                        'time',
                        chunk_time_interval => INTERVAL '1 day',
                        if_not_exists => TRUE
                    );
                    """,
                    reverse_sql="-- Hypertable conversion cannot be reversed; table must be dropped and recreated",
                ),
                # 3단계: 압축 설정
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE stock_ticks SET (
                        timescaledb.compress = TRUE,
                        timescaledb.compress_segmentby = 'stock_code, symbol',
                        timescaledb.compress_orderby = 'time DESC'
                    );
                    """,
                    reverse_sql="""
                    ALTER TABLE stock_ticks SET (
                        timescaledb.compress = FALSE
                    );
                    """,
                ),
                # 4단계: 인덱스 생성
                migrations.RunSQL(
                    sql="""
                    CREATE INDEX IF NOT EXISTS idx_stock_ticks_stock_code_symbol_time 
                    ON stock_ticks(stock_code, symbol, time DESC);
                    """,
                    reverse_sql="""
                    DROP INDEX IF EXISTS idx_stock_ticks_stock_code_symbol_time;
                    """,
                ),
                # 5단계: 1분봉 OHLCV Continuous Aggregate
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW stock_prices_1m
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 minute', time) AS bucket,
                        stock_code,
                        symbol,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    WHERE stock_code IS NOT NULL
                    GROUP BY bucket, stock_code, symbol
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS stock_prices_1m CASCADE;",
                ),
                # 6단계: 15분봉 OHLCV Continuous Aggregate
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW stock_prices_15m
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('15 minutes', time) AS bucket,
                        stock_code,
                        symbol,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    WHERE stock_code IS NOT NULL
                    GROUP BY bucket, stock_code, symbol
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS stock_prices_15m CASCADE;",
                ),
                # 7단계: 1시간봉 OHLCV Continuous Aggregate
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW stock_prices_1h
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 hour', time) AS bucket,
                        stock_code,
                        symbol,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    WHERE stock_code IS NOT NULL
                    GROUP BY bucket, stock_code, symbol
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS stock_prices_1h CASCADE;",
                ),
                # 8단계: 1일봉 OHLCV Continuous Aggregate
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW stock_prices_1d
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 day', time) AS bucket,
                        stock_code,
                        symbol,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    WHERE stock_code IS NOT NULL
                    GROUP BY bucket, stock_code, symbol
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS stock_prices_1d CASCADE;",
                ),
                # 9단계: 자동 갱신 정책 설정
                migrations.RunSQL(
                    sql="""
                    -- 1분봉 정책 (30초마다 갱신)
                    SELECT add_continuous_aggregate_policy('stock_prices_1m',
                        start_offset => INTERVAL '10 minutes',
                        end_offset => INTERVAL '1 minute',
                        schedule_interval => INTERVAL '30 seconds',
                        if_not_exists => TRUE
                    );
                    
                    -- 15분봉 정책 (5분마다 갱신)
                    SELECT add_continuous_aggregate_policy('stock_prices_15m',
                        start_offset => INTERVAL '1 hour',
                        end_offset => INTERVAL '15 minutes',
                        schedule_interval => INTERVAL '5 minutes',
                        if_not_exists => TRUE
                    );
                    
                    -- 1시간봉 정책 (15분마다 갱신)
                    SELECT add_continuous_aggregate_policy('stock_prices_1h',
                        start_offset => INTERVAL '4 hours',
                        end_offset => INTERVAL '1 hour',
                        schedule_interval => INTERVAL '15 minutes',
                        if_not_exists => TRUE
                    );
                    
                    -- 1일봉 정책 (1시간마다 갱신)
                    SELECT add_continuous_aggregate_policy('stock_prices_1d',
                        start_offset => INTERVAL '3 days',
                        end_offset => INTERVAL '1 day',
                        schedule_interval => INTERVAL '1 hour',
                        if_not_exists => TRUE
                    );
                    """,
                    reverse_sql="""
                    SELECT remove_continuous_aggregate_policy('stock_prices_1m', if_exists => TRUE);
                    SELECT remove_continuous_aggregate_policy('stock_prices_15m', if_exists => TRUE);
                    SELECT remove_continuous_aggregate_policy('stock_prices_1h', if_exists => TRUE);
                    SELECT remove_continuous_aggregate_policy('stock_prices_1d', if_exists => TRUE);
                    """,
                ),
                # 10단계: 데이터 보관 정책 (Retention Policies)
                migrations.RunSQL(
                    sql="""
                    -- 원본 tick 데이터: 7일 보관 후 자동 삭제
                    -- 원본 데이터는 Continuous Aggregates에 집계되므로 짧은 기간만 보관
                    SELECT add_retention_policy('stock_ticks', INTERVAL '7 days', if_not_exists => TRUE);
                    
                    -- 1분봉: 30일 보관
                    SELECT add_retention_policy('stock_prices_1m', INTERVAL '30 days', if_not_exists => TRUE);
                    
                    -- 15분봉: 90일 보관
                    SELECT add_retention_policy('stock_prices_15m', INTERVAL '90 days', if_not_exists => TRUE);
                    
                    -- 1시간봉: 1년 보관
                    SELECT add_retention_policy('stock_prices_1h', INTERVAL '1 year', if_not_exists => TRUE);
                    
                    -- 1일봉: 무기한 보관 (정책 없음)
                    """,
                    reverse_sql="""
                    SELECT remove_retention_policy('stock_ticks', if_exists => TRUE);
                    SELECT remove_retention_policy('stock_prices_1m', if_exists => TRUE);
                    SELECT remove_retention_policy('stock_prices_15m', if_exists => TRUE);
                    SELECT remove_retention_policy('stock_prices_1h', if_exists => TRUE);
                    """,
                ),
            ],
            # Django 상태 작업: 모델 등록 (stock_code 포함)
            state_operations=[
                migrations.CreateModel(
                    name="StockTick",
                    fields=[
                        ("symbol", models.CharField(db_column="symbol", max_length=10)),
                        (
                            "stock_code",
                            models.CharField(
                                blank=True,
                                db_column="stock_code",
                                max_length=10,
                                null=True,
                            ),
                        ),
                        ("time", models.DateTimeField(db_column="time")),
                        (
                            "price",
                            models.DecimalField(
                                db_column="price", decimal_places=2, max_digits=12
                            ),
                        ),
                        ("volume", models.BigIntegerField(db_column="volume")),
                    ],
                    options={
                        "db_table": "stock_ticks",
                        "ordering": ["-time"],
                        "unique_together": {("symbol", "time")},
                        "managed": True,
                    },
                ),
            ],
        ),
    ]
