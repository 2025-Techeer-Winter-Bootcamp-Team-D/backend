import json
from channels.generic.websocket import AsyncWebsocketConsumer


class StockPriceConsumer(AsyncWebsocketConsumer):
    """
    실시간 주가 데이터를 클라이언트에게 전송하는 WebSocket Consumer.

    - 클라이언트가 연결하면 'stock_prices' 그룹에 추가
    - subscribe_handler가 channel_layer.group_send로 데이터 전송
    - 클라이언트에게 JSON 형태로 실시간 주가 전달
    """

    async def connect(self):
        """WebSocket 연결 시 stock_prices 그룹에 추가"""
        self.group_name = "stock_prices"

        # 그룹에 채널 추가
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # WebSocket 연결 수락
        await self.accept()

        # 연결 확인 메시지 전송
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection_established",
                    "message": "실시간 주가 스트림에 연결되었습니다.",
                }
            )
        )

    async def disconnect(self, close_code):
        """WebSocket 연결 해제 시 그룹에서 제거"""
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """
        클라이언트로부터 메시지 수신 (선택적)
        - 특정 종목 구독/해제 등 확장 가능
        """
        # text_data와 bytes_data가 모두 None이면 무시
        if text_data is None and bytes_data is None:
            return

        # bytes_data가 있으면 UTF-8로 디코딩
        if bytes_data is not None:
            try:
                text_data = bytes_data.decode("utf-8")
            except UnicodeDecodeError:
                await self.send(
                    text_data=json.dumps(
                        {"type": "error", "message": "Invalid encoding"}
                    )
                )
                return

        # JSON 파싱
        try:
            data = json.loads(text_data)
            action = data.get("action")

            if action == "ping":
                await self.send(text_data=json.dumps({"type": "pong"}))

        except (json.JSONDecodeError, TypeError):
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def stock_price_update(self, event):
        """
        subscribe_handler에서 group_send로 호출되는 핸들러.
        실시간 주가 데이터를 클라이언트에게 전송.
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "stock_price",
                    "stock_code": event["stock_code"],
                    "symbol": event.get("symbol"),
                    "time": event["time"],
                    "price": event["price"],
                    "volume": event["volume"],
                }
            )
        )
