import asyncio
import json
import os
import websockets
import redis.asyncio as redis
import aiohttp
from fetch_symbols import get_all_listed_symbols, get_stock_codes_from_db

APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_URL = "https://openapivts.koreainvestment.com:29443"
WS_URL = "ws://ops.koreainvestment.com:31000"
TEST_URL = os.getenv("KIS_TEST_WS_URL", "ws://host.docker.internal:8080")

# 구독 설정 (모의투자 환경에서는 동시 구독 수 제한 있음)
# KIS_SYMBOL_LIMIT (docker-compose) 또는 KIS_MAX_SYMBOLS 환경변수 지원
MAX_SUBSCRIBE_SYMBOLS = int(
    os.getenv("KIS_SYMBOL_LIMIT", os.getenv("KIS_MAX_SYMBOLS", "5"))
)  # 기본 5개
SUBSCRIPTION_DELAY = float(os.getenv("KIS_SUBSCRIPTION_DELAY", "0.5"))  # 기본 500ms
BATCH_DELAY = float(os.getenv("KIS_BATCH_DELAY", "1.0"))  # 배치 간 딜레이 1초
BATCH_SIZE = int(os.getenv("KIS_BATCH_SIZE", "5"))  # 배치 크기

# 구독할 종목 코드 목록은 run_publisher() 함수 내에서 동적으로 로드
SUBSCRIBE_SYMBOLS = []


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
    # DB에서 모든 기업의 stock_code 가져오기 (우선순위 1)
    global SUBSCRIBE_SYMBOLS

    # DB 연결 재시도 로직 (최대 3회)
    max_db_retries = 3
    db_retry_delay = 5  # 5초
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
                    f"[INIT] Subscribing to {len(SUBSCRIBE_SYMBOLS)} symbols "
                    f"(limited by MAX_SUBSCRIBE_SYMBOLS={MAX_SUBSCRIBE_SYMBOLS})"
                )
                print(f"[INIT] First symbols to subscribe: {SUBSCRIBE_SYMBOLS[:5]}")
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

    # DB 조회 실패 시 fallback으로 CSV 또는 환경변수 사용
    if not all_stock_codes or len(all_stock_codes) == 0:
        print("[WARNING] Using fallback: loading from CSV/environment variables")
        try:
            # 동기 함수이므로 이벤트 루프에서 실행하려면 별도 처리 필요
            # 하지만 이미 async 컨텍스트이므로 asyncio.to_thread 사용
            loop = asyncio.get_event_loop()
            all_stock_codes = await loop.run_in_executor(None, get_all_listed_symbols)

            if all_stock_codes and len(all_stock_codes) > 0:
                SUBSCRIBE_SYMBOLS = all_stock_codes[:MAX_SUBSCRIBE_SYMBOLS]
                print(
                    f"[INIT] Loaded {len(all_stock_codes)} symbols from fallback source"
                )
                print(
                    f"[INIT] Subscribing to {len(SUBSCRIBE_SYMBOLS)} symbols "
                    f"(limited by MAX_SUBSCRIBE_SYMBOLS={MAX_SUBSCRIBE_SYMBOLS})"
                )
                print(f"[INIT] First symbols to subscribe: {SUBSCRIBE_SYMBOLS[:5]}")
            else:
                raise Exception("Fallback source also returned empty list")
        except Exception as e:
            print(f"[ERROR] Fallback also failed: {e}")
            raise Exception(
                "Failed to load stock codes from both DB and fallback sources"
            )

    if not SUBSCRIBE_SYMBOLS or len(SUBSCRIBE_SYMBOLS) == 0:
        raise Exception(
            "No stock codes to subscribe. Please check database connection or fallback configuration."
        )

    # Redis 연결
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_password = os.getenv("REDIS_PASSWORD")
    
    if redis_password:
        redis_url = f"redis://:{redis_password}@{redis_host}:6379/0"
    else:
        redis_url = f"redis://{redis_host}:6379/0"
        
    redis_client = redis.from_url(redis_url)
    print(f"[INIT] Redis client connected: {redis_url}")

    # Redis 연결 테스트
    try:
        await redis_client.ping()
        print("[INIT] Redis ping successful")
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
    max_reconnect_attempts = int(
        os.getenv("KIS_MAX_RECONNECT", "10")
    )  # 최대 재연결 시도 횟수

    while reconnect_count < max_reconnect_attempts:
        try:
            print(f"Connecting to WebSocket: {uri} (attempt {reconnect_count + 1})")
            async with websockets.connect(uri) as ws:
                print(f"WebSocket connected: {uri}")

                # 테스트 환경에서는 approval_key 없이도 동작
                # 실제 KIS API를 사용할 때만 approval_key가 필요
                is_test_mode = uri == TEST_URL
                approval_key = os.getenv("KIS_APPROVAL_KEY")

                if not approval_key and not is_test_mode:
                    approval_key = await get_approval_key()
                    if not approval_key:
                        raise Exception("Failed to get approval key")

                # 테스트 모드이거나 approval_key가 있으면 구독 진행
                if is_test_mode or approval_key:
                    # 여러 종목 구독 (배치 단위로 처리)
                    symbols = [s.strip() for s in SUBSCRIBE_SYMBOLS if s.strip()]
                    print(
                        f"[WS] Subscribing to {len(symbols)} symbols "
                        f"(batch_size={BATCH_SIZE}, delay={SUBSCRIPTION_DELAY}s)"
                    )

                    subscription_count = 0

                    for symbol in symbols:
                        try:
                            # 테스트 모드에서는 간소화된 메시지 사용
                            if is_test_mode:
                                subscribe_msg = {
                                    "header": {"tr_type": "1"},
                                    "body": {
                                        "input": {"tr_id": "H0STCNT0", "tr_key": symbol}
                                    },
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
                                response = await asyncio.wait_for(
                                    ws.recv(), timeout=3.0
                                )
                                print(
                                    f"[WS DEBUG] Response for {symbol}: "
                                    f"{response[:200] if len(response) > 200 else response}"
                                )

                                # 에러 응답 체크
                                try:
                                    resp_json = json.loads(response)
                                    rt_cd = resp_json.get("body", {}).get("rt_cd", "0")
                                    msg1 = resp_json.get("body", {}).get("msg1", "")

                                    if rt_cd != "0":  # 0이 아니면 에러
                                        if "ALREADY IN USE" in msg1:
                                            print(
                                                "[WS ERROR] APP_KEY already in use. Waiting 30s before retry..."
                                            )
                                            raise Exception("APP_KEY_IN_USE")
                                        else:
                                            print(
                                                f"[WS WARNING] Server returned error: {msg1}"
                                            )
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
                            if (
                                "APP_KEY_IN_USE" in str(e)
                                or "no close frame" in str(e)
                                or "Connection closed" in str(e)
                            ):
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
                        # 테스트/실제 환경 공통: KIS API 형식 메시지 파싱 후 Redis Stream에 추가
                        if message and len(message) > 0 and message[0] in ["0", "1"]:
                            parsed_data = KISParser.parse_trade_data(message)
                            if parsed_data:
                                # Redis Stream에 XADD (stock:realtime 단일 스트림)
                                stream_key = "stock:realtime"
                                entry_id = await redis_client.xadd(
                                    stream_key,
                                    {
                                        "stock_code": parsed_data["stock_code"],
                                        "symbol": parsed_data["symbol"],
                                        "time": parsed_data["time"],
                                        "price": str(parsed_data["price"]),
                                        "volume": str(parsed_data["volume"]),
                                    },
                                    maxlen=1000000,  # 스트림 최대 길이 제한
                                )
                                mode = "[TEST]" if uri == TEST_URL else "[PROD]"
                                print(
                                    f"{mode} XADD: {stream_key}, id={entry_id}, "
                                    f"stock={parsed_data['stock_code']}, price={parsed_data['price']}"
                                )
                    except Exception as e:
                        print(f"[ERROR] Error processing message: {e}")
                        continue

        except websockets.ConnectionClosed as e:
            reconnect_count += 1
            print(
                f"[RECONNECT] WebSocket connection closed: {e}. "
                f"Attempt {reconnect_count}/{max_reconnect_attempts}. "
                f"Reconnecting in {reconnect_delay}s..."
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

        except websockets.InvalidURI as e:
            print(f"[ERROR] Invalid WebSocket URI: {e}")
            raise
        except Exception as e:
            # APP_KEY 중복 사용 에러 시 즉시 종료 (재시도 무의미)
            if "APP_KEY_IN_USE" in str(e):
                print(
                    "[FATAL] APP_KEY already in use. Please wait a few minutes and restart the container."
                )
                print("[FATAL] Or use a different APP_KEY.")
                raise SystemExit(1)

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
