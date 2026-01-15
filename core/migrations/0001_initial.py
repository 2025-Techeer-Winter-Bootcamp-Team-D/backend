# Combined migration: Stock ticks + Continuous Aggregates + 통합 테이블
# Primary Key: (stock_code, time) - 종목코드와 시간으로 고유 식별
# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            # 데이터베이스 작업: TimescaleDB hypertable 생성
            database_operations=[
                # ============================================================
                # 1단계: stock_ticks 테이블 생성
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS stock_ticks (
                        stock_code VARCHAR(10) NOT NULL,
                        symbol VARCHAR(10),
                        time TIMESTAMP NOT NULL,
                        price DECIMAL(12, 2) NOT NULL,
                        volume BIGINT NOT NULL,
                        PRIMARY KEY (stock_code, time)
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS stock_ticks CASCADE;",
                ),
                # ============================================================
                # 2단계: TimescaleDB hypertable로 변환
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    SELECT create_hypertable(
                        'stock_ticks',
                        'time',
                        chunk_time_interval => INTERVAL '1 day',
                        if_not_exists => TRUE
                    );
                    """,
                    reverse_sql="-- Hypertable conversion cannot be reversed",
                ),
                # ============================================================
                # 3단계: 압축 설정
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE stock_ticks SET (
                        timescaledb.compress = TRUE,
                        timescaledb.compress_segmentby = 'stock_code',
                        timescaledb.compress_orderby = 'time DESC'
                    );
                    """,
                    reverse_sql="""
                    ALTER TABLE stock_ticks SET (
                        timescaledb.compress = FALSE
                    );
                    """,
                ),
                # ============================================================
                # 4단계: stock_ticks 인덱스 생성
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE INDEX IF NOT EXISTS idx_stock_ticks_stock_code_time 
                    ON stock_ticks(stock_code, time DESC);
                    """,
                    reverse_sql="DROP INDEX IF EXISTS idx_stock_ticks_stock_code_time;",
                ),
                # ============================================================
                # 5단계: 내부용 Continuous Aggregate - 1분봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW _cagg_1m
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 minute', time) AS bucket,
                        stock_code,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    GROUP BY bucket, stock_code
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS _cagg_1m CASCADE;",
                ),
                # ============================================================
                # 6단계: 내부용 Continuous Aggregate - 15분봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW _cagg_15m
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('15 minutes', time) AS bucket,
                        stock_code,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    GROUP BY bucket, stock_code
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS _cagg_15m CASCADE;",
                ),
                # ============================================================
                # 7단계: 내부용 Continuous Aggregate - 1시간봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW _cagg_1h
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 hour', time) AS bucket,
                        stock_code,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    GROUP BY bucket, stock_code
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS _cagg_1h CASCADE;",
                ),
                # ============================================================
                # 8단계: 내부용 Continuous Aggregate - 1일봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE MATERIALIZED VIEW _cagg_1d
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 day', time) AS bucket,
                        stock_code,
                        first(price, time) AS open,
                        max(price) AS high,
                        min(price) AS low,
                        last(price, time) AS close,
                        sum(volume) AS volume,
                        sum(price * volume) AS amount,
                        count(*) AS trade_count
                    FROM stock_ticks
                    GROUP BY bucket, stock_code
                    WITH NO DATA;
                    """,
                    reverse_sql="DROP MATERIALIZED VIEW IF EXISTS _cagg_1d CASCADE;",
                ),
                # ============================================================
                # 9단계: Continuous Aggregate 자동 갱신 정책
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    -- 1분봉 정책 (30초마다 갱신)
                    SELECT add_continuous_aggregate_policy('_cagg_1m',
                        start_offset => INTERVAL '10 minutes',
                        end_offset => INTERVAL '1 minute',
                        schedule_interval => INTERVAL '30 seconds',
                        if_not_exists => TRUE
                    );
                    
                    -- 15분봉 정책 (5분마다 갱신)
                    SELECT add_continuous_aggregate_policy('_cagg_15m',
                        start_offset => INTERVAL '1 hour',
                        end_offset => INTERVAL '15 minutes',
                        schedule_interval => INTERVAL '5 minutes',
                        if_not_exists => TRUE
                    );
                    
                    -- 1시간봉 정책 (15분마다 갱신)
                    SELECT add_continuous_aggregate_policy('_cagg_1h',
                        start_offset => INTERVAL '4 hours',
                        end_offset => INTERVAL '1 hour',
                        schedule_interval => INTERVAL '15 minutes',
                        if_not_exists => TRUE
                    );
                    
                    -- 1일봉 정책 (1시간마다 갱신)
                    SELECT add_continuous_aggregate_policy('_cagg_1d',
                        start_offset => INTERVAL '3 days',
                        end_offset => INTERVAL '1 day',
                        schedule_interval => INTERVAL '1 hour',
                        if_not_exists => TRUE
                    );
                    """,
                    reverse_sql="""
                    SELECT remove_continuous_aggregate_policy('_cagg_1m', if_exists => TRUE);
                    SELECT remove_continuous_aggregate_policy('_cagg_15m', if_exists => TRUE);
                    SELECT remove_continuous_aggregate_policy('_cagg_1h', if_exists => TRUE);
                    SELECT remove_continuous_aggregate_policy('_cagg_1d', if_exists => TRUE);
                    """,
                ),
                # ============================================================
                # 10단계: stock_ticks 데이터 보관 정책
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    -- 원본 tick 데이터: 7일 보관 후 자동 삭제
                    SELECT add_retention_policy('stock_ticks', INTERVAL '7 days', if_not_exists => TRUE);
                    """,
                    reverse_sql="""
                    SELECT remove_retention_policy('stock_ticks', if_exists => TRUE);
                    """,
                ),
                # ============================================================
                # 11단계: 통합 테이블 생성 - 1분봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS stock_prices_1m (
                        bucket TIMESTAMP NOT NULL,
                        stock_code VARCHAR(10) NOT NULL,
                        open DECIMAL(12, 2),
                        high DECIMAL(12, 2),
                        low DECIMAL(12, 2),
                        close DECIMAL(12, 2),
                        volume BIGINT DEFAULT 0,
                        amount DECIMAL(20, 2) DEFAULT 0,
                        trade_count INTEGER DEFAULT 0,
                        source VARCHAR(20) DEFAULT 'realtime',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (stock_code, bucket)
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS stock_prices_1m CASCADE;",
                ),
                # ============================================================
                # 12단계: 통합 테이블 생성 - 15분봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS stock_prices_15m (
                        bucket TIMESTAMP NOT NULL,
                        stock_code VARCHAR(10) NOT NULL,
                        open DECIMAL(12, 2),
                        high DECIMAL(12, 2),
                        low DECIMAL(12, 2),
                        close DECIMAL(12, 2),
                        volume BIGINT DEFAULT 0,
                        amount DECIMAL(20, 2) DEFAULT 0,
                        trade_count INTEGER DEFAULT 0,
                        source VARCHAR(20) DEFAULT 'realtime',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (stock_code, bucket)
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS stock_prices_15m CASCADE;",
                ),
                # ============================================================
                # 13단계: 통합 테이블 생성 - 1시간봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS stock_prices_1h (
                        bucket TIMESTAMP NOT NULL,
                        stock_code VARCHAR(10) NOT NULL,
                        open DECIMAL(12, 2),
                        high DECIMAL(12, 2),
                        low DECIMAL(12, 2),
                        close DECIMAL(12, 2),
                        volume BIGINT DEFAULT 0,
                        amount DECIMAL(20, 2) DEFAULT 0,
                        trade_count INTEGER DEFAULT 0,
                        source VARCHAR(20) DEFAULT 'realtime',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (stock_code, bucket)
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS stock_prices_1h CASCADE;",
                ),
                # ============================================================
                # 14단계: 통합 테이블 생성 - 1일봉
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS stock_prices_1d (
                        bucket TIMESTAMP NOT NULL,
                        stock_code VARCHAR(10) NOT NULL,
                        open DECIMAL(12, 2),
                        high DECIMAL(12, 2),
                        low DECIMAL(12, 2),
                        close DECIMAL(12, 2),
                        volume BIGINT DEFAULT 0,
                        amount DECIMAL(20, 2) DEFAULT 0,
                        trade_count INTEGER DEFAULT 0,
                        source VARCHAR(20) DEFAULT 'realtime',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (stock_code, bucket)
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS stock_prices_1d CASCADE;",
                ),
                # ============================================================
                # 15단계: 통합 테이블을 hypertable로 변환
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    SELECT create_hypertable('stock_prices_1m', 'bucket', 
                        chunk_time_interval => INTERVAL '1 day',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    );
                    SELECT create_hypertable('stock_prices_15m', 'bucket', 
                        chunk_time_interval => INTERVAL '7 days',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    );
                    SELECT create_hypertable('stock_prices_1h', 'bucket', 
                        chunk_time_interval => INTERVAL '30 days',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    );
                    SELECT create_hypertable('stock_prices_1d', 'bucket', 
                        chunk_time_interval => INTERVAL '1 year',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    );
                    """,
                    reverse_sql="-- Hypertable conversion cannot be reversed",
                ),
                # ============================================================
                # 16단계: 통합 테이블 인덱스 생성
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    CREATE INDEX IF NOT EXISTS idx_prices_1m_bucket 
                    ON stock_prices_1m(bucket DESC);
                    CREATE INDEX IF NOT EXISTS idx_prices_1m_stock_bucket 
                    ON stock_prices_1m(stock_code, bucket DESC);
                    
                    CREATE INDEX IF NOT EXISTS idx_prices_15m_bucket 
                    ON stock_prices_15m(bucket DESC);
                    CREATE INDEX IF NOT EXISTS idx_prices_15m_stock_bucket 
                    ON stock_prices_15m(stock_code, bucket DESC);
                    
                    CREATE INDEX IF NOT EXISTS idx_prices_1h_bucket 
                    ON stock_prices_1h(bucket DESC);
                    CREATE INDEX IF NOT EXISTS idx_prices_1h_stock_bucket 
                    ON stock_prices_1h(stock_code, bucket DESC);
                    
                    CREATE INDEX IF NOT EXISTS idx_prices_1d_bucket 
                    ON stock_prices_1d(bucket DESC);
                    CREATE INDEX IF NOT EXISTS idx_prices_1d_stock_bucket 
                    ON stock_prices_1d(stock_code, bucket DESC);
                    """,
                    reverse_sql="""
                    DROP INDEX IF EXISTS idx_prices_1m_bucket;
                    DROP INDEX IF EXISTS idx_prices_1m_stock_bucket;
                    DROP INDEX IF EXISTS idx_prices_15m_bucket;
                    DROP INDEX IF EXISTS idx_prices_15m_stock_bucket;
                    DROP INDEX IF EXISTS idx_prices_1h_bucket;
                    DROP INDEX IF EXISTS idx_prices_1h_stock_bucket;
                    DROP INDEX IF EXISTS idx_prices_1d_bucket;
                    DROP INDEX IF EXISTS idx_prices_1d_stock_bucket;
                    """,
                ),
                # ============================================================
                # 17단계: 통합 테이블 보관 정책
                # ============================================================
                migrations.RunSQL(
                    sql="""
                    -- 1분봉: 30일 보관
                    SELECT add_retention_policy('stock_prices_1m', INTERVAL '30 days', if_not_exists => TRUE);
                    -- 15분봉: 90일 보관
                    SELECT add_retention_policy('stock_prices_15m', INTERVAL '90 days', if_not_exists => TRUE);
                    -- 1시간봉: 1년 보관
                    SELECT add_retention_policy('stock_prices_1h', INTERVAL '1 year', if_not_exists => TRUE);
                    -- 1일봉: 무기한 보관 (정책 없음)
                    """,
                    reverse_sql="""
                    SELECT remove_retention_policy('stock_prices_1m', if_exists => TRUE);
                    SELECT remove_retention_policy('stock_prices_15m', if_exists => TRUE);
                    SELECT remove_retention_policy('stock_prices_1h', if_exists => TRUE);
                    """,
                ),
            ],
            # Django 상태 작업: 모델 등록
            state_operations=[
                migrations.CreateModel(
                    name="StockTick",
                    fields=[
                        (
                            "stock_code",
                            models.CharField(
                                db_column="stock_code",
                                max_length=10,
                                primary_key=False,
                            ),
                        ),
                        (
                            "symbol",
                            models.CharField(
                                blank=True,
                                db_column="symbol",
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
                        "unique_together": {("stock_code", "time")},
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="StockPrice1m",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("bucket", models.DateTimeField(db_column="bucket")),
                        (
                            "stock_code",
                            models.CharField(db_column="stock_code", max_length=10),
                        ),
                        (
                            "open",
                            models.DecimalField(
                                db_column="open",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "high",
                            models.DecimalField(
                                db_column="high",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "low",
                            models.DecimalField(
                                db_column="low",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "close",
                            models.DecimalField(
                                db_column="close",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "volume",
                            models.BigIntegerField(db_column="volume", default=0),
                        ),
                        (
                            "amount",
                            models.DecimalField(
                                db_column="amount",
                                decimal_places=2,
                                default=0,
                                max_digits=20,
                            ),
                        ),
                        (
                            "trade_count",
                            models.IntegerField(db_column="trade_count", default=0),
                        ),
                        (
                            "source",
                            models.CharField(
                                db_column="source", default="realtime", max_length=20
                            ),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, db_column="created_at"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(auto_now=True, db_column="updated_at"),
                        ),
                    ],
                    options={
                        "db_table": "stock_prices_1m",
                        "ordering": ["-bucket"],
                        "unique_together": {("stock_code", "bucket")},
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="StockPrice15m",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("bucket", models.DateTimeField(db_column="bucket")),
                        (
                            "stock_code",
                            models.CharField(db_column="stock_code", max_length=10),
                        ),
                        (
                            "open",
                            models.DecimalField(
                                db_column="open",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "high",
                            models.DecimalField(
                                db_column="high",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "low",
                            models.DecimalField(
                                db_column="low",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "close",
                            models.DecimalField(
                                db_column="close",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "volume",
                            models.BigIntegerField(db_column="volume", default=0),
                        ),
                        (
                            "amount",
                            models.DecimalField(
                                db_column="amount",
                                decimal_places=2,
                                default=0,
                                max_digits=20,
                            ),
                        ),
                        (
                            "trade_count",
                            models.IntegerField(db_column="trade_count", default=0),
                        ),
                        (
                            "source",
                            models.CharField(
                                db_column="source", default="realtime", max_length=20
                            ),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, db_column="created_at"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(auto_now=True, db_column="updated_at"),
                        ),
                    ],
                    options={
                        "db_table": "stock_prices_15m",
                        "ordering": ["-bucket"],
                        "unique_together": {("stock_code", "bucket")},
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="StockPrice1h",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("bucket", models.DateTimeField(db_column="bucket")),
                        (
                            "stock_code",
                            models.CharField(db_column="stock_code", max_length=10),
                        ),
                        (
                            "open",
                            models.DecimalField(
                                db_column="open",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "high",
                            models.DecimalField(
                                db_column="high",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "low",
                            models.DecimalField(
                                db_column="low",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "close",
                            models.DecimalField(
                                db_column="close",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "volume",
                            models.BigIntegerField(db_column="volume", default=0),
                        ),
                        (
                            "amount",
                            models.DecimalField(
                                db_column="amount",
                                decimal_places=2,
                                default=0,
                                max_digits=20,
                            ),
                        ),
                        (
                            "trade_count",
                            models.IntegerField(db_column="trade_count", default=0),
                        ),
                        (
                            "source",
                            models.CharField(
                                db_column="source", default="realtime", max_length=20
                            ),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, db_column="created_at"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(auto_now=True, db_column="updated_at"),
                        ),
                    ],
                    options={
                        "db_table": "stock_prices_1h",
                        "ordering": ["-bucket"],
                        "unique_together": {("stock_code", "bucket")},
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="StockPrice1d",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("bucket", models.DateTimeField(db_column="bucket")),
                        (
                            "stock_code",
                            models.CharField(db_column="stock_code", max_length=10),
                        ),
                        (
                            "open",
                            models.DecimalField(
                                db_column="open",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "high",
                            models.DecimalField(
                                db_column="high",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "low",
                            models.DecimalField(
                                db_column="low",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "close",
                            models.DecimalField(
                                db_column="close",
                                decimal_places=2,
                                max_digits=12,
                                null=True,
                            ),
                        ),
                        (
                            "volume",
                            models.BigIntegerField(db_column="volume", default=0),
                        ),
                        (
                            "amount",
                            models.DecimalField(
                                db_column="amount",
                                decimal_places=2,
                                default=0,
                                max_digits=20,
                            ),
                        ),
                        (
                            "trade_count",
                            models.IntegerField(db_column="trade_count", default=0),
                        ),
                        (
                            "source",
                            models.CharField(
                                db_column="source", default="realtime", max_length=20
                            ),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, db_column="created_at"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(auto_now=True, db_column="updated_at"),
                        ),
                    ],
                    options={
                        "db_table": "stock_prices_1d",
                        "ordering": ["-bucket"],
                        "unique_together": {("stock_code", "bucket")},
                        "managed": False,
                    },
                ),
            ],
        ),
    ]
