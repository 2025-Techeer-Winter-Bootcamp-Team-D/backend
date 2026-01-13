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
TEST_URL = "ws://host.docker.internal:8080"

# 구독할 종목 코드 목록 (동적으로 로드)
SUBSCRIBE_SYMBOLS = get_all_listed_symbols()


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

    async for ws in websockets.connect(uri):
        try:
            print(f"WebSocket connected: {uri}")

            # 테스트 환경에서는 approval_key 없이도 동작
            # 실제 KIS API를 사용할 때만 approval_key가 필요
            approval_key = os.getenv("KIS_APPROVAL_KEY")
            if not approval_key and uri != TEST_URL:
                approval_key = await get_approval_key()
                if not approval_key:
                    raise Exception("Failed to get approval key")

            if approval_key:
                # 여러 종목 구독 (각 종목마다 개별 구독 메시지 전송)
                symbols = [s.strip() for s in SUBSCRIBE_SYMBOLS if s.strip()]
                print(f"[WS] Subscribing to {len(symbols)} symbols: {symbols}")

                for symbol in symbols:
                    subscribe_msg = {
                        "header": {
                            "approval_key": approval_key,
                            "appkey": APP_KEY,
                            "secretkey": APP_SECRET,
                            "custtype": "P",
                            "tr_type": "1",
                            "content-type": "utf-8",
                        },
                        "body": {"input": {"tr_id": "H0STCNT0", "tr_key": symbol}},
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    print(f"[WS] Subscription sent for symbol: {symbol}")

                print(f"[WS] All subscription messages sent ({len(symbols)} symbols)")

            async for message in ws:
                print(f"Raw Message Received: {message}")

                # 테스트 환경: 메시지를 파싱해서 실제 형식으로 발행
                if uri == TEST_URL:
                    print(f"[TEST MODE] Received message: {message}")
                    # 테스트 메시지도 실제 KIS API 형식으로 파싱
                    if message and len(message) > 0 and message[0] in ["0", "1"]:
                        parsed_data = KISParser.parse_trade_data(message)
                        if parsed_data:
                            channel = f"stock:realtime:{parsed_data['symbol']}"
                            payload = json.dumps(parsed_data)
                            num_subscribers = await redis_client.publish(
                                channel, payload
                            )
                            print(
                                f"[TEST MODE] Published to Redis: channel={channel}, data={parsed_data}, subscribers={num_subscribers}"
                            )
                        else:
                            print(f"[TEST MODE] Failed to parse message: {message}")
                    else:
                        # 파싱할 수 없는 메시지는 무시
                        print(f"[TEST MODE] Skipping non-parseable message: {message}")
                elif message and len(message) > 0 and message[0] in ["0", "1"]:
                    # 실제 KIS API 형식 메시지 처리
                    parsed_data = KISParser.parse_trade_data(message)
                    if parsed_data:
                        channel = f"stock:realtime:{parsed_data['symbol']}"
                        payload = json.dumps(parsed_data)
                        num_subscribers = await redis_client.publish(channel, payload)
                        print(
                            f"[PROD MODE] Published to Redis: channel={channel}, data={parsed_data}, subscribers={num_subscribers}"
                        )
                    else:
                        print(f"Failed to parse message: {message}")

        except websockets.ConnectionClosed as e:
            print(f"WebSocket connection closed: {e}")
            await asyncio.sleep(1)
            continue
        except Exception as e:
            print(f"Error in WebSocket loop: {e}")
            import traceback

            traceback.print_exc()
            await asyncio.sleep(1)
            continue


if __name__ == "__main__":
    print("Starting KIS Publisher...")
    try:
        asyncio.run(run_publisher())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()
        raise
