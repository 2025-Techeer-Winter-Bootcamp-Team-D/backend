# 실시간 주가 동적 구독 기능 구현 계획

## 개요

프론트엔드에서 사용자가 보는 페이지에 따라 동적으로 종목을 구독/해제하는 기능 구현.
KIS API의 40개 종목 제한을 효율적으로 관리.

## 상태

- **작성일**: 2025-01-24
- **구현 완료일**: 2025-01-24
- **상태**: ✅ 구현 완료

## 아키텍처

```
┌─────────────┐     WebSocket      ┌───────────────────┐      RPC       ┌───────────────┐
│  Frontend   │ ◄─────────────────►│ StockPriceConsumer│ ◄─────────────►│ kis-publisher │
└─────────────┘                    └───────────────────┘                └───────────────┘
                                            │                                   │
                                            ▼                                   ▼
                                   ┌────────────────┐                  ┌────────────────┐
                                   │  Redis (상태)   │                  │   KIS API      │
                                   └────────────────┘                  └────────────────┘
                                            │                                   │
                                            └───────────► RabbitMQ ◄────────────┘
```

## 구현 순서

### Phase 1: Redis 구독 상태 관리 서비스 ✅

**파일**: `core/services/subscription_manager.py` (신규)

- `SubscriptionManager` 클래스 구현
- Redis 키 구조:
  - `subscription:clients:{channel}` - 클라이언트별 구독 종목
  - `subscription:stocks:{code}` - 종목별 구독 클라이언트
  - `subscription:active` - KIS에 실제 구독 중인 종목
- RabbitMQ RPC로 kis-publisher와 통신

### Phase 2: WebSocket Consumer 수정 ✅

**파일**: `core/consumers.py` (수정)

- `receive()` 메서드에 subscribe/unsubscribe 액션 추가
- 클라이언트별 구독 상태 추적 (`self.subscribed_codes`)
- 종목별 Channels 그룹 가입/탈퇴 (`stock_{code}`)
- 연결 해제 시 cleanup 처리

### Phase 3: subscribe-handler 수정 ✅

**파일**: `core/management/commands/subscribe_handler.py` (수정)

- 전체 브로드캐스트 → 종목별 그룹 브로드캐스트 변경
- `group_send("stock_prices", ...)` → `group_send(f"stock_{code}", ...)`

### Phase 4: kis-publisher 동적 구독 ✅

**파일**: `kis-publisher/subscription_handler.py` (신규)

- `SubscriptionHandler` 클래스
- KIS 구독 메시지 (tr_type: "1")
- KIS 해제 메시지 (tr_type: "2")
- 40개 제한 관리

**파일**: `kis-publisher/main.py` (수정)

- RPC 큐 (`subscription.commands`) 구독
- `SubscriptionHandler` 통합
- 재연결 시 구독 복원

### Phase 5: 테스트 ✅

**파일**: `kis-publisher/mock_server.py` (수정)

- 기존 mock_server에 동적 구독/해제 테스트 지원 추가
- RPC 명령 처리 시뮬레이션

## WebSocket 프로토콜

### 요청 메시지

```json
// 종목 구독
{"action": "subscribe", "codes": ["005930", "000660"]}

// 종목 구독 해제
{"action": "unsubscribe", "codes": ["005930"]}

// 구독 목록 조회
{"action": "list_subscriptions"}

// 연결 확인
{"action": "ping"}
```

### 응답 메시지

```json
// 구독 결과
{
  "type": "subscription_result",
  "success": true,
  "subscribed": ["005930"],
  "failed": [],
  "error": null,
  "total_subscribed": 1
}

// 실시간 주가 데이터
{
  "type": "stock_price",
  "stock_code": "005930",
  "price": 70000,
  "volume": 1000,
  "time": "143052"
}

// 구독 목록
{
  "type": "subscriptions_list",
  "subscribed_codes": ["005930", "000660"],
  "count": 2,
  "kis_active_subscriptions": 15,
  "kis_max_subscriptions": 40
}
```

## 수정 파일 목록

| 파일 | 작업 | 상태 |
|------|------|------|
| `core/services/subscription_manager.py` | 신규 | ✅ |
| `core/consumers.py` | 수정 | ✅ |
| `core/management/commands/subscribe_handler.py` | 수정 | ✅ |
| `kis-publisher/subscription_handler.py` | 신규 | ✅ |
| `kis-publisher/main.py` | 수정 | ✅ |
| `kis-publisher/mock_server.py` | 수정 | ✅ |

## 데이터 흐름

### 구독 요청 흐름

```
1. Frontend: {"action": "subscribe", "codes": ["005930"]}
2. StockPriceConsumer.receive() → _handle_subscribe()
3. SubscriptionManager.subscribe()
   - Redis에서 기존 구독자 확인
   - 새 종목이면 RPC로 kis-publisher에 구독 요청
4. kis-publisher: SubscriptionHandler.subscribe()
   - KIS WebSocket에 구독 메시지 전송 (tr_type: "1")
5. Redis 상태 업데이트
6. StockPriceConsumer: Channels 그룹 가입 (stock_{code})
7. Frontend에 구독 결과 응답
```

### 실시간 데이터 흐름

```
1. KIS API → kis-publisher: 체결 데이터 수신
2. kis-publisher → RabbitMQ: 메시지 발행 (stock.realtime exchange)
3. subscribe_handler: RabbitMQ 구독 → Channels 그룹 전송
4. StockPriceConsumer.stock_price_update() → Frontend
```

### 구독 해제 흐름

```
1. Frontend: {"action": "unsubscribe", "codes": ["005930"]}
   또는 WebSocket 연결 종료
2. SubscriptionManager.unsubscribe() 또는 cleanup_client()
3. Redis에서 클라이언트 제거
4. 해당 종목 구독자가 0명이면:
   - RPC로 kis-publisher에 해제 요청
   - kis-publisher: KIS에 해제 메시지 전송 (tr_type: "2")
5. StockPriceConsumer: Channels 그룹 탈퇴
```

## 검증 방법

### 기본 기능 테스트

1. ✅ WebSocket 클라이언트로 연결 테스트
2. ✅ 구독 요청 후 실시간 데이터 수신 확인
3. ✅ 구독 해제 후 데이터 중단 확인
4. ✅ 40개 초과 시 에러 응답 확인
5. ✅ 클라이언트 연결 해제 시 자동 정리 확인

### 테스트 명령

```bash
# Mock 서버 실행
python kis-publisher/mock_server.py

# Docker 환경 실행 (테스트 모드)
KIS_USE_TEST_MODE=true docker-compose up

# WebSocket 테스트 (websocat)
websocat ws://localhost:8000/ws/stock/
> {"action": "subscribe", "codes": ["005930"]}
> {"action": "list_subscriptions"}
> {"action": "unsubscribe", "codes": ["005930"]}
```

## 관련 문서

- [실시간 주가 WebSocket API](../REALTIME-STOCK-WEBSOCKET-API.md)
- [시스템 아키텍처](../SYSTEM_ARCHITECTURE.md)

## 향후 개선 사항

1. **JWT 인증 추가**: WebSocket 연결 시 토큰 검증
2. **구독 우선순위**: 인기 종목 우선 구독 로직
3. **캐싱 최적화**: 최근 체결가 Redis 캐싱
4. **모니터링**: 구독 상태 Prometheus 메트릭 추가
