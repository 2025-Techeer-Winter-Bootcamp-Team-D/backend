"""
실시간 주가 WebSocket Consumer.

클라이언트의 동적 구독/해제 요청을 처리하고,
종목별로 실시간 데이터를 전송합니다.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from core.services.subscription_manager import get_subscription_manager


class StockPriceConsumer(AsyncWebsocketConsumer):
    """
    실시간 주가 데이터를 클라이언트에게 전송하는 WebSocket Consumer.

    - 클라이언트별 동적 종목 구독/해제 지원
    - 종목별 Channels 그룹으로 선택적 데이터 수신
    - 연결 해제 시 자동 정리
    """

    async def connect(self):
        """WebSocket 연결 시 초기화"""
        # 클라이언트가 구독 중인 종목 코드 집합
        self.subscribed_codes = set()

        # WebSocket 연결 수락
        await self.accept()

        # 연결 확인 메시지 전송
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection_established",
                    "message": "실시간 주가 스트림에 연결되었습니다.",
                    "actions": ["subscribe", "unsubscribe", "list_subscriptions", "ping"]
                }
            )
        )

    async def disconnect(self, close_code):
        """WebSocket 연결 해제 시 정리"""
        # 구독 중인 모든 종목 그룹에서 나가기
        for code in self.subscribed_codes:
            group_name = f"stock_{code}"
            await self.channel_layer.group_discard(group_name, self.channel_name)

        # SubscriptionManager에서 클라이언트 정리
        try:
            manager = await get_subscription_manager()
            await manager.cleanup_client(self.channel_name)
        except Exception as e:
            print(f"[StockPriceConsumer] Cleanup error: {e}")

    async def receive(self, text_data=None, bytes_data=None):
        """
        클라이언트로부터 메시지 수신 및 처리.

        지원 액션:
        - subscribe: 종목 구독
        - unsubscribe: 종목 구독 해제
        - list_subscriptions: 현재 구독 목록 조회
        - ping: 연결 확인
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

            elif action == "subscribe":
                await self._handle_subscribe(data.get("codes", []))

            elif action == "unsubscribe":
                await self._handle_unsubscribe(data.get("codes", []))

            elif action == "list_subscriptions":
                await self._handle_list_subscriptions()

            else:
                await self.send(
                    text_data=json.dumps({
                        "type": "error",
                        "message": f"Unknown action: {action}"
                    })
                )

        except (json.JSONDecodeError, TypeError):
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def _handle_subscribe(self, codes: list):
        """종목 구독 요청 처리"""
        if not codes:
            await self.send(
                text_data=json.dumps({
                    "type": "subscription_result",
                    "success": False,
                    "subscribed": [],
                    "failed": [],
                    "error": "구독할 종목 코드를 입력해주세요."
                })
            )
            return

        # 종목 코드 유효성 검사 (6자리 숫자)
        valid_codes = []
        invalid_codes = []
        for code in codes:
            if isinstance(code, str) and len(code) == 6 and code.isdigit():
                valid_codes.append(code)
            else:
                invalid_codes.append(code)

        if invalid_codes:
            await self.send(
                text_data=json.dumps({
                    "type": "warning",
                    "message": f"유효하지 않은 종목 코드: {invalid_codes}"
                })
            )

        if not valid_codes:
            await self.send(
                text_data=json.dumps({
                    "type": "subscription_result",
                    "success": False,
                    "subscribed": [],
                    "failed": codes,
                    "error": "유효한 종목 코드가 없습니다."
                })
            )
            return

        try:
            manager = await get_subscription_manager()
            result = await manager.subscribe(self.channel_name, valid_codes)

            # 성공한 종목에 대해 Channels 그룹 가입
            for code in result.get("subscribed", []):
                if code not in self.subscribed_codes:
                    group_name = f"stock_{code}"
                    await self.channel_layer.group_add(group_name, self.channel_name)
                    self.subscribed_codes.add(code)

            await self.send(
                text_data=json.dumps({
                    "type": "subscription_result",
                    "success": result["success"],
                    "subscribed": result["subscribed"],
                    "failed": result["failed"] + invalid_codes,
                    "error": result.get("error"),
                    "total_subscribed": len(self.subscribed_codes)
                })
            )

        except Exception as e:
            await self.send(
                text_data=json.dumps({
                    "type": "subscription_result",
                    "success": False,
                    "subscribed": [],
                    "failed": valid_codes,
                    "error": f"구독 처리 중 오류: {str(e)}"
                })
            )

    async def _handle_unsubscribe(self, codes: list):
        """종목 구독 해제 요청 처리"""
        if not codes:
            await self.send(
                text_data=json.dumps({
                    "type": "unsubscription_result",
                    "success": False,
                    "unsubscribed": [],
                    "error": "해제할 종목 코드를 입력해주세요."
                })
            )
            return

        # 실제로 구독 중인 종목만 해제
        codes_to_unsubscribe = [c for c in codes if c in self.subscribed_codes]

        if not codes_to_unsubscribe:
            await self.send(
                text_data=json.dumps({
                    "type": "unsubscription_result",
                    "success": True,
                    "unsubscribed": [],
                    "message": "해제할 구독이 없습니다."
                })
            )
            return

        try:
            manager = await get_subscription_manager()
            result = await manager.unsubscribe(self.channel_name, codes_to_unsubscribe)

            # 해제된 종목에 대해 Channels 그룹 탈퇴
            for code in result.get("unsubscribed", []):
                if code in self.subscribed_codes:
                    group_name = f"stock_{code}"
                    await self.channel_layer.group_discard(group_name, self.channel_name)
                    self.subscribed_codes.discard(code)

            await self.send(
                text_data=json.dumps({
                    "type": "unsubscription_result",
                    "success": result["success"],
                    "unsubscribed": result["unsubscribed"],
                    "error": result.get("error"),
                    "total_subscribed": len(self.subscribed_codes)
                })
            )

        except Exception as e:
            await self.send(
                text_data=json.dumps({
                    "type": "unsubscription_result",
                    "success": False,
                    "unsubscribed": [],
                    "error": f"구독 해제 중 오류: {str(e)}"
                })
            )

    async def _handle_list_subscriptions(self):
        """현재 구독 목록 조회"""
        try:
            manager = await get_subscription_manager()
            active_count = await manager.get_subscription_count()

            await self.send(
                text_data=json.dumps({
                    "type": "subscriptions_list",
                    "subscribed_codes": list(self.subscribed_codes),
                    "count": len(self.subscribed_codes),
                    "kis_active_subscriptions": active_count,
                    "kis_max_subscriptions": 40
                })
            )
        except Exception as e:
            await self.send(
                text_data=json.dumps({
                    "type": "subscriptions_list",
                    "subscribed_codes": list(self.subscribed_codes),
                    "count": len(self.subscribed_codes),
                    "error": str(e)
                })
            )

    async def stock_price_update(self, event):
        """
        subscribe_handler에서 group_send로 호출되는 핸들러.
        실시간 주가 데이터를 클라이언트에게 전송.
        """
        stock_code = event.get("stock_code")

        # 구독 중인 종목만 전송 (이중 체크)
        if stock_code not in self.subscribed_codes:
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "stock_price",
                    "stock_code": stock_code,
                    "symbol": event.get("symbol"),
                    "time": event["time"],
                    "price": event["price"],
                    "volume": event["volume"],
                }
            )
        )
