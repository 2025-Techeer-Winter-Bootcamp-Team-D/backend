import asyncio
import redis.asyncio as redis
from django.core.management.base import BaseCommand
from django.conf import settings
import json


class Command(BaseCommand):
    help = "Redis Pub/Sub을 구독하여 처리합니다."

    def handle(self, *args, **options):
        asyncio.run(self.main())

    async def main(self):
        self.stdout.write(f"[INIT] Connecting to Redis: {settings.REDIS_URL}")
        r = redis.from_url(settings.REDIS_URL)

        # Redis 연결 테스트
        try:
            await r.ping()
            self.stdout.write("[INIT] Redis ping successful")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] Redis ping failed: {e}"))
            raise

        pubsub = r.pubsub()
        await pubsub.psubscribe("stock:realtime:*")
        self.stdout.write("[INIT] Subscribed to Redis channel: stock:realtime:*")
        self.stdout.write("[INIT] Listening for messages...")

        message_count = 0
        async for message in pubsub.listen():
            self.stdout.write(f"[DEBUG] Received raw message: type={message['type']}")

            if message["type"] == "pmessage":
                message_count += 1
                raw_json = (
                    message["data"].decode("utf-8")
                    if isinstance(message["data"], bytes)
                    else message["data"]
                )
                channel = (
                    message["channel"].decode("utf-8")
                    if isinstance(message["channel"], bytes)
                    else message["channel"]
                )

                try:
                    # JSON 파싱
                    data = json.loads(raw_json)

                    # data 추출
                    symbol = data.get("symbol", "N/A")
                    time = data.get("time", "N/A")
                    price = data.get("price", "N/A")
                    volume = data.get("volume", "N/A")

                    # TODO: 여기서 Django Channels를 통해 클라이언트에게 전송
                    # 현재는 로그 출력만 수행
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[RECV #{message_count}] [{time}] {symbol} {price} {volume} (channel: {channel})"
                        )
                    )
                except json.JSONDecodeError:
                    self.stdout.write(
                        self.style.ERROR(f"[ERROR] Failed to parse JSON: {raw_json}")
                    )
