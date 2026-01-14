"""
KIS API Mock WebSocket Server for local testing.
실행: python mock_server.py
"""

import asyncio
import json
import random
import websockets
from datetime import datetime

# 테스트용 종목 코드
TEST_SYMBOLS = ["005930", "000660", "035720", "051910", "068270"]

async def generate_trade_data(symbol: str) -> str:
    """KIS API 형식의 실시간 체결 데이터 생성"""
    now = datetime.now()
    time_str = now.strftime("%H%M%S")

    # 임의의 가격과 거래량 생성
    base_prices = {
        "005930": 71000,  # 삼성전자
        "000660": 180000,  # SK하이닉스
        "035720": 55000,   # 카카오
        "051910": 450000,  # LG화학
        "068270": 180000,  # 셀트리온
    }
    base_price = base_prices.get(symbol, 50000)
    price = base_price + random.randint(-500, 500)
    volume = random.randint(1, 100)

    # KIS API 형식: 데이터구분|TR_ID|심볼|데이터부(^로 구분)
    # 데이터부: 종목코드^시간^현재가^...^체결량^...
    data_parts = [symbol, time_str, str(price)] + ["0"] * 9 + [str(volume)] + ["0"] * 30
    body = "^".join(data_parts)

    # 형식: 0|H0STCNT0|001|데이터부
    return f"0|H0STCNT0|001|{body}"

async def handle_connection(websocket):
    """WebSocket 클라이언트 연결 처리"""
    print(f"[MOCK] Client connected: {websocket.remote_address}")

    subscribed_symbols = []

    try:
        # 구독 메시지 처리 및 실시간 데이터 전송 동시 실행
        async def receive_messages():
            nonlocal subscribed_symbols
            async for message in websocket:
                try:
                    msg = json.loads(message)
                    tr_id = msg.get("body", {}).get("input", {}).get("tr_id", "")
                    tr_key = msg.get("body", {}).get("input", {}).get("tr_key", "")

                    if tr_id == "H0STCNT0" and tr_key:
                        subscribed_symbols.append(tr_key)
                        print(f"[MOCK] Subscribed to: {tr_key}")

                        # 구독 성공 응답
                        response = {
                            "header": {"tr_id": "H0STCNT0", "tr_key": tr_key, "encrypt": "N"},
                            "body": {"rt_cd": "0", "msg_cd": "OPSP0000", "msg1": "SUBSCRIBE SUCCESS"}
                        }
                        await websocket.send(json.dumps(response))
                except json.JSONDecodeError:
                    print(f"[MOCK] Invalid JSON: {message[:100]}")

        async def send_data():
            while True:
                if subscribed_symbols:
                    # 구독된 종목 중 하나 선택하여 데이터 전송
                    symbol = random.choice(subscribed_symbols)
                    data = await generate_trade_data(symbol)
                    await websocket.send(data)
                await asyncio.sleep(1)  # 1초마다 데이터 전송

        # 두 태스크 동시 실행
        receive_task = asyncio.create_task(receive_messages())
        send_task = asyncio.create_task(send_data())

        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

    except websockets.ConnectionClosed:
        print(f"[MOCK] Client disconnected: {websocket.remote_address}")
    except Exception as e:
        print(f"[MOCK] Error: {e}")

async def main():
    port = 8080
    print(f"[MOCK] Starting Mock KIS WebSocket Server on port {port}...")
    async with websockets.serve(handle_connection, "0.0.0.0", port):
        print(f"[MOCK] Server is running at ws://localhost:{port}")
        await asyncio.Future()  # 무한 대기

if __name__ == "__main__":
    asyncio.run(main())
