"""
KIS WebSocket Publisher.

KIS API에서 실시간 체결 데이터를 수신하여 RabbitMQ로 발행합니다.
RPC 명령을 통해 동적 구독/해제를 지원합니다.

KIS 가이드라인 준수:
- 연결 시도 → 접속 확인 → 구독 정보 등록 → 정보 수신 → PINGPONG 응답 처리 → 구독 해제 → 접속 해제
- 연결/종료 간격 최소 1초 이상
"""

import asyncio
import json
import os
import signal
import time
import websockets
import aio_pika
from aio_pika.exceptions import DeliveryError
import aiohttp
from fetch_symbols import get_all_listed_symbols, get_stock_codes_from_db
from subscription_handler import SubscriptionHandler

APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_URL = "https://openapivts.koreainvestment.com:29443"
WS_URL = "ws://ops.koreainvestment.com:31000"
TEST_URL = os.getenv("KIS_TEST_WS_URL", "ws://host.docker.internal:8080")

# 구독 설정
MAX_SUBSCRIBE_SYMBOLS = int(
    os.getenv("KIS_SYMBOL_LIMIT", os.getenv("KIS_MAX_SYMBOLS", "5"))
)
SUBSCRIPTION_DELAY = float(os.getenv("KIS_SUBSCRIPTION_DELAY", "0.5"))
BATCH_DELAY = float(os.getenv("KIS_BATCH_DELAY", "1.0"))
BATCH_SIZE = int(os.getenv("KIS_BATCH_SIZE", "5"))

# PINGPONG 설정
PING_INTERVAL = int(os.getenv("KIS_PING_INTERVAL", "30"))  # 30초마다 PING
PING_TIMEOUT = int(os.getenv("KIS_PING_TIMEOUT", "10"))  # PONG 응답 타임아웃

# RPC 설정
RPC_QUEUE_NAME = "subscription.commands"

# 구독할 종목 코드 목록은 run_publisher() 함수 내에서 동적으로 로드
SUBSCRIBE_SYMBOLS = []


class PublishMetrics:
    """Publisher Confirm 메트릭 추적"""

    def __init__(self):
        self.published = 0
        self.confirmed = 0
        self.failed = 0
        self.last_report_time = time.time()
        self.report_interval = 60  # 60초마다 메트릭 출력

    def record_success(self):
        self.published += 1
        self.confirmed += 1
        self._maybe_report()

    def record_failure(self, stock_code: str, error: str):
        self.published += 1
        self.failed += 1
        print(f"[CONFIRM FAILED] stock={stock_code}, error={error}")
        self._maybe_report()

    def _maybe_report(self):
        now = time.time()
        if now - self.last_report_time >= self.report_interval:
            self.report()
            self.last_report_time = now

    def report(self):
        success_rate = (self.confirmed / self.published * 100) if self.published > 0 else 0
        print(
            f"[METRICS] published={self.published}, "
            f"confirmed={self.confirmed}, failed={self.failed}, "
            f"success_rate={success_rate:.2f}%"
        )


class KISParser:
    @staticmethod
    def parse_trade_data(raw_message: str) -> dict:
        """
        KIS 실시간 체결 데이터를 파싱합니다.
        형식: 데이터구분|TR_ID|종목코드|데이터부
        """
        try:
            parts = raw_message.split("|")
            if len(parts) < 4:
                return None

            body_parts = parts[3].split("^")

            return {
                "symbol": parts[2],
                "stock_code": (
                    body_parts[0] if len(body_parts) > 0 else parts[2]
                ),
                "time": body_parts[1],
                "price": int(body_parts[2]),
                "volume": int(body_parts[12]),
            }
        except (IndexError, ValueError) as e:
            print(f"Parsing error: {e}")
            return None

    @staticmethod
    def is_pingpong_message(message: str) -> bool:
        """PINGPONG 메시지인지 확인"""
        if not message:
            return False
        # KIS API PINGPONG 메시지 형식 확인
        return "PINGPONG" in message.upper() or message.strip().upper() == "PING"


class HeartbeatManager:
    """
    KIS WebSocket PINGPONG 관리.

    KIS 가이드라인: 데이터가 없을 시 PINGPONG 응답 처리 필수
    """

    def __init__(self, websocket, ping_interval: int = 30, ping_timeout: int = 10):
        self._websocket = websocket
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._last_pong_time = asyncio.get_event_loop().time()
        self._heartbeat_task = None
        self._is_running = False

    async def start(self):
        """하트비트 태스크 시작"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        self._is_running = True
        self._last_pong_time = asyncio.get_event_loop().time()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        print(f"[HEARTBEAT] Started (interval={self._ping_interval}s, timeout={self._ping_timeout}s)")

    async def stop(self):
        """하트비트 태스크 중지"""
        self._is_running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        print("[HEARTBEAT] Stopped")

    def record_activity(self):
        """데이터 수신 시 호출 - 연결 활성 상태 기록"""
        self._last_pong_time = asyncio.get_event_loop().time()

    async def handle_pingpong(self, message: str) -> bool:
        """
        PINGPONG 메시지 처리.

        KIS 가이드라인: 동일한 페이로드를 응답해야 함.

        Returns:
            True: PINGPONG 메시지 처리됨
            False: PINGPONG 메시지 아님
        """
        if not KISParser.is_pingpong_message(message):
            return False

        try:
            # 원본 메시지를 그대로 에코 (KIS 가이드라인)
            await self._websocket.send(message)
            self.record_activity()
            print(f"[HEARTBEAT] PINGPONG received, echoed back: {message[:50]}")
            return True
        except Exception as e:
            print(f"[HEARTBEAT] Error sending PONG: {e}")
            return True

    async def _heartbeat_loop(self):
        """비활성 타임아웃 체크 (서버 PINGPONG에 응답하는 방식)"""
        while self._is_running:
            try:
                await asyncio.sleep(self._ping_interval)

                if not self._is_running:
                    break

                # 마지막 활동 시간 체크
                current_time = asyncio.get_event_loop().time()
                elapsed = current_time - self._last_pong_time

                if elapsed > self._ping_interval + self._ping_timeout:
                    # 타임아웃 - 연결이 끊어진 것으로 간주
                    print(f"[HEARTBEAT] Connection timeout ({elapsed:.1f}s since last activity)")
                    raise websockets.ConnectionClosed(None, None)

                print(f"[HEARTBEAT] Connection alive (last activity: {elapsed:.1f}s ago)")

            except asyncio.CancelledError:
                break
            except websockets.ConnectionClosed:
                break
            except Exception as e:
                print(f"[HEARTBEAT] Error in heartbeat loop: {e}")
                await asyncio.sleep(1)


async def get_approval_key():
    url = f"{KIS_URL}/oauth2/Approval"
    payload = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "secretkey": APP_SECRET,
    }
    headers = {"Content-Type": "application/json"}

    print(f"[AUTH] Requesting approval key from {url}")
    print(
        f"[AUTH] Payload: appkey={APP_KEY[:10]}..., secretkey={'***' if APP_SECRET else 'None'}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, headers=headers, data=json.dumps(payload)
        ) as response:
            if response.status == 200:
                data = await response.json()
                approval_key = data.get("approval_key")
                print(
                    f"[AUTH] Successfully got approval_key: {approval_key[:20]}..."
                    if approval_key
                    else "[AUTH] No approval_key in response"
                )
                return approval_key
            else:
                error_text = await response.text()
                print(f"[AUTH ERROR] Failed to get approval key: {error_text}")
                raise Exception(f"Failed to get approval key: {error_text}")


async def setup_rpc_consumer(rabbitmq_channel, subscription_handler: SubscriptionHandler):
    """RPC 명령 큐 설정 및 소비자 시작"""
    # RPC 큐 선언
    rpc_queue = await rabbitmq_channel.declare_queue(
        RPC_QUEUE_NAME,
        durable=True
    )

    print(f"[RPC] Listening for commands on queue: {RPC_QUEUE_NAME}")

    async def on_rpc_message(message: aio_pika.IncomingMessage):
        """RPC 메시지 처리"""
        async with message.process():
            try:
                data = json.loads(message.body)
                command = data.get("command")
                stock_codes = data.get("stock_codes", [])

                print(f"[RPC] Received command: {command}, codes: {stock_codes}")

                # 명령 처리
                if command == "subscribe":
                    result = await subscription_handler.subscribe(stock_codes)
                elif command == "unsubscribe":
                    result = await subscription_handler.unsubscribe(stock_codes)
                else:
                    result = {"success": False, "error": f"Unknown command: {command}"}

                # 응답 전송
                if message.reply_to:
                    response = aio_pika.Message(
                        body=json.dumps(result).encode(),
                        correlation_id=message.correlation_id,
                        content_type="application/json"
                    )
                    await rabbitmq_channel.default_exchange.publish(
                        response,
                        routing_key=message.reply_to
                    )
                    print(f"[RPC] Response sent: {result}")

            except Exception as e:
                print(f"[RPC] Error processing message: {e}")
                if message.reply_to:
                    response = aio_pika.Message(
                        body=json.dumps({"success": False, "error": str(e)}).encode(),
                        correlation_id=message.correlation_id,
                        content_type="application/json"
                    )
                    await rabbitmq_channel.default_exchange.publish(
                        response,
                        routing_key=message.reply_to
                    )

    # RPC 소비자 시작
    await rpc_queue.consume(on_rpc_message)
    return rpc_queue


async def run_publisher():
    global SUBSCRIBE_SYMBOLS

    # 종료 이벤트 (per-loop 생성)
    shutdown_event = asyncio.Event()

    # DB에서 초기 종목 코드 가져오기
    max_db_retries = 3
    db_retry_delay = 5
    all_stock_codes = None

    for attempt in range(1, max_db_retries + 1):
        try:
            print(
                f"[INIT] Attempting to load stock codes from DB (attempt {attempt}/{max_db_retries})..."
            )
            all_stock_codes = await get_stock_codes_from_db()

            if all_stock_codes and len(all_stock_codes) > 0:
                SUBSCRIBE_SYMBOLS = all_stock_codes[:MAX_SUBSCRIBE_SYMBOLS]
                print(
                    f"[INIT] ✓ Successfully loaded {len(all_stock_codes)} stock codes from DB"
                )
                print(
                    f"[INIT] Initial subscription: {len(SUBSCRIBE_SYMBOLS)} symbols "
                    f"(limited by MAX_SUBSCRIBE_SYMBOLS={MAX_SUBSCRIBE_SYMBOLS})"
                )
                print(f"[INIT] First symbols: {SUBSCRIBE_SYMBOLS[:5]}")
                break
            else:
                print(
                    f"[WARNING] DB query returned empty list "
                    f"(attempt {attempt}/{max_db_retries})"
                )
                if attempt < max_db_retries:
                    print(f"[INIT] Retrying in {db_retry_delay}s...")
                    await asyncio.sleep(db_retry_delay)

        except Exception as e:
            print(
                f"[ERROR] Failed to load stock codes from DB (attempt {attempt}/{max_db_retries}): {e}"
            )
            import traceback
            traceback.print_exc()

            if attempt < max_db_retries:
                print(f"[INIT] Retrying in {db_retry_delay}s...")
                await asyncio.sleep(db_retry_delay)
            else:
                print(
                    "[WARNING] All DB connection attempts failed. Falling back to CSV/environment..."
                )

    # DB 조회 실패 시 fallback
    if not all_stock_codes or len(all_stock_codes) == 0:
        print("[WARNING] Using fallback: loading from CSV/environment variables")
        try:
            loop = asyncio.get_event_loop()
            all_stock_codes = await loop.run_in_executor(None, get_all_listed_symbols)

            if all_stock_codes and len(all_stock_codes) > 0:
                SUBSCRIBE_SYMBOLS = all_stock_codes[:MAX_SUBSCRIBE_SYMBOLS]
                print(
                    f"[INIT] Loaded {len(all_stock_codes)} symbols from fallback source"
                )
                print(
                    f"[INIT] Initial subscription: {len(SUBSCRIBE_SYMBOLS)} symbols"
                )
            else:
                raise Exception("Fallback source also returned empty list")
        except Exception as e:
            print(f"[ERROR] Fallback also failed: {e}")
            # 초기 종목 없어도 RPC를 통해 동적으로 추가 가능
            print("[WARNING] No initial symbols. Waiting for RPC commands...")
            SUBSCRIBE_SYMBOLS = []

    # RabbitMQ 연결
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    print(f"[INIT] Connecting to RabbitMQ: {rabbitmq_url}")

    # Publisher Confirm 메트릭 초기화
    publish_metrics = PublishMetrics()

    try:
        rabbitmq_connection = await aio_pika.connect_robust(rabbitmq_url)
        rabbitmq_channel = await rabbitmq_connection.channel()

        # Publisher Confirms 활성화
        await rabbitmq_channel.set_publisher_confirms(True)
        print("[INIT] Publisher Confirms enabled")

        # Exchange 선언 (Fanout 타입)
        rabbitmq_exchange = await rabbitmq_channel.declare_exchange(
            "stock.realtime",
            aio_pika.ExchangeType.FANOUT,
            durable=True
        )
        print("[INIT] RabbitMQ connected and exchange 'stock.realtime' declared")
    except Exception as e:
        print(f"[ERROR] RabbitMQ connection failed: {e}")
        raise

    # KIS WebSocket 연결
    use_test_mode = os.getenv("KIS_USE_TEST_MODE", "false").lower() == "true"
    uri = TEST_URL if use_test_mode else WS_URL
    if use_test_mode:
        print(f"[TEST MODE] Using test WebSocket server: {uri}")
    print(f"Connecting to WebSocket: {uri}")

    reconnect_delay = 5
    max_reconnect_delay = 300
    reconnect_count = 0
    max_reconnect_attempts = int(os.getenv("KIS_MAX_RECONNECT", "10"))

    # SubscriptionHandler 초기화
    subscription_handler = SubscriptionHandler(is_test_mode=use_test_mode)

    # RPC 소비자 설정
    await setup_rpc_consumer(rabbitmq_channel, subscription_handler)

    # 종료 시그널 핸들러 설정
    def signal_handler():
        print("[SHUTDOWN] Received shutdown signal")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows에서는 지원하지 않음
            pass

    heartbeat_manager = None

    while reconnect_count < max_reconnect_attempts and not shutdown_event.is_set():
        try:
            print(f"Connecting to WebSocket: {uri} (attempt {reconnect_count + 1})")
            async with websockets.connect(uri) as ws:
                print(f"WebSocket connected: {uri}")

                is_test_mode = uri == TEST_URL
                approval_key = os.getenv("KIS_APPROVAL_KEY")

                if not approval_key and not is_test_mode:
                    approval_key = await get_approval_key()
                    if not approval_key:
                        raise Exception("Failed to get approval key")

                # SubscriptionHandler에 WebSocket 설정
                subscription_handler.set_websocket(ws, approval_key)
                subscription_handler.set_test_mode(is_test_mode)

                # HeartbeatManager 초기화
                heartbeat_manager = HeartbeatManager(
                    ws,
                    ping_interval=PING_INTERVAL,
                    ping_timeout=PING_TIMEOUT
                )

                print("[WS] Connected, proceeding to subscription...")

                # [KIS 가이드라인] 1단계: 구독 정보 등록
                if subscription_handler.subscription_count > 0:
                    # 재연결: 기존 구독 복원
                    print("[WS] Restoring previous subscriptions...")
                    await subscription_handler.restore_subscriptions()
                elif SUBSCRIBE_SYMBOLS:
                    # 초기 연결: DB에서 가져온 종목 구독
                    print(f"[WS] Initial subscription: {len(SUBSCRIBE_SYMBOLS)} symbols")
                    result = await subscription_handler.subscribe(SUBSCRIBE_SYMBOLS)
                    print(f"[WS] Initial subscription result: {len(result['subscribed'])} subscribed, "
                          f"{len(result['failed'])} failed")

                # 구독 완료 후 재연결 카운터 리셋
                reconnect_count = 0
                reconnect_delay = 5

                # [KIS 가이드라인] 2단계: PINGPONG 처리를 위한 하트비트 시작
                await heartbeat_manager.start()

                print(f"[WS] Listening for real-time data... "
                      f"(Active subscriptions: {subscription_handler.subscription_count})")

                # [KIS 가이드라인] 3단계: 정보 수신
                async for message in ws:
                    # 종료 이벤트 체크
                    if shutdown_event.is_set():
                        print("[WS] Shutdown event detected")
                        break

                    try:
                        # 연결 활성 상태 기록
                        heartbeat_manager.record_activity()

                        # [KIS 가이드라인] PINGPONG 응답 처리
                        if await heartbeat_manager.handle_pingpong(message):
                            continue

                        # KIS API 형식 메시지 파싱 후 RabbitMQ에 발행
                        if message and len(message) > 0 and message[0] in ["0", "1"]:
                            parsed_data = KISParser.parse_trade_data(message)
                            if parsed_data:
                                # RabbitMQ에 메시지 발행 (Publisher Confirm 사용)
                                rabbitmq_message = aio_pika.Message(
                                    body=json.dumps(parsed_data).encode(),
                                    content_type="application/json",
                                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                                )
                                try:
                                    # Publisher Confirm: 메시지가 RabbitMQ에 도달했는지 확인
                                    await rabbitmq_exchange.publish(
                                        rabbitmq_message,
                                        routing_key="",
                                        mandatory=True  # 라우팅 실패 시 예외 발생
                                    )
                                    publish_metrics.record_success()
                                    mode = "[TEST]" if uri == TEST_URL else "[PROD]"
                                    print(
                                        f"{mode} PUBLISH: stock.realtime exchange, "
                                        f"stock={parsed_data['stock_code']}, price={parsed_data['price']}"
                                    )
                                except DeliveryError as e:
                                    publish_metrics.record_failure(
                                        parsed_data['stock_code'],
                                        f"DeliveryError: {e}"
                                    )
                                except Exception as e:
                                    publish_metrics.record_failure(
                                        parsed_data['stock_code'],
                                        str(e)
                                    )
                    except Exception as e:
                        print(f"[ERROR] Error processing message: {e}")
                        continue

                # [KIS 가이드라인] 5단계: 정상 종료 시 구독 해제
                if shutdown_event.is_set():
                    print("[WS] Graceful shutdown: unsubscribing all...")
                    await heartbeat_manager.stop()
                    await subscription_handler.unsubscribe_all()
                    print("[WS] All subscriptions removed")
                    # 종료 전 최종 메트릭 출력
                    print("[SHUTDOWN] Final metrics:")
                    publish_metrics.report()
                    break

        except websockets.ConnectionClosed as e:
            if heartbeat_manager:
                await heartbeat_manager.stop()

            if shutdown_event.is_set():
                break

            reconnect_count += 1
            print(
                f"[RECONNECT] WebSocket connection closed: {e}. "
                f"Attempt {reconnect_count}/{max_reconnect_attempts}. "
                f"Reconnecting in {reconnect_delay}s..."
            )
            # [KIS 가이드라인] 연결/종료 간격 최소 1초 이상 (현재 5초)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

        except websockets.InvalidURI as e:
            print(f"[ERROR] Invalid WebSocket URI: {e}")
            raise
        except Exception as e:
            if heartbeat_manager:
                await heartbeat_manager.stop()

            # APP_KEY 중복 사용 에러 시 즉시 종료
            if "APP_KEY_IN_USE" in str(e):
                print(
                    "[FATAL] APP_KEY already in use. Waiting 60 seconds for server session to timeout..."
                )
                await asyncio.sleep(60)
                print("[FATAL] Exiting container to restart...")
                raise SystemExit(1)

            if shutdown_event.is_set():
                break

            reconnect_count += 1
            print(f"[ERROR] Error in WebSocket loop: {e}")
            import traceback
            traceback.print_exc()
            print(
                f"[RECONNECT] Attempt {reconnect_count}/{max_reconnect_attempts}. Reconnecting in {reconnect_delay}s..."
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    # 최대 재연결 횟수 초과 시 종료
    print(
        f"[FATAL] Maximum reconnection attempts ({max_reconnect_attempts}) exceeded. Exiting."
    )
    print("[SHUTDOWN] Final metrics:")
    publish_metrics.report()
    raise SystemExit(1)


if __name__ == "__main__":
    print("Starting KIS Publisher with dynamic subscription support...")
    try:
        asyncio.run(run_publisher())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        raise
