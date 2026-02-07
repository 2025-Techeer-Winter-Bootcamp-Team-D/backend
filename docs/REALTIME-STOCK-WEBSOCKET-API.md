# 실시간 주가 WebSocket API

실시간 주가 데이터를 수신하기 위한 WebSocket API 문서입니다.

## 개요

- **프로토콜**: WebSocket
- **엔드포인트**: `ws://localhost:8000/ws/stock/` (개발) / `wss://your-domain.com/ws/stock/` (프로덕션)
- **인증**: 현재 미적용 (추후 JWT 토큰 인증 추가 예정)
- **최대 구독 종목**: 40개 (KIS API 제한)

---

## 빠른 시작 (Quick Start)

### 30초 만에 실시간 주가 받기

```javascript
// 1. 연결
const ws = new WebSocket('ws://localhost:8000/ws/stock/');

// 2. 연결되면 삼성전자 구독
ws.onopen = () => {
  ws.send(JSON.stringify({ action: 'subscribe', codes: ['005930'] }));
};

// 3. 실시간 데이터 수신
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'stock_price') {
    console.log(`${data.stock_code}: ${data.price.toLocaleString()}원`);
  }
};
```

**출력 예시:**
```
005930: 71,500원
005930: 71,520원
005930: 71,480원
```

---

## 연결 흐름

### 전체 흐름도

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              연결 및 구독 흐름                                  │
└──────────────────────────────────────────────────────────────────────────────┘

  프론트엔드                          백엔드                            KIS API
      │                                │                                   │
      │  1. WebSocket 연결 요청         │                                   │
      │ ─────────────────────────────► │                                   │
      │                                │                                   │
      │  2. connection_established     │                                   │
      │ ◄───────────────────────────── │                                   │
      │                                │                                   │
      │  3. subscribe ["005930"]       │                                   │
      │ ─────────────────────────────► │                                   │
      │                                │  4. 종목 구독 요청                  │
      │                                │ ─────────────────────────────────► │
      │                                │                                   │
      │  5. subscription_result        │  구독 성공                         │
      │ ◄───────────────────────────── │ ◄───────────────────────────────── │
      │                                │                                   │
      │                                │  6. 실시간 체결 데이터              │
      │  7. stock_price (반복)          │ ◄───────────────────────────────── │
      │ ◄───────────────────────────── │                                   │
      │ ◄───────────────────────────── │                                   │
      │ ◄───────────────────────────── │                                   │
      │                                │                                   │
      │  8. unsubscribe ["005930"]     │                                   │
      │ ─────────────────────────────► │  9. 구독 해제                      │
      │                                │ ─────────────────────────────────► │
      │                                │                                   │
      │  10. unsubscription_result     │                                   │
      │ ◄───────────────────────────── │                                   │
      │                                │                                   │
      ▼                                ▼                                   ▼
```

### 연결 상태 다이어그램

```
┌─────────┐     연결 성공      ┌─────────┐     종목 구독      ┌─────────┐
│  연결중  │ ───────────────► │  연결됨  │ ───────────────► │ 구독 중  │
└─────────┘                   └─────────┘                   └─────────┘
     │                             │                             │
     │ 연결 실패                    │ 연결 끊김                    │ 구독 해제
     ▼                             ▼                             ▼
┌─────────┐     재연결 시도    ┌─────────┐                   ┌─────────┐
│  에러   │ ◄───────────────  │ 재연결중 │                   │  연결됨  │
└─────────┘                   └─────────┘                   └─────────┘
```

---

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

## 연결

### 단계별 연결 가이드

#### Step 1: WebSocket 객체 생성

```javascript
// 개발 환경
const ws = new WebSocket('ws://localhost:8000/ws/stock/');

// 프로덕션 환경 (HTTPS 사이트에서는 반드시 wss:// 사용)
const ws = new WebSocket('wss://your-domain.com/ws/stock/');
```

> ⚠️ **주의**: HTTPS 페이지에서 `ws://`로 연결하면 Mixed Content 에러가 발생합니다.

#### Step 2: 이벤트 핸들러 등록

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/stock/');

// 연결 성공
ws.onopen = () => {
  console.log('✅ WebSocket 연결 성공');
  // 여기서 구독 요청을 보내면 됩니다
};

// 메시지 수신
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('📥 메시지 수신:', data);

  // 메시지 타입별 처리
  switch (data.type) {
    case 'connection_established':
      console.log('서버 연결 확인됨');
      break;
    case 'stock_price':
      console.log(`${data.stock_code}: ${data.price}원`);
      break;
    case 'subscription_result':
      console.log('구독 결과:', data.subscribed);
      break;
    // ... 기타 타입
  }
};

// 연결 종료
ws.onclose = (event) => {
  console.log('❌ 연결 종료:', event.code, event.reason);
  // 재연결 로직 실행
};

// 에러 발생
ws.onerror = (error) => {
  console.error('🚨 에러:', error);
};
```

#### Step 3: 연결 상태 확인

```javascript
// WebSocket readyState 값
// 0 = CONNECTING (연결 중)
// 1 = OPEN (연결됨)
// 2 = CLOSING (종료 중)
// 3 = CLOSED (종료됨)

function isConnected() {
  return ws.readyState === WebSocket.OPEN;
}

// 안전하게 메시지 보내기
function safeSend(message) {
  if (isConnected()) {
    ws.send(JSON.stringify(message));
    return true;
  } else {
    console.warn('WebSocket이 연결되지 않았습니다.');
    return false;
  }
}
```

### 연결 성공 응답

연결 성공 시 서버에서 **자동으로** 다음 메시지를 전송합니다:

```json
{
  "type": "connection_established",
  "message": "실시간 주가 스트림에 연결되었습니다.",
  "actions": ["subscribe", "unsubscribe", "list_subscriptions", "ping"]
}
```

> 💡 **팁**: 이 메시지를 받으면 구독 요청을 보내도 안전합니다.

### 자동 재연결 구현

```javascript
class StockWebSocket {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // 1초부터 시작
    this.subscribedCodes = new Set(); // 구독 중인 종목 저장
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('✅ 연결됨');
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;

      // 재연결 시 이전 구독 복원
      if (this.subscribedCodes.size > 0) {
        this.subscribe([...this.subscribedCodes]);
      }
    };

    this.ws.onclose = (event) => {
      console.log('❌ 연결 종료:', event.code);
      this.scheduleReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('🚨 에러:', error);
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
  }

  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('최대 재연결 시도 횟수 초과');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000);

    console.log(`${delay/1000}초 후 재연결 시도 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    setTimeout(() => this.connect(), delay);
  }

  subscribe(codes) {
    codes.forEach(code => this.subscribedCodes.add(code));
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'subscribe', codes }));
    }
  }

  unsubscribe(codes) {
    codes.forEach(code => this.subscribedCodes.delete(code));
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'unsubscribe', codes }));
    }
  }

  handleMessage(data) {
    // 오버라이드하여 사용
    console.log('메시지:', data);
  }

  disconnect() {
    this.maxReconnectAttempts = 0; // 재연결 방지
    this.ws?.close();
  }
}

// 사용 예시
const stockWs = new StockWebSocket('ws://localhost:8000/ws/stock/');
stockWs.handleMessage = (data) => {
  if (data.type === 'stock_price') {
    document.getElementById('price').textContent = data.price.toLocaleString() + '원';
  }
};
stockWs.connect();
stockWs.subscribe(['005930', '000660']);
```

---

## 클라이언트 → 서버 메시지

### 1. 종목 구독 (subscribe)

특정 종목의 실시간 데이터를 구독합니다.

**요청**:
```json
{
  "action": "subscribe",
  "codes": ["005930", "000660", "035720"]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `action` | string | ✅ | `"subscribe"` 고정 |
| `codes` | string[] | ✅ | 종목 코드 배열 (6자리 숫자) |

**응답**:
```json
{
  "type": "subscription_result",
  "success": true,
  "subscribed": ["005930", "000660"],
  "failed": ["035720"],
  "error": null,
  "total_subscribed": 2
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | string | `"subscription_result"` |
| `success` | boolean | 모든 종목 구독 성공 여부 |
| `subscribed` | string[] | 구독 성공한 종목 코드 |
| `failed` | string[] | 구독 실패한 종목 코드 |
| `error` | string \| null | 에러 메시지 |
| `total_subscribed` | number | 현재 구독 중인 총 종목 수 |

**에러 케이스**:
- 40개 초과 시: `"error": "40개 종목 구독 실패"` (KIS API 제한)
- 잘못된 종목 코드: `"failed"` 배열에 포함

---

### 2. 종목 구독 해제 (unsubscribe)

구독 중인 종목의 실시간 데이터 수신을 중단합니다.

**요청**:
```json
{
  "action": "unsubscribe",
  "codes": ["005930"]
}
```

**응답**:
```json
{
  "type": "unsubscription_result",
  "success": true,
  "unsubscribed": ["005930"],
  "error": null,
  "total_subscribed": 1
}
```

---

### 3. 구독 목록 조회 (list_subscriptions)

현재 구독 중인 종목 목록을 조회합니다.

**요청**:
```json
{
  "action": "list_subscriptions"
}
```

**응답**:
```json
{
  "type": "subscriptions_list",
  "subscribed_codes": ["005930", "000660"],
  "count": 2,
  "kis_active_subscriptions": 15,
  "kis_max_subscriptions": 40
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `subscribed_codes` | string[] | 현재 클라이언트가 구독 중인 종목 |
| `count` | number | 구독 중인 종목 수 |
| `kis_active_subscriptions` | number | KIS에서 전체 활성 구독 수 |
| `kis_max_subscriptions` | number | KIS 최대 구독 가능 수 (40) |

---

### 4. 연결 확인 (ping)

연결 상태를 확인합니다.

**요청**:
```json
{
  "action": "ping"
}
```

**응답**:
```json
{
  "type": "pong"
}
```

---

## 서버 → 클라이언트 메시지

### 실시간 주가 데이터 (stock_price)

구독 중인 종목의 체결 데이터가 발생하면 자동으로 전송됩니다.

```json
{
  "type": "stock_price",
  "stock_code": "005930",
  "symbol": "001",
  "time": "143052",
  "price": 71500,
  "volume": 150
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | string | `"stock_price"` |
| `stock_code` | string | 종목 코드 (6자리) |
| `symbol` | string | KIS 내부 심볼 ID |
| `time` | string | 체결 시간 (HHMMSS 형식) |
| `price` | number | 체결 가격 |
| `volume` | number | 체결 수량 |

---

### 에러 메시지 (error)

요청 처리 중 에러 발생 시:

```json
{
  "type": "error",
  "message": "Invalid JSON"
}
```

---

### 경고 메시지 (warning)

일부 요청이 처리되지 않았을 때:

```json
{
  "type": "warning",
  "message": "유효하지 않은 종목 코드: ['INVALID']"
}
```

---

## 프론트엔드 구현 예시

### React Hook (TypeScript)

```typescript
// hooks/useStockWebSocket.ts
import { useEffect, useRef, useState, useCallback } from 'react';

interface StockPrice {
  type: 'stock_price';
  stock_code: string;
  symbol: string;
  time: string;
  price: number;
  volume: number;
}

interface SubscriptionResult {
  type: 'subscription_result';
  success: boolean;
  subscribed: string[];
  failed: string[];
  error: string | null;
  total_subscribed: number;
}

interface UnsubscriptionResult {
  type: 'unsubscription_result';
  success: boolean;
  unsubscribed: string[];
  error: string | null;
  total_subscribed: number;
}

interface SubscriptionsList {
  type: 'subscriptions_list';
  subscribed_codes: string[];
  count: number;
  kis_active_subscriptions: number;
  kis_max_subscriptions: number;
}

type WebSocketMessage =
  | StockPrice
  | SubscriptionResult
  | UnsubscriptionResult
  | SubscriptionsList
  | { type: 'connection_established'; message: string }
  | { type: 'pong' }
  | { type: 'error'; message: string }
  | { type: 'warning'; message: string };

export function useStockWebSocket() {
  const ws = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [prices, setPrices] = useState<Map<string, StockPrice>>(new Map());
  const [subscribedCodes, setSubscribedCodes] = useState<string[]>([]);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  const connect = useCallback(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/stock/';
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      console.log('[WS] 연결됨');
      setIsConnected(true);
      reconnectAttempts.current = 0;
    };

    ws.current.onmessage = (event) => {
      const data: WebSocketMessage = JSON.parse(event.data);

      switch (data.type) {
        case 'connection_established':
          console.log('[WS]', data.message);
          break;

        case 'stock_price':
          setPrices(prev => {
            const next = new Map(prev);
            next.set(data.stock_code, data);
            return next;
          });
          break;

        case 'subscription_result':
          if (data.subscribed.length > 0) {
            setSubscribedCodes(prev => [...new Set([...prev, ...data.subscribed])]);
          }
          if (!data.success) {
            console.warn('[WS] 구독 실패:', data.failed, data.error);
          }
          break;

        case 'unsubscription_result':
          if (data.unsubscribed.length > 0) {
            setSubscribedCodes(prev =>
              prev.filter(code => !data.unsubscribed.includes(code))
            );
            // 해제된 종목 가격 데이터 제거
            setPrices(prev => {
              const next = new Map(prev);
              data.unsubscribed.forEach(code => next.delete(code));
              return next;
            });
          }
          break;

        case 'subscriptions_list':
          setSubscribedCodes(data.subscribed_codes);
          break;

        case 'error':
          console.error('[WS] 에러:', data.message);
          break;

        case 'warning':
          console.warn('[WS] 경고:', data.message);
          break;
      }
    };

    ws.current.onclose = (event) => {
      console.log('[WS] 연결 종료:', event.code, event.reason);
      setIsConnected(false);

      // 자동 재연결 (최대 5회)
      if (reconnectAttempts.current < maxReconnectAttempts) {
        reconnectAttempts.current++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
        console.log(`[WS] ${delay}ms 후 재연결 시도 (${reconnectAttempts.current}/${maxReconnectAttempts})`);
        setTimeout(connect, delay);
      }
    };

    ws.current.onerror = (error) => {
      console.error('[WS] 에러:', error);
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [connect]);

  // 종목 구독
  const subscribe = useCallback((codes: string[]) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'subscribe', codes }));
    } else {
      console.warn('[WS] 연결되지 않음. 구독 요청 무시됨.');
    }
  }, []);

  // 종목 구독 해제
  const unsubscribe = useCallback((codes: string[]) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'unsubscribe', codes }));
    }
  }, []);

  // 구독 목록 조회
  const listSubscriptions = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ action: 'list_subscriptions' }));
    }
  }, []);

  // 특정 종목 가격 조회
  const getPrice = useCallback((code: string): StockPrice | undefined => {
    return prices.get(code);
  }, [prices]);

  return {
    isConnected,
    prices,
    subscribedCodes,
    subscribe,
    unsubscribe,
    listSubscriptions,
    getPrice,
  };
}
```

### 컴포넌트 예시

```tsx
// components/StockTicker.tsx
import { useEffect } from 'react';
import { useStockWebSocket } from '@/hooks/useStockWebSocket';

interface StockTickerProps {
  stockCodes: string[];
}

export function StockTicker({ stockCodes }: StockTickerProps) {
  const {
    isConnected,
    prices,
    subscribedCodes,
    subscribe,
    unsubscribe
  } = useStockWebSocket();

  // 컴포넌트 마운트 시 구독, 언마운트 시 해제
  useEffect(() => {
    if (isConnected && stockCodes.length > 0) {
      subscribe(stockCodes);
    }

    return () => {
      if (stockCodes.length > 0) {
        unsubscribe(stockCodes);
      }
    };
  }, [isConnected, stockCodes, subscribe, unsubscribe]);

  return (
    <div className="stock-ticker">
      <div className="connection-status">
        {isConnected ? '🟢 실시간' : '🔴 연결 끊김'}
      </div>

      <ul className="stock-list">
        {stockCodes.map(code => {
          const stock = prices.get(code);
          return (
            <li key={code} className="stock-item">
              <span className="code">{code}</span>
              {stock ? (
                <>
                  <span className="price">{stock.price.toLocaleString()}원</span>
                  <span className="volume">거래량: {stock.volume}</span>
                  <span className="time">{formatTime(stock.time)}</span>
                </>
              ) : (
                <span className="loading">데이터 대기중...</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function formatTime(time: string): string {
  // "143052" -> "14:30:52"
  return `${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`;
}
```

### 페이지 전환 시 구독 관리

```tsx
// pages/stock/[code].tsx
import { useRouter } from 'next/router';
import { useEffect } from 'react';
import { useStockWebSocket } from '@/hooks/useStockWebSocket';

export default function StockDetailPage() {
  const router = useRouter();
  const { code } = router.query;
  const { isConnected, prices, subscribe, unsubscribe } = useStockWebSocket();

  useEffect(() => {
    if (!isConnected || !code || typeof code !== 'string') return;

    // 현재 페이지 종목 구독
    subscribe([code]);

    // 페이지 이탈 시 구독 해제
    return () => {
      unsubscribe([code]);
    };
  }, [isConnected, code, subscribe, unsubscribe]);

  const stockData = code ? prices.get(code as string) : undefined;

  // ... 렌더링
}
```

---

## 주요 종목 코드

| 종목 코드 | 종목명 |
|----------|--------|
| 005930 | 삼성전자 |
| 000660 | SK하이닉스 |
| 035720 | 카카오 |
| 035420 | NAVER |
| 051910 | LG화학 |
| 068270 | 셀트리온 |
| 006400 | 삼성SDI |
| 207940 | 삼성바이오로직스 |
| 373220 | LG에너지솔루션 |
| 105560 | KB금융 |

---

## 에러 처리 가이드

### 연결 실패

```typescript
ws.onerror = (error) => {
  // 네트워크 오류, 서버 다운 등
  console.error('WebSocket 연결 실패:', error);
  // 재연결 로직 실행
};
```

### 구독 제한 초과

KIS API는 최대 40개 종목까지 동시 구독 가능합니다.

```typescript
const result = await subscribe(['005930', ...]);
if (result.failed.length > 0) {
  alert(`구독 제한 초과: ${result.error}`);
}
```

### 잘못된 종목 코드

6자리 숫자가 아닌 종목 코드는 자동으로 필터링됩니다.

```json
{
  "type": "warning",
  "message": "유효하지 않은 종목 코드: ['ABC', '12345']"
}
```

---

## 테스트

### 브라우저 개발자 도구

```javascript
// 연결
const ws = new WebSocket('ws://localhost:8000/ws/stock/');

// 구독
ws.send(JSON.stringify({ action: 'subscribe', codes: ['005930'] }));

// 구독 목록 확인
ws.send(JSON.stringify({ action: 'list_subscriptions' }));

// 해제
ws.send(JSON.stringify({ action: 'unsubscribe', codes: ['005930'] }));
```

### websocat CLI 도구

```bash
# 설치
brew install websocat  # macOS

# 연결 및 테스트
websocat ws://localhost:8000/ws/stock/

# 메시지 전송
{"action": "subscribe", "codes": ["005930"]}
{"action": "list_subscriptions"}
```

---

## 환경 변수

### 백엔드

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis 연결 URL |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | RabbitMQ 연결 URL |
| `KIS_MAX_SUBSCRIPTIONS` | `40` | 최대 구독 종목 수 |

### 프론트엔드

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws/stock/` | WebSocket 서버 URL |

---

---

## 일반적인 사용 패턴

### 패턴 1: 특정 종목 상세 페이지

사용자가 특정 종목 상세 페이지에 들어갔을 때만 해당 종목 구독:

```javascript
// 페이지 진입 시
function onPageEnter(stockCode) {
  ws.send(JSON.stringify({
    action: 'subscribe',
    codes: [stockCode]
  }));
}

// 페이지 이탈 시
function onPageLeave(stockCode) {
  ws.send(JSON.stringify({
    action: 'unsubscribe',
    codes: [stockCode]
  }));
}

// React에서 useEffect 사용
useEffect(() => {
  if (isConnected) {
    subscribe([stockCode]);
    return () => unsubscribe([stockCode]); // cleanup
  }
}, [isConnected, stockCode]);
```

### 패턴 2: 관심 종목 리스트

여러 종목을 한 번에 구독:

```javascript
// 관심 종목 5개 동시 구독
const watchlist = ['005930', '000660', '035720', '035420', '051910'];

ws.send(JSON.stringify({
  action: 'subscribe',
  codes: watchlist
}));

// 화면에 표시
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'stock_price') {
    // 해당 종목 행의 가격 업데이트
    const row = document.querySelector(`[data-code="${data.stock_code}"]`);
    if (row) {
      row.querySelector('.price').textContent = data.price.toLocaleString();
      row.querySelector('.time').textContent = formatTime(data.time);
    }
  }
};
```

### 패턴 3: 구독 전환 (페이지 이동)

A 종목 페이지에서 B 종목 페이지로 이동 시:

```javascript
let currentSubscription = null;

function switchStock(newStockCode) {
  // 기존 구독 해제
  if (currentSubscription) {
    ws.send(JSON.stringify({
      action: 'unsubscribe',
      codes: [currentSubscription]
    }));
  }

  // 새 종목 구독
  ws.send(JSON.stringify({
    action: 'subscribe',
    codes: [newStockCode]
  }));

  currentSubscription = newStockCode;
}
```

### 패턴 4: 배치 구독 (40개 제한 관리)

```javascript
const MAX_SUBSCRIPTIONS = 40;

function smartSubscribe(newCodes, currentCodes) {
  const totalAfterAdd = new Set([...currentCodes, ...newCodes]).size;

  if (totalAfterAdd > MAX_SUBSCRIPTIONS) {
    // 오래된 종목부터 해제
    const toRemove = [...currentCodes].slice(0, totalAfterAdd - MAX_SUBSCRIPTIONS);
    ws.send(JSON.stringify({ action: 'unsubscribe', codes: toRemove }));
  }

  ws.send(JSON.stringify({ action: 'subscribe', codes: newCodes }));
}
```

---

## 바닐라 JavaScript 완전 예제

```html
<!DOCTYPE html>
<html>
<head>
  <title>실시간 주가</title>
  <style>
    .stock-card {
      border: 1px solid #ddd;
      padding: 16px;
      margin: 8px;
      border-radius: 8px;
    }
    .price { font-size: 24px; font-weight: bold; }
    .price.up { color: #ef4444; }
    .price.down { color: #3b82f6; }
    .status { padding: 4px 8px; border-radius: 4px; font-size: 12px; }
    .status.connected { background: #22c55e; color: white; }
    .status.disconnected { background: #ef4444; color: white; }
  </style>
</head>
<body>
  <h1>실시간 주가 모니터</h1>

  <div id="status" class="status disconnected">연결 중...</div>

  <div>
    <input type="text" id="stockCode" placeholder="종목코드 (예: 005930)" maxlength="6">
    <button onclick="addStock()">추가</button>
  </div>

  <div id="stocks"></div>

  <script>
    // 설정
    const WS_URL = 'ws://localhost:8000/ws/stock/';

    // 상태
    let ws = null;
    let stocks = new Map(); // code -> { price, prevPrice, time }

    // WebSocket 연결
    function connect() {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        updateStatus(true);
        // 기존 구독 복원
        if (stocks.size > 0) {
          ws.send(JSON.stringify({
            action: 'subscribe',
            codes: [...stocks.keys()]
          }));
        }
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
      };

      ws.onclose = () => {
        updateStatus(false);
        // 3초 후 재연결
        setTimeout(connect, 3000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket 에러:', error);
      };
    }

    // 메시지 처리
    function handleMessage(data) {
      switch (data.type) {
        case 'connection_established':
          console.log('서버 연결됨:', data.message);
          break;

        case 'subscription_result':
          if (data.success) {
            data.subscribed.forEach(code => {
              if (!stocks.has(code)) {
                stocks.set(code, { price: null, prevPrice: null, time: null });
                renderStock(code);
              }
            });
          }
          if (data.failed.length > 0) {
            alert(`구독 실패: ${data.failed.join(', ')}\n${data.error}`);
          }
          break;

        case 'stock_price':
          updateStockPrice(data);
          break;

        case 'unsubscription_result':
          data.unsubscribed.forEach(code => {
            stocks.delete(code);
            document.getElementById(`stock-${code}`)?.remove();
          });
          break;
      }
    }

    // 주가 업데이트
    function updateStockPrice(data) {
      const stock = stocks.get(data.stock_code);
      if (!stock) return;

      stock.prevPrice = stock.price;
      stock.price = data.price;
      stock.time = data.time;

      const el = document.getElementById(`stock-${data.stock_code}`);
      if (el) {
        const priceEl = el.querySelector('.price');
        priceEl.textContent = data.price.toLocaleString() + '원';

        // 등락 표시
        priceEl.classList.remove('up', 'down');
        if (stock.prevPrice !== null) {
          if (data.price > stock.prevPrice) priceEl.classList.add('up');
          else if (data.price < stock.prevPrice) priceEl.classList.add('down');
        }

        // 시간 표시
        el.querySelector('.time').textContent = formatTime(data.time);
      }
    }

    // 종목 카드 렌더링
    function renderStock(code) {
      const container = document.getElementById('stocks');
      const card = document.createElement('div');
      card.id = `stock-${code}`;
      card.className = 'stock-card';
      card.innerHTML = `
        <div>
          <strong>${code}</strong>
          <button onclick="removeStock('${code}')" style="float:right">X</button>
        </div>
        <div class="price">-</div>
        <div class="time">대기 중</div>
      `;
      container.appendChild(card);
    }

    // 종목 추가
    function addStock() {
      const input = document.getElementById('stockCode');
      const code = input.value.trim();

      if (!/^\d{6}$/.test(code)) {
        alert('종목코드는 6자리 숫자입니다.');
        return;
      }

      if (stocks.has(code)) {
        alert('이미 추가된 종목입니다.');
        return;
      }

      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'subscribe', codes: [code] }));
      }

      input.value = '';
    }

    // 종목 제거
    function removeStock(code) {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'unsubscribe', codes: [code] }));
      }
    }

    // 상태 업데이트
    function updateStatus(connected) {
      const el = document.getElementById('status');
      el.textContent = connected ? '🟢 연결됨' : '🔴 연결 끊김';
      el.className = 'status ' + (connected ? 'connected' : 'disconnected');
    }

    // 시간 포맷
    function formatTime(time) {
      if (!time) return '-';
      return `${time.slice(0,2)}:${time.slice(2,4)}:${time.slice(4,6)}`;
    }

    // 페이지 로드 시 연결
    connect();
  </script>
</body>
</html>
```

---

## 디버깅 가이드

### 브라우저 개발자 도구에서 테스트

```javascript
// 1. 콘솔에서 WebSocket 연결
const ws = new WebSocket('ws://localhost:8000/ws/stock/');

// 2. 모든 메시지 로깅
ws.onmessage = (e) => console.log(JSON.parse(e.data));

// 3. 구독 테스트
ws.send(JSON.stringify({ action: 'subscribe', codes: ['005930'] }));

// 4. 현재 구독 확인
ws.send(JSON.stringify({ action: 'list_subscriptions' }));

// 5. 연결 상태 확인
console.log('readyState:', ws.readyState);
// 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED
```

### 흔한 문제와 해결법

| 문제 | 원인 | 해결 |
|------|------|------|
| `WebSocket connection failed` | 서버 미실행 | `docker-compose up` 실행 |
| `Mixed Content` 에러 | HTTPS에서 ws:// 사용 | wss:// 사용 |
| 구독했는데 데이터 안 옴 | 장 마감 시간 | 테스트 모드 확인 |
| `40개 종목 구독 실패` | KIS API 제한 | 기존 구독 해제 후 구독 |
| 메시지가 안 옴 | JSON 파싱 안 함 | `JSON.parse(event.data)` 확인 |

### 네트워크 탭에서 확인

1. 개발자 도구 열기 (F12)
2. Network 탭 선택
3. WS 필터 선택
4. `ws/stock/` 연결 클릭
5. Messages 탭에서 송수신 메시지 확인

```
↑ {"action":"subscribe","codes":["005930"]}        [송신]
↓ {"type":"subscription_result","success":true...}  [수신]
↓ {"type":"stock_price","stock_code":"005930"...}   [수신]
```

---

## FAQ

### Q: 연결이 자주 끊겨요

WebSocket은 네트워크 상태에 따라 끊길 수 있습니다. 자동 재연결 로직을 구현하세요:

```javascript
ws.onclose = () => {
  setTimeout(() => connect(), 3000); // 3초 후 재연결
};
```

### Q: 구독한 종목의 데이터가 안 와요

1. **장 시간 확인**: 주식 시장은 평일 09:00~15:30만 운영
2. **테스트 모드 확인**: 테스트 모드에서는 mock 데이터가 옴
3. **구독 결과 확인**: `subscription_result`의 `subscribed` 배열 확인

```javascript
// 구독 결과 로깅
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'subscription_result') {
    console.log('구독 성공:', data.subscribed);
    console.log('구독 실패:', data.failed);
  }
};
```

### Q: 40개 넘게 구독하고 싶어요

KIS API 제한으로 40개가 최대입니다. 해결 방법:

1. **우선순위 관리**: 현재 화면에 보이는 종목만 구독
2. **페이지 이동 시 해제**: 이전 페이지 종목 구독 해제
3. **스마트 구독**: LRU 방식으로 오래된 구독 자동 해제

### Q: 실시간 데이터가 지연되는 것 같아요

WebSocket 자체는 실시간이지만, KIS API에서 데이터를 받아오는 데 약간의 지연이 있을 수 있습니다. 일반적으로 1초 이내입니다.

### Q: 모바일에서도 동작하나요?

네, 모든 최신 브라우저에서 WebSocket을 지원합니다. 다만 모바일에서는 백그라운드로 가면 연결이 끊길 수 있으니 재연결 로직이 중요합니다.

### Q: 여러 탭에서 열면 어떻게 되나요?

각 탭마다 별도의 WebSocket 연결이 생성됩니다. 서버 측에서는 각각 독립적인 클라이언트로 처리합니다.

리소스를 절약하려면 BroadcastChannel API나 SharedWorker를 사용해 단일 연결을 공유할 수 있습니다.

---

## 버전 히스토리

| 버전 | 날짜 | 변경 사항 |
|------|------|----------|
| 1.0.0 | 2025-01-24 | 초기 버전 - 동적 구독/해제 지원 |
