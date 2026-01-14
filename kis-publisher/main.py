import asyncio
import json
import os
import websockets
import redis.asyncio as redis
import aiohttp
from fetch_symbols import get_all_listed_symbols

APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_URL = "https://openapivts.koreainvestment.com:29443"
WS_URL = "ws://ops.koreainvestment.com:31000"
TEST_URL = os.getenv("KIS_TEST_WS_URL", "ws://host.docker.internal:8080")

# 구독 설정 (모의투자 환경에서는 동시 구독 수 제한 있음)
# KIS_SYMBOL_LIMIT (docker-compose) 또는 KIS_MAX_SYMBOLS 환경변수 지원
MAX_SUBSCRIBE_SYMBOLS = int(os.getenv("KIS_SYMBOL_LIMIT", os.getenv("KIS_MAX_SYMBOLS", "5")))  # 기본 5개
SUBSCRIPTION_DELAY = float(os.getenv("KIS_SUBSCRIPTION_DELAY", "0.5"))  # 기본 500ms
BATCH_DELAY = float(os.getenv("KIS_BATCH_DELAY", "1.0"))  # 배치 간 딜레이 1초
BATCH_SIZE = int(os.getenv("KIS_BATCH_SIZE", "5"))  # 배치 크기

# 구독할 종목 코드 목록 (동적으로 로드, 제한 적용)
ALL_SYMBOLS = get_all_listed_symbols()
SUBSCRIBE_SYMBOLS = ALL_SYMBOLS[:MAX_SUBSCRIBE_SYMBOLS]
print(f"[INIT] Total symbols available: {len(ALL_SYMBOLS)}, subscribing to: {len(SUBSCRIBE_SYMBOLS)}")
print(f"[INIT] First symbols to subscribe: {SUBSCRIBE_SYMBOLS[:5]}")


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

            # 실시간 체결 데이터부는 '^'로 구분됨
            body_parts = parts[3].split("^")

            # 필요한 핵심 필드만 추출 (인덱스는 KIS API 명세 기준)
            return {
                "symbol": parts[2],  # KIS 내부 식별자 (구독 순서: '001', '002', ...)
                "stock_code": (
                    body_parts[0] if len(body_parts) > 0 else parts[2]
                ),  # 실제 6자리 종목코드
                "time": body_parts[1],  # 체결시간 (HHMMSS)
                "price": int(body_parts[2]),  # 현재가
                "volume": int(body_parts[12]),  # 체결량
            }
        except (IndexError, ValueError) as e:
            print(f"Parsing error: {e}")
            return None


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


async def run_publisher():
    # Redis 연결
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_url = f"redis://{redis_host}:6379/0"
    redis_client = redis.from_url(redis_url)
    print(f"[INIT] Redis client connected: {redis_url}")

    # Redis 연결 테스트
    try:
        await redis_client.ping()
        print(f"[INIT] Redis ping successful")
    except Exception as e:
        print(f"[ERROR] Redis ping failed: {e}")
        raise

    # KIS WebSocket 연결
    # 테스트 모드: 환경변수 KIS_USE_TEST_MODE=true로 설정하면 Mock 서버 사용
    use_test_mode = os.getenv("KIS_USE_TEST_MODE", "false").lower() == "true"
    uri = TEST_URL if use_test_mode else WS_URL
    if use_test_mode:
        print(f"[TEST MODE] Using test WebSocket server: {uri}")
    print(f"Connecting to WebSocket: {uri}")

    reconnect_delay = 5
    max_reconnect_delay = 300  # 최대 5분
    reconnect_count = 0
    max_reconnect_attempts = int(os.getenv("KIS_MAX_RECONNECT", "10"))  # 최대 재연결 시도 횟수

    while reconnect_count < max_reconnect_attempts:
        try:
            print(f"Connecting to WebSocket: {uri} (attempt {reconnect_count + 1})")
            async with websockets.connect(uri) as ws:
                print(f"WebSocket connected: {uri}")

                # 테스트 환경에서는 approval_key 없이도 동작
                # 실제 KIS API를 사용할 때만 approval_key가 필요
                is_test_mode = (uri == TEST_URL)
                approval_key = os.getenv("KIS_APPROVAL_KEY")

                if not approval_key and not is_test_mode:
                    approval_key = await get_approval_key()
                    if not approval_key:
                        raise Exception("Failed to get approval key")

                # 테스트 모드이거나 approval_key가 있으면 구독 진행
                if is_test_mode or approval_key:
                    # 여러 종목 구독 (배치 단위로 처리)
                    symbols = [s.strip() for s in SUBSCRIBE_SYMBOLS if s.strip()]
                    print(f"[WS] Subscribing to {len(symbols)} symbols (batch_size={BATCH_SIZE}, delay={SUBSCRIPTION_DELAY}s)")

                    subscription_count = 0

                    for symbol in symbols:
                        try:
                            # 테스트 모드에서는 간소화된 메시지 사용
                            if is_test_mode:
                                subscribe_msg = {
                                    "header": {"tr_type": "1"},
                                    "body": {"input": {"tr_id": "H0STCNT0", "tr_key": symbol}}
                                }
                            else:
                                subscribe_msg = {
                                    "header": {
                                        "approval_key": approval_key,
                                        "appkey": APP_KEY,
                                        "secretkey": APP_SECRET,
                                        "custtype": "P",
                                        "tr_type": "1",
                                        "content-type": "utf-8",
                                    },
                                    "body": {
                                        "input": {"tr_id": "H0STCNT0", "tr_key": symbol}
                                    },
                                }
                            print(f"[WS DEBUG] Sending subscribe for {symbol}...")
                            await ws.send(json.dumps(subscribe_msg))

                            # 서버 응답 대기 (타임아웃 3초)
                            try:
                                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                                print(f"[WS DEBUG] Response for {symbol}: {response[:200] if len(response) > 200 else response}")

                                # 에러 응답 체크
                                try:
                                    resp_json = json.loads(response)
                                    rt_cd = resp_json.get("body", {}).get("rt_cd", "0")
                                    msg1 = resp_json.get("body", {}).get("msg1", "")

                                    if rt_cd != "0":  # 0이 아니면 에러
                                        if "ALREADY IN USE" in msg1:
                                            print(f"[WS ERROR] APP_KEY already in use. Waiting 30s before retry...")
                                            raise Exception("APP_KEY_IN_USE")
                                        else:
                                            print(f"[WS WARNING] Server returned error: {msg1}")
                                except json.JSONDecodeError:
                                    pass  # JSON이 아닌 응답은 실시간 데이터일 수 있음

                            except asyncio.TimeoutError:
                                print(f"[WS DEBUG] No response for {symbol} (timeout)")

                            subscription_count += 1

                            # 배치 단위로 딜레이 적용
                            if subscription_count % BATCH_SIZE == 0:
                                print(
                                    f"[WS] Subscribed {subscription_count}/{len(symbols)} symbols..."
                                )
                                # 배치 완료 후 더 긴 딜레이 (서버 처리 시간 확보)
                                await asyncio.sleep(BATCH_DELAY)
                            else:
                                # 일반 구독 메시지 사이 딜레이
                                await asyncio.sleep(SUBSCRIPTION_DELAY)

                        except websockets.ConnectionClosed as e:
                            print(
                                f"[WS ERROR] Connection closed while subscribing {symbol}: {e}"
                            )
                            raise
                        except Exception as e:
                            print(f"[WS ERROR] Failed to subscribe {symbol}: {e}")
                            # APP_KEY_IN_USE 또는 연결 끊김 에러는 상위로 전파
                            if "APP_KEY_IN_USE" in str(e) or "no close frame" in str(e) or "Connection closed" in str(e):
                                raise
                            continue

                    print(
                        f"[WS] All subscription messages sent ({subscription_count}/{len(symbols)} symbols)"
                    )
                    # 구독 완료 후 재연결 카운터 리셋
                    reconnect_count = 0
                    reconnect_delay = 5

                async for message in ws:
                    try:
                        # 테스트 환경: 메시지를 파싱해서 실제 형식으로 발행
                        if uri == TEST_URL:
                            # 테스트 메시지도 실제 KIS API 형식으로 파싱
                            if (
                                message
                                and len(message) > 0
                                and message[0] in ["0", "1"]
                            ):
                                parsed_data = KISParser.parse_trade_data(message)
                                if parsed_data:
                                    channel = (
                                        f"stock:realtime:{parsed_data['stock_code']}"
                                    )
                                    payload = json.dumps(parsed_data)
                                    num_subscribers = await redis_client.publish(
                                        channel, payload
                                    )
                                    if num_subscribers > 0:
                                        print(
                                            f"[TEST] Published: {channel}, price={parsed_data.get('price')}, subscribers={num_subscribers}"
                                        )
                        elif message and len(message) > 0 and message[0] in ["0", "1"]:
                            # 실제 KIS API 형식 메시지 처리
                            parsed_data = KISParser.parse_trade_data(message)
                            if parsed_data:
                                channel = f"stock:realtime:{parsed_data['stock_code']}"
                                payload = json.dumps(parsed_data)
                                num_subscribers = await redis_client.publish(
                                    channel, payload
                                )
                                if num_subscribers > 0:
                                    print(
                                        f"[PROD] Published: {channel}, price={parsed_data.get('price')}, subscribers={num_subscribers}"
                                    )
                    except Exception as e:
                        print(f"[ERROR] Error processing message: {e}")
                        continue

        except websockets.ConnectionClosed as e:
            reconnect_count += 1
            print(
                f"[RECONNECT] WebSocket connection closed: {e}. Attempt {reconnect_count}/{max_reconnect_attempts}. Reconnecting in {reconnect_delay}s..."
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

        except websockets.InvalidURI as e:
            print(f"[ERROR] Invalid WebSocket URI: {e}")
            raise
        except Exception as e:
            # APP_KEY 중복 사용 에러 시 즉시 종료 (재시도 무의미)
            if "APP_KEY_IN_USE" in str(e):
                print(f"[FATAL] APP_KEY already in use. Please wait a few minutes and restart the container.")
                print(f"[FATAL] Or use a different APP_KEY.")
                raise SystemExit(1)

            reconnect_count += 1
            print(f"[ERROR] Error in WebSocket loop: {e}")
            import traceback
            traceback.print_exc()
            print(f"[RECONNECT] Attempt {reconnect_count}/{max_reconnect_attempts}. Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    # 최대 재연결 횟수 초과 시 종료
    print(f"[FATAL] Maximum reconnection attempts ({max_reconnect_attempts}) exceeded. Exiting.")
    raise SystemExit(1)


if __name__ == "__main__":
    print("Starting KIS Publisher...")
    try:
        asyncio.run(run_publisher())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()
        raise
