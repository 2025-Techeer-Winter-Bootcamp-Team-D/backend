"""
Redis 기반 구독 상태 관리 서비스.

클라이언트별 구독 상태와 KIS API 구독 상태를 관리하며,
RabbitMQ RPC를 통해 kis-publisher와 통신합니다.
"""

import json
import asyncio
import uuid
import os
from typing import Set, Optional
import aio_pika
from django.core.cache import cache
import redis.asyncio as redis


# Redis 키 접두사
REDIS_PREFIX = "subscription"
# 클라이언트별 구독 종목: subscription:clients:{channel_name} -> Set[stock_code]
CLIENT_STOCKS_KEY = f"{REDIS_PREFIX}:clients:{{channel}}"
# 종목별 구독 클라이언트: subscription:stocks:{stock_code} -> Set[channel_name]
STOCK_CLIENTS_KEY = f"{REDIS_PREFIX}:stocks:{{code}}"
# KIS에 실제 구독 중인 종목: subscription:active -> Set[stock_code]
ACTIVE_SUBSCRIPTIONS_KEY = f"{REDIS_PREFIX}:active"

# RabbitMQ RPC 설정
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
RPC_QUEUE_NAME = "subscription.commands"
RPC_TIMEOUT = 10.0  # RPC 응답 대기 시간 (초)

# KIS API 최대 구독 종목 수
MAX_SUBSCRIPTIONS = int(os.getenv("KIS_MAX_SUBSCRIPTIONS", "40"))


class SubscriptionManager:
    """
    실시간 주가 구독 상태 관리 서비스.

    - Redis를 사용하여 클라이언트별/종목별 구독 상태 추적
    - RabbitMQ RPC로 kis-publisher에 구독/해제 명령 전송
    - KIS API의 40개 종목 제한 관리
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._rabbitmq_connection: Optional[aio_pika.Connection] = None
        self._rabbitmq_channel: Optional[aio_pika.Channel] = None
        self._callback_queue: Optional[aio_pika.Queue] = None
        self._pending_responses: dict = {}

    async def connect(self):
        """Redis 및 RabbitMQ 연결 초기화"""
        # Redis 연결
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._redis = redis.from_url(redis_url)

        # RabbitMQ 연결
        try:
            self._rabbitmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
            self._rabbitmq_channel = await self._rabbitmq_connection.channel()

            # RPC 응답 큐 생성 (자동 삭제)
            self._callback_queue = await self._rabbitmq_channel.declare_queue(
                exclusive=True
            )

            # 응답 리스너 시작
            await self._callback_queue.consume(self._on_rpc_response)
        except Exception as e:
            print(f"[SubscriptionManager] RabbitMQ connection failed: {e}")
            # RabbitMQ 연결 실패해도 Redis는 사용 가능

    async def close(self):
        """연결 종료"""
        if self._redis:
            await self._redis.close()
        if self._rabbitmq_connection:
            await self._rabbitmq_connection.close()

    async def _on_rpc_response(self, message: aio_pika.IncomingMessage):
        """RPC 응답 처리"""
        async with message.process():
            correlation_id = message.correlation_id
            if correlation_id in self._pending_responses:
                future = self._pending_responses.pop(correlation_id)
                if not future.done():
                    future.set_result(json.loads(message.body))

    async def _send_rpc_command(self, command: str, stock_codes: list) -> dict:
        """kis-publisher에 RPC 명령 전송"""
        if not self._rabbitmq_channel or not self._callback_queue:
            return {"success": False, "error": "RabbitMQ not connected"}

        correlation_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_responses[correlation_id] = future

        message = aio_pika.Message(
            body=json.dumps({
                "command": command,
                "stock_codes": stock_codes
            }).encode(),
            correlation_id=correlation_id,
            reply_to=self._callback_queue.name,
            content_type="application/json"
        )

        await self._rabbitmq_channel.default_exchange.publish(
            message,
            routing_key=RPC_QUEUE_NAME
        )

        try:
            result = await asyncio.wait_for(future, timeout=RPC_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            self._pending_responses.pop(correlation_id, None)
            return {"success": False, "error": "RPC timeout"}

    async def subscribe(
        self, channel_name: str, stock_codes: list[str]
    ) -> dict:
        """
        클라이언트의 종목 구독 요청 처리.

        Args:
            channel_name: WebSocket 채널 이름
            stock_codes: 구독할 종목 코드 목록

        Returns:
            {
                "success": bool,
                "subscribed": list[str],  # 성공적으로 구독된 종목
                "failed": list[str],      # 구독 실패한 종목
                "error": str              # 에러 메시지 (있는 경우)
            }
        """
        if not self._redis:
            return {"success": False, "subscribed": [], "failed": stock_codes,
                    "error": "Redis not connected"}

        subscribed = []
        failed = []
        new_subscriptions = []  # KIS에 새로 구독 요청할 종목

        # 현재 활성 구독 수 확인
        active_count = await self._redis.scard(ACTIVE_SUBSCRIPTIONS_KEY)

        for code in stock_codes:
            # 이 종목을 이미 다른 클라이언트가 구독 중인지 확인
            stock_clients_key = STOCK_CLIENTS_KEY.format(code=code)
            client_count = await self._redis.scard(stock_clients_key)

            if client_count > 0:
                # 이미 KIS에 구독 중이므로 클라이언트만 추가
                await self._redis.sadd(stock_clients_key, channel_name)
                client_stocks_key = CLIENT_STOCKS_KEY.format(channel=channel_name)
                await self._redis.sadd(client_stocks_key, code)
                subscribed.append(code)
            else:
                # 새로 KIS 구독 필요
                if active_count + len(new_subscriptions) >= MAX_SUBSCRIPTIONS:
                    failed.append(code)
                    continue

                new_subscriptions.append(code)

        # KIS에 새 구독 요청
        if new_subscriptions:
            rpc_result = await self._send_rpc_command("subscribe", new_subscriptions)

            if rpc_result.get("success"):
                kis_subscribed = rpc_result.get("subscribed", [])
                kis_failed = rpc_result.get("failed", [])

                for code in kis_subscribed:
                    # Redis 상태 업데이트
                    stock_clients_key = STOCK_CLIENTS_KEY.format(code=code)
                    await self._redis.sadd(stock_clients_key, channel_name)
                    client_stocks_key = CLIENT_STOCKS_KEY.format(channel=channel_name)
                    await self._redis.sadd(client_stocks_key, code)
                    await self._redis.sadd(ACTIVE_SUBSCRIPTIONS_KEY, code)
                    subscribed.append(code)

                failed.extend(kis_failed)
            else:
                # RPC 실패 시 모든 새 구독 실패 처리
                failed.extend(new_subscriptions)

        return {
            "success": len(failed) == 0,
            "subscribed": subscribed,
            "failed": failed,
            "error": None if len(failed) == 0 else f"{len(failed)}개 종목 구독 실패"
        }

    async def unsubscribe(
        self, channel_name: str, stock_codes: list[str]
    ) -> dict:
        """
        클라이언트의 종목 구독 해제 요청 처리.

        Args:
            channel_name: WebSocket 채널 이름
            stock_codes: 구독 해제할 종목 코드 목록

        Returns:
            {
                "success": bool,
                "unsubscribed": list[str],
                "error": str
            }
        """
        if not self._redis:
            return {"success": False, "unsubscribed": [], "error": "Redis not connected"}

        unsubscribed = []
        codes_to_unsubscribe_from_kis = []

        for code in stock_codes:
            stock_clients_key = STOCK_CLIENTS_KEY.format(code=code)
            client_stocks_key = CLIENT_STOCKS_KEY.format(channel=channel_name)

            # 클라이언트 구독 해제
            await self._redis.srem(stock_clients_key, channel_name)
            await self._redis.srem(client_stocks_key, code)
            unsubscribed.append(code)

            # 이 종목을 구독 중인 클라이언트가 없으면 KIS 해제 대상
            remaining_clients = await self._redis.scard(stock_clients_key)
            if remaining_clients == 0:
                codes_to_unsubscribe_from_kis.append(code)
                await self._redis.srem(ACTIVE_SUBSCRIPTIONS_KEY, code)

        # KIS 구독 해제 요청
        if codes_to_unsubscribe_from_kis:
            await self._send_rpc_command("unsubscribe", codes_to_unsubscribe_from_kis)

        return {
            "success": True,
            "unsubscribed": unsubscribed,
            "error": None
        }

    async def cleanup_client(self, channel_name: str):
        """
        클라이언트 연결 종료 시 구독 정리.

        Args:
            channel_name: 종료된 WebSocket 채널 이름
        """
        if not self._redis:
            return

        client_stocks_key = CLIENT_STOCKS_KEY.format(channel=channel_name)

        # 클라이언트가 구독 중인 모든 종목 가져오기
        subscribed_codes = await self._redis.smembers(client_stocks_key)

        if subscribed_codes:
            # bytes를 str로 변환
            codes = [c.decode() if isinstance(c, bytes) else c for c in subscribed_codes]
            await self.unsubscribe(channel_name, codes)

        # 클라이언트 키 삭제
        await self._redis.delete(client_stocks_key)

    async def get_client_subscriptions(self, channel_name: str) -> Set[str]:
        """클라이언트가 구독 중인 종목 목록 조회"""
        if not self._redis:
            return set()

        client_stocks_key = CLIENT_STOCKS_KEY.format(channel=channel_name)
        codes = await self._redis.smembers(client_stocks_key)
        return {c.decode() if isinstance(c, bytes) else c for c in codes}

    async def get_active_subscriptions(self) -> Set[str]:
        """KIS에 활성화된 구독 종목 목록 조회"""
        if not self._redis:
            return set()

        codes = await self._redis.smembers(ACTIVE_SUBSCRIPTIONS_KEY)
        return {c.decode() if isinstance(c, bytes) else c for c in codes}

    async def get_subscription_count(self) -> int:
        """현재 KIS 구독 종목 수 조회"""
        if not self._redis:
            return 0

        return await self._redis.scard(ACTIVE_SUBSCRIPTIONS_KEY)


# 싱글톤 인스턴스
_subscription_manager: Optional[SubscriptionManager] = None


async def get_subscription_manager() -> SubscriptionManager:
    """SubscriptionManager 싱글톤 인스턴스 반환"""
    global _subscription_manager
    if _subscription_manager is None:
        _subscription_manager = SubscriptionManager()
        await _subscription_manager.connect()
    return _subscription_manager
