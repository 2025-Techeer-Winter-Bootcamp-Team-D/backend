# yfinance 과거 데이터 동기화 API 구현 계획

## 1. 개요

### 1.1 목적
- yfinance API를 통해 한국 주식의 과거 OHLCV 데이터를 수집
- 실시간 Continuous Aggregate 데이터를 통합 테이블에 동기화
- 단일 테이블에서 과거 + 실시간 데이터 모두 조회 가능

### 1.2 데이터 수집 범위

| 시간 단위 | yfinance 수집 기간 | 최종 테이블 |
|-----------|-------------------|-------------|
| 1분봉 | 하루 (1d) | `stock_prices_1m` |
| 15분봉 | 5일 (5d) | `stock_prices_15m` |
| 1시간봉 | 1달 (1mo) | `stock_prices_1h` |
| 1일봉 | 1년 (1y) | `stock_prices_1d` |

### 1.3 yfinance 한국 주식 티커 형식
- **KOSPI**: `{종목코드}.KS` (예: `005930.KS` = 삼성전자)
- **KOSDAQ**: `{종목코드}.KQ` (예: `035720.KQ` = 카카오)

---

## 2. 시스템 아키텍처

### 2.1 통합 테이블 구조

기존 Continuous Aggregate를 **일반 테이블**로 대체하고, 두 가지 소스에서 데이터를 통합합니다.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        데이터 흐름                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   [yfinance API]                      [KIS WebSocket]               │
│        │                                    │                       │
│        │ (과거 데이터)                       │ (실시간)               │
│        │                                    ▼                       │
│        │                            ┌─────────────────┐             │
│        │                            │   stock_ticks   │             │
│        │                            │  (hypertable)   │             │
│        │                            └────────┬────────┘             │
│        │                                     │                      │
│        │                                     ▼                      │
│        │                            ┌─────────────────┐             │
│        │                            │ _cagg_1m/15m/   │             │
│        │                            │ 1h/1d (내부용)   │             │
│        │                            │ Continuous Agg  │             │
│        │                            └────────┬────────┘             │
│        │                                     │                      │
│        │         ┌───────────────────────────┘                      │
│        │         │ (주기적 동기화: 30초~1시간)                        │
│        ▼         ▼                                                  │
│   ┌─────────────────────────────────────────┐                       │
│   │         stock_prices_1m/15m/1h/1d       │                       │
│   │            (통합 테이블)                  │                       │
│   │   - yfinance 과거 데이터                 │                       │
│   │   - 실시간 Continuous Aggregate 데이터   │                       │
│   └─────────────────────────────────────────┘                       │
│                        │                                            │
│                        ▼                                            │
│                   [API 조회]                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 장점
- **단일 테이블 조회**: JOIN이나 UNION 없이 모든 데이터 조회
- **간단한 API**: 클라이언트는 하나의 테이블만 알면 됨
- **Continuous Aggregate 활용**: 실시간 집계는 TimescaleDB가 자동 처리
- **과거 데이터 보존**: yfinance 데이터는 영구 보관

---

## 3. 데이터베이스 스키마 변경

### 3.1 마이그레이션 전략

1. **기존 Continuous Aggregate 유지** (내부 집계용)
2. **통합 테이블 새로 생성** (최종 조회용)
3. **동기화 프로세스 추가**

### 3.2 통합 테이블 스키마

```sql
-- 1분봉 통합 테이블
CREATE TABLE IF NOT EXISTS stock_prices_1m (
    bucket TIMESTAMP NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    open DECIMAL(12, 2),
    high DECIMAL(12, 2),
    low DECIMAL(12, 2),
    close DECIMAL(12, 2),
    volume BIGINT,
    amount DECIMAL(20, 2),
    trade_count INTEGER DEFAULT 0,
    source VARCHAR(20) DEFAULT 'realtime',  -- 'yfinance' or 'realtime'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_code, bucket)
);

-- 15분봉 통합 테이블
CREATE TABLE IF NOT EXISTS stock_prices_15m (
    bucket TIMESTAMP NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    open DECIMAL(12, 2),
    high DECIMAL(12, 2),
    low DECIMAL(12, 2),
    close DECIMAL(12, 2),
    volume BIGINT,
    amount DECIMAL(20, 2),
    trade_count INTEGER DEFAULT 0,
    source VARCHAR(20) DEFAULT 'realtime',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_code, bucket)
);

-- 1시간봉 통합 테이블
CREATE TABLE IF NOT EXISTS stock_prices_1h (
    bucket TIMESTAMP NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    open DECIMAL(12, 2),
    high DECIMAL(12, 2),
    low DECIMAL(12, 2),
    close DECIMAL(12, 2),
    volume BIGINT,
    amount DECIMAL(20, 2),
    trade_count INTEGER DEFAULT 0,
    source VARCHAR(20) DEFAULT 'realtime',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_code, bucket)
);

-- 1일봉 통합 테이블
CREATE TABLE IF NOT EXISTS stock_prices_1d (
    bucket TIMESTAMP NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    open DECIMAL(12, 2),
    high DECIMAL(12, 2),
    low DECIMAL(12, 2),
    close DECIMAL(12, 2),
    volume BIGINT,
    amount DECIMAL(20, 2),
    trade_count INTEGER DEFAULT 0,
    source VARCHAR(20) DEFAULT 'realtime',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_code, bucket)
);

-- 인덱스
CREATE INDEX idx_prices_1m_bucket ON stock_prices_1m(bucket DESC);
CREATE INDEX idx_prices_15m_bucket ON stock_prices_15m(bucket DESC);
CREATE INDEX idx_prices_1h_bucket ON stock_prices_1h(bucket DESC);
CREATE INDEX idx_prices_1d_bucket ON stock_prices_1d(bucket DESC);
```

### 3.3 내부용 Continuous Aggregate (이름 변경)

```sql
-- 기존 Continuous Aggregate를 내부용으로 이름 변경
-- _cagg_* 접두사로 내부용임을 명시

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

-- 15분봉, 1시간봉, 1일봉도 동일 패턴
```

---

## 4. 동기화 프로세스

### 4.1 Continuous Aggregate → 통합 테이블 동기화

```python
# core/tasks/price_sync.py

from celery import shared_task
from django.db import connection


@shared_task
def sync_cagg_to_prices_1m():
    """
    1분봉 Continuous Aggregate → 통합 테이블 동기화
    30초마다 실행
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO stock_prices_1m (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
            SELECT 
                bucket, stock_code, open, high, low, close, volume, amount, trade_count, 
                'realtime', CURRENT_TIMESTAMP
            FROM _cagg_1m
            WHERE bucket >= NOW() - INTERVAL '10 minutes'
            ON CONFLICT (stock_code, bucket) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                trade_count = EXCLUDED.trade_count,
                source = 'realtime',
                updated_at = CURRENT_TIMESTAMP
        """)
        return cursor.rowcount


@shared_task
def sync_cagg_to_prices_15m():
    """15분봉 동기화 - 5분마다 실행"""
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO stock_prices_15m (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
            SELECT 
                bucket, stock_code, open, high, low, close, volume, amount, trade_count, 
                'realtime', CURRENT_TIMESTAMP
            FROM _cagg_15m
            WHERE bucket >= NOW() - INTERVAL '1 hour'
            ON CONFLICT (stock_code, bucket) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                trade_count = EXCLUDED.trade_count,
                source = 'realtime',
                updated_at = CURRENT_TIMESTAMP
        """)
        return cursor.rowcount


@shared_task
def sync_cagg_to_prices_1h():
    """1시간봉 동기화 - 15분마다 실행"""
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO stock_prices_1h (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
            SELECT 
                bucket, stock_code, open, high, low, close, volume, amount, trade_count, 
                'realtime', CURRENT_TIMESTAMP
            FROM _cagg_1h
            WHERE bucket >= NOW() - INTERVAL '4 hours'
            ON CONFLICT (stock_code, bucket) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                trade_count = EXCLUDED.trade_count,
                source = 'realtime',
                updated_at = CURRENT_TIMESTAMP
        """)
        return cursor.rowcount


@shared_task
def sync_cagg_to_prices_1d():
    """1일봉 동기화 - 1시간마다 실행"""
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO stock_prices_1d (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
            SELECT 
                bucket, stock_code, open, high, low, close, volume, amount, trade_count, 
                'realtime', CURRENT_TIMESTAMP
            FROM _cagg_1d
            WHERE bucket >= NOW() - INTERVAL '3 days'
            ON CONFLICT (stock_code, bucket) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                trade_count = EXCLUDED.trade_count,
                source = 'realtime',
                updated_at = CURRENT_TIMESTAMP
        """)
        return cursor.rowcount
```

### 4.2 Celery Beat 스케줄 설정

```python
# config/celery.py

from celery.schedules import crontab

app.conf.beat_schedule = {
    # 1분봉: 30초마다 동기화
    'sync-1m-every-30-seconds': {
        'task': 'core.tasks.price_sync.sync_cagg_to_prices_1m',
        'schedule': 30.0,
    },
    # 15분봉: 5분마다 동기화
    'sync-15m-every-5-minutes': {
        'task': 'core.tasks.price_sync.sync_cagg_to_prices_15m',
        'schedule': crontab(minute='*/5'),
    },
    # 1시간봉: 15분마다 동기화
    'sync-1h-every-15-minutes': {
        'task': 'core.tasks.price_sync.sync_cagg_to_prices_1h',
        'schedule': crontab(minute='*/15'),
    },
    # 1일봉: 1시간마다 동기화
    'sync-1d-every-hour': {
        'task': 'core.tasks.price_sync.sync_cagg_to_prices_1d',
        'schedule': crontab(minute=0),
    },
}
```

---

## 5. yfinance 과거 데이터 동기화

### 5.1 YFinanceService 클래스

```python
# core/services/yfinance_service.py

import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class YFinanceService:
    """yfinance를 통한 과거 주가 데이터 수집 서비스"""
    
    INTERVAL_CONFIG = {
        "1m": {"period": "1d", "table": "stock_prices_1m"},
        "15m": {"period": "5d", "table": "stock_prices_15m"},
        "1h": {"period": "1mo", "table": "stock_prices_1h"},
        "1d": {"period": "1y", "table": "stock_prices_1d"},
    }
    
    def __init__(self):
        self.delay_between_requests = 1.0  # Rate limit 방지
    
    def get_ticker_symbol(self, stock_code: str, market: str = "KOSPI") -> str:
        """
        종목코드를 yfinance 티커 형식으로 변환
        """
        suffix = ".KS" if market == "KOSPI" else ".KQ"
        return f"{stock_code}{suffix}"
    
    def fetch_ohlcv(self, stock_code: str, interval: str, market: str = "KOSPI") -> Optional[pd.DataFrame]:
        """
        yfinance에서 OHLCV 데이터 가져오기
        """
        if interval not in self.INTERVAL_CONFIG:
            raise ValueError(f"Invalid interval: {interval}")
        
        config = self.INTERVAL_CONFIG[interval]
        ticker_symbol = self.get_ticker_symbol(stock_code, market)
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period=config["period"], interval=interval)
            
            if df.empty:
                logger.warning(f"No data returned for {ticker_symbol} ({interval})")
                return None
            
            # 컬럼명 정규화
            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            
            df = df[["open", "high", "low", "close", "volume"]]
            df["stock_code"] = stock_code
            df["amount"] = df["close"] * df["volume"]
            df["trade_count"] = 0
            df["source"] = "yfinance"
            
            df = df.reset_index()
            df = df.rename(columns={"Datetime": "bucket", "Date": "bucket"})
            
            # 타임존 제거
            if df["bucket"].dt.tz is not None:
                df["bucket"] = df["bucket"].dt.tz_localize(None)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching {ticker_symbol}: {e}")
            return None
    
    def sync_stock_history(
        self, 
        stock_code: str, 
        intervals: List[str] = None,
        market: str = "KOSPI",
        force: bool = False
    ) -> Dict[str, any]:
        """
        특정 종목의 히스토리 데이터 동기화
        """
        if intervals is None:
            intervals = ["1m", "15m", "1h", "1d"]
        
        results = {}
        
        for interval in intervals:
            try:
                df = self.fetch_ohlcv(stock_code, interval, market)
                
                if df is None or df.empty:
                    results[interval] = {"saved": 0, "status": "no_data"}
                    continue
                
                saved_count = self._save_to_database(
                    df, 
                    self.INTERVAL_CONFIG[interval]["table"],
                    force=force
                )
                results[interval] = {"saved": saved_count, "status": "success"}
                
            except Exception as e:
                logger.exception(f"Error syncing {stock_code} {interval}")
                results[interval] = {"saved": 0, "status": "error", "message": str(e)}
        
        return results
    
    def _save_to_database(self, df: pd.DataFrame, table_name: str, force: bool = False) -> int:
        """DataFrame을 DB에 저장 (UPSERT)"""
        with connection.cursor() as cursor:
            saved_count = 0
            
            for _, row in df.iterrows():
                if force:
                    sql = f"""
                        INSERT INTO {table_name} 
                        (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (stock_code, bucket) DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount,
                            source = EXCLUDED.source,
                            updated_at = CURRENT_TIMESTAMP
                    """
                else:
                    # force=False: 기존 데이터가 있으면 건너뛰기
                    sql = f"""
                        INSERT INTO {table_name} 
                        (bucket, stock_code, open, high, low, close, volume, amount, trade_count, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (stock_code, bucket) DO NOTHING
                    """
                
                cursor.execute(sql, [
                    row["bucket"],
                    row["stock_code"],
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["volume"]),
                    float(row["amount"]),
                    int(row["trade_count"]),
                    row["source"],
                ])
                saved_count += cursor.rowcount
        
        return saved_count
```

---

## 6. API 엔드포인트

### 6.1 단일 종목 동기화

```python
# core/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from core.services.yfinance_service import YFinanceService
from core.tasks.yfinance_sync import sync_stock_history_task


@extend_schema(
    summary="주가 히스토리 동기화 (관리자용)",
    description="""
    yfinance API를 통해 과거 OHLCV 데이터를 동기화합니다.
    
    - 1분봉: 최근 1일
    - 15분봉: 최근 5일
    - 1시간봉: 최근 1달
    - 1일봉: 최근 1년
    """,
    parameters=[
        OpenApiParameter(name="stock_code", type=str, location=OpenApiParameter.PATH),
        OpenApiParameter(name="intervals", type=str, location=OpenApiParameter.QUERY, 
                        description="동기화할 간격 (콤마 구분: 1m,15m,1h,1d)", required=False),
        OpenApiParameter(name="market", type=str, location=OpenApiParameter.QUERY,
                        description="시장 구분 (KOSPI/KOSDAQ)", required=False),
        OpenApiParameter(name="async", type=bool, location=OpenApiParameter.QUERY,
                        description="비동기 실행 여부", required=False),
        OpenApiParameter(name="force", type=bool, location=OpenApiParameter.QUERY,
                        description="기존 데이터 덮어쓰기", required=False),
    ],
    responses={
        200: OpenApiResponse(description="동기화 완료"),
        202: OpenApiResponse(description="비동기 작업 시작됨"),
        400: OpenApiResponse(description="잘못된 요청"),
        401: OpenApiResponse(description="인증 필요"),
    },
    tags=["Admin - Stock Data"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_stock_history(request, stock_code):
    """단일 종목 히스토리 동기화 API"""
    
    # 파라미터 파싱
    intervals_param = request.query_params.get("intervals", "1m,15m,1h,1d")
    intervals = [i.strip() for i in intervals_param.split(",")]
    market = request.query_params.get("market", "KOSPI")
    use_async = request.query_params.get("async", "true").lower() == "true"
    force = request.query_params.get("force", "false").lower() == "true"
    
    # 유효성 검사
    valid_intervals = ["1m", "15m", "1h", "1d"]
    for interval in intervals:
        if interval not in valid_intervals:
            return Response(
                {"error": f"Invalid interval: {interval}. Valid: {valid_intervals}"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    if use_async:
        # Celery 태스크로 실행
        task = sync_stock_history_task.delay(stock_code, intervals, market, force)
        return Response({
            "status": 202,
            "message": "동기화 작업이 시작되었습니다.",
            "data": {
                "task_id": task.id,
                "stock_code": stock_code,
                "intervals": intervals,
                "market": market,
            }
        }, status=status.HTTP_202_ACCEPTED)
    else:
        # 동기 실행
        service = YFinanceService()
        results = service.sync_stock_history(stock_code, intervals, market, force)
        return Response({
            "status": 200,
            "message": "동기화 완료",
            "data": {
                "stock_code": stock_code,
                "results": results,
            }
        }, status=status.HTTP_200_OK)
```

### 6.2 URL 설정

```python
# core/urls.py

from django.urls import path
from .views import health_check, sync_stock_history

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('admin/stocks/<str:stock_code>/sync-history/', sync_stock_history, name='sync_stock_history'),
]
```

---

## 7. 구현 단계

### Phase 1: 데이터베이스 스키마 변경 (1일)
- [ ] 기존 Continuous Aggregate 이름 변경 (`_cagg_*`)
- [ ] 통합 테이블 생성 (`stock_prices_*`)
- [ ] 인덱스 생성
- [ ] 마이그레이션 작성

### Phase 2: 동기화 프로세스 구현 (1일)
- [ ] Continuous Aggregate → 통합 테이블 동기화 태스크
- [ ] Celery Beat 스케줄 설정
- [ ] 동기화 상태 모니터링

### Phase 3: yfinance 서비스 구현 (1일)
- [ ] YFinanceService 클래스
- [ ] KOSPI/KOSDAQ 시장 구분
- [ ] 에러 핸들링 및 재시도 로직

### Phase 4: API 엔드포인트 (1일)
- [ ] 단일 종목 동기화 API
- [ ] Swagger 문서화
- [ ] 인증/권한 설정

### Phase 5: 테스트 및 최적화 (1일)
- [ ] 단위 테스트
- [ ] 통합 테스트
- [ ] 대량 데이터 성능 테스트

---

## 8. 데이터 보관 정책

### 8.1 통합 테이블 보관 정책

| 테이블 | 보관 기간 | 설명 |
|--------|----------|------|
| `stock_prices_1m` | 30일 | yfinance(1일) + 실시간 |
| `stock_prices_15m` | 90일 | yfinance(5일) + 실시간 |
| `stock_prices_1h` | 1년 | yfinance(1달) + 실시간 |
| `stock_prices_1d` | **무기한** | yfinance(1년) + 실시간 |

### 8.2 자동 정리 (선택사항)

```sql
-- 통합 테이블에도 retention policy 적용 가능
-- 단, TimescaleDB hypertable로 변환 필요

SELECT create_hypertable('stock_prices_1m', 'bucket', if_not_exists => TRUE);
SELECT add_retention_policy('stock_prices_1m', INTERVAL '30 days', if_not_exists => TRUE);
```

---

## 9. 주의사항

### 9.1 yfinance 제한사항
- **1분봉**: 최근 7일까지만 조회 가능
- **Rate Limit**: 과도한 요청 시 IP 차단 가능
- **데이터 정확도**: 비공식 Yahoo Finance 데이터

### 9.2 동기화 충돌 방지
- yfinance 데이터는 `source = 'yfinance'`
- 실시간 데이터는 `source = 'realtime'`
- 실시간 데이터가 yfinance 데이터를 **덮어씀** (더 정확)

### 9.3 권장 운영 방식
1. **초기 설정**: yfinance로 과거 데이터 일괄 동기화
2. **일상 운영**: Celery Beat으로 실시간 데이터 자동 동기화
3. **주기적 보완**: 장 마감 후 yfinance로 누락 데이터 보완

---

## 10. 의존성

```txt
# requirements.txt에 추가
yfinance>=0.2.36
pandas>=2.0.0
```

---

## 11. 참고 자료

- [yfinance 공식 문서](https://pypi.org/project/yfinance/)
- [TimescaleDB Continuous Aggregates](https://docs.timescale.com/timescaledb/latest/how-to-guides/continuous-aggregates/)
- [Celery Beat Scheduler](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html)
