"""
KIS API Mock WebSocket Server for local testing.

동적 구독/해제를 지원하는 테스트 서버.
실행: python mock_server.py
"""

import asyncio
import json
import random
import websockets
from datetime import datetime

# 테스트용 종목 코드와 기준 가격
BASE_PRICES = {
    "005930": 71000,   # 삼성전자
    "000660": 180000,  # SK하이닉스
    "035720": 55000,   # 카카오
    "051910": 450000,  # LG화학
    "068270": 180000,  # 셀트리온
    "035420": 210000,  # NAVER
    "006400": 55000,   # 삼성SDI
    "207940": 750000,  # 삼성바이오로직스
    "373220": 240000,  # LG에너지솔루션
    "105560": 75000,   # KB금융
}


async def generate_trade_data(symbol: str) -> str:
    """KIS API 형식의 실시간 체결 데이터 생성"""
    now = datetime.now()
    time_str = now.strftime("%H%M%S")

    base_price = BASE_PRICES.get(symbol, 50000)
    price = base_price + random.randint(-500, 500)
    volume = random.randint(1, 100)

    # KIS API 형식: 데이터구분|TR_ID|심볼|데이터부(^로 구분)
    data_parts = [symbol, time_str, str(price)] + ["0"] * 9 + [str(volume)] + ["0"] * 30
    body = "^".join(data_parts)

    return f"0|H0STCNT0|001|{body}"


async def handle_connection(websocket):
    """WebSocket 클라이언트 연결 처리"""
    print(f"[MOCK] Client connected: {websocket.remote_address}")

    subscribed_symbols = set()

    try:
        async def receive_messages():
            """클라이언트 메시지 수신 및 처리"""
            nonlocal subscribed_symbols
            async for message in websocket:
                try:
                    msg = json.loads(message)
                    tr_type = msg.get("header", {}).get("tr_type", "1")
                    tr_id = msg.get("body", {}).get("input", {}).get("tr_id", "")
                    tr_key = msg.get("body", {}).get("input", {}).get("tr_key", "")

                    if tr_id == "H0STCNT0" and tr_key:
                        if tr_type == "1":
                            # 구독 요청
                            subscribed_symbols.add(tr_key)
                            print(f"[MOCK] Subscribed to: {tr_key} "
                                  f"(total: {len(subscribed_symbols)})")

                            # 구독 성공 응답
                            response = {
                                "header": {
                                    "tr_id": "H0STCNT0",
                                    "tr_key": tr_key,
                                    "encrypt": "N"
                                },
                                "body": {
                                    "rt_cd": "0",
                                    "msg_cd": "OPSP0000",
                                    "msg1": "SUBSCRIBE SUCCESS"
                                }
                            }
                            await websocket.send(json.dumps(response))

                        elif tr_type == "2":
                            # 구독 해제 요청
                            subscribed_symbols.discard(tr_key)
                            print(f"[MOCK] Unsubscribed from: {tr_key} "
                                  f"(total: {len(subscribed_symbols)})")

                            # 해제 성공 응답
                            response = {
                                "header": {
                                    "tr_id": "H0STCNT0",
                                    "tr_key": tr_key,
                                    "encrypt": "N"
                                },
                                "body": {
                                    "rt_cd": "0",
                                    "msg_cd": "OPSP0001",
                                    "msg1": "UNSUBSCRIBE SUCCESS"
                                }
                            }
                            await websocket.send(json.dumps(response))

                except json.JSONDecodeError:
                    print(f"[MOCK] Invalid JSON: {message[:100]}")

        async def send_data():
            """구독된 종목의 실시간 데이터 전송"""
            while True:
                if subscribed_symbols:
                    # 구독된 종목 중 하나 선택하여 데이터 전송
                    symbol = random.choice(list(subscribed_symbols))
                    data = await generate_trade_data(symbol)
                    try:
                        await websocket.send(data)
                    except websockets.ConnectionClosed:
                        break
                await asyncio.sleep(0.5)  # 0.5초마다 데이터 전송

        # 두 태스크 동시 실행
        receive_task = asyncio.create_task(receive_messages())
        send_task = asyncio.create_task(send_data())

        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except websockets.ConnectionClosed:
        print(f"[MOCK] Client disconnected: {websocket.remote_address}")
    except Exception as e:
        print(f"[MOCK] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"[MOCK] Connection closed. Final subscriptions: {subscribed_symbols}")


async def main():
    port = 8080
    print(f"[MOCK] Starting Mock KIS WebSocket Server on port {port}...")
    print("[MOCK] Supports dynamic subscribe (tr_type=1) and unsubscribe (tr_type=2)")
    async with websockets.serve(handle_connection, "0.0.0.0", port):
        print(f"[MOCK] Server is running at ws://localhost:{port}")
        await asyncio.Future()  # 무한 대기


if __name__ == "__main__":
    asyncio.run(main())
