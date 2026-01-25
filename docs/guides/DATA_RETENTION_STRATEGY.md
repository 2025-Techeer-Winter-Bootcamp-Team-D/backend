# 데이터 보관 전략 (Data Retention Strategy)

## 개요

`stock_ticks` 테이블은 실시간 주가 데이터가 계속 쌓이므로, 저장 공간 관리와 성능 최적화를 위해 데이터 보관 정책을 수립했습니다.

## 전략 원칙

1. **원본 데이터 최소화**: 원본 tick 데이터는 Continuous Aggregates로 집계되므로 짧은 기간만 보관
2. **계층적 보관**: 시간 단위가 큰 데이터일수록 더 오래 보관
3. **자동화**: TimescaleDB의 Retention Policy를 사용하여 자동 관리

## 보관 정책

| 데이터 타입 | 보관 기간 | 삭제 기준 | 비고 |
|------------|----------|----------|------|
| `stock_ticks` (원본) | **7일** | 7일 지난 데이터 자동 삭제 | Continuous Aggregates로 집계되므로 짧게 보관 |
| `stock_prices_1m` (1분봉) | **30일** | 30일 지난 데이터 자동 삭제 | 단기 분석용 |
| `stock_prices_15m` (15분봉) | **90일** | 90일 지난 데이터 자동 삭제 | 중기 분석용 |
| `stock_prices_1h` (1시간봉) | **1년** | 1년 지난 데이터 자동 삭제 | 장기 추세 분석용 |
| `stock_prices_1d` (1일봉) | **무기한** | 삭제하지 않음 | 최종 보관 데이터 |

## 구현 방법

TimescaleDB의 `add_retention_policy` 함수를 사용하여 자동 삭제 정책을 설정합니다:

```sql
-- 원본 tick 데이터: 7일 보관
SELECT add_retention_policy('stock_ticks', INTERVAL '7 days');

-- 1분봉: 30일 보관
SELECT add_retention_policy('stock_prices_1m', INTERVAL '30 days');

-- 15분봉: 90일 보관
SELECT add_retention_policy('stock_prices_15m', INTERVAL '90 days');

-- 1시간봉: 1년 보관
SELECT add_retention_policy('stock_prices_1h', INTERVAL '1 year');
```

## 데이터 흐름

```
실시간 Tick 데이터 (stock_ticks)
    ↓ [7일 후 자동 삭제]
    ↓
집계 (Continuous Aggregates)
    ↓
1분봉 (30일) → 15분봉 (90일) → 1시간봉 (1년) → 1일봉 (무기한)
```

## 예상 데이터량 (참고)

- **실시간 Tick 데이터**: 약 500개 종목 × 평균 100건/분 × 7일 = 약 5억 건
- **1분봉**: 500개 종목 × 1440분/일 × 30일 = 약 2,160만 건
- **1일봉**: 500개 종목 × 365일/년 = 약 18만 건/년

## 정책 조정

보관 기간은 실제 사용 패턴과 저장 공간에 따라 조정할 수 있습니다:

```sql
-- 정책 제거
SELECT remove_retention_policy('stock_ticks');

-- 새로운 보관 기간으로 재설정
SELECT add_retention_policy('stock_ticks', INTERVAL '14 days');
```

## 모니터링

데이터 보관 정책이 제대로 작동하는지 확인:

```sql
-- 정책 목록 확인
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_retention';

-- 테이블 크기 확인
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename LIKE 'stock_%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## 주의사항

1. **Continuous Aggregates와의 관계**: 원본 데이터가 삭제되면 Continuous Aggregates의 자동 갱신 범위에 영향을 줍니다
2. **백업**: 중요한 데이터는 별도 백업 전략을 수립해야 합니다
3. **복구**: 삭제된 데이터는 복구할 수 없으므로 필요한 경우 먼저 백업하세요
