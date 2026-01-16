import asyncio
import os
import redis.asyncio as redis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.management.base import BaseCommand
from django.conf import settings

# Redis Stream 설정
STREAM_KEY = "stock:realtime"
CONSUMER_GROUP = "django_channels_group"
CONSUMER_NAME = os.getenv("CONSUMER_NAME", f"subscribe_handler_{os.getpid()}")


class Command(BaseCommand):
    help = "Redis Stream을 구독하여 실시간 주가 데이터를 Django Channels로 전송합니다."

    def handle(self, *args, **options):
        asyncio.run(self.main())

    async def ensure_consumer_group(self, redis_client):
        """Consumer Group이 없으면 생성"""
        try:
            await redis_client.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="$", mkstream=True
            )
            self.stdout.write(f"[INIT] Created consumer group: {CONSUMER_GROUP}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                self.stdout.write(
                    f"[INIT] Consumer group already exists: {CONSUMER_GROUP}"
                )
            else:
                raise

    async def main(self):
        self.stdout.write(f"[INIT] Connecting to Redis: {settings.REDIS_URL}")
        self.stdout.write(
            f"[INIT] Stream: {STREAM_KEY}, Group: {CONSUMER_GROUP}, Consumer: {CONSUMER_NAME}"
        )
        r = redis.from_url(settings.REDIS_URL)

        # Redis 연결 테스트
        try:
            await r.ping()
            self.stdout.write("[INIT] Redis ping successful")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] Redis ping failed: {e}"))
            raise

        # Consumer Group 생성/확인
        await self.ensure_consumer_group(r)

        # Django Channels Layer 가져오기
        channel_layer = get_channel_layer()
        if channel_layer is None:
            self.stdout.write(
                self.style.ERROR(
                    "[ERROR] Channel layer not configured. Check CHANNEL_LAYERS in settings."
                )
            )
            raise RuntimeError("Channel layer not configured")

        self.stdout.write("[INIT] Channel layer initialized")
        self.stdout.write("[INIT] Listening for stream messages...")

        message_count = 0
        broadcast_count = 0

        while True:
            try:
                # XREADGROUP: 새 메시지 읽기 (블로킹)
                messages = await r.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {STREAM_KEY: ">"},
                    count=100,
                    block=2000,
                )

                if messages:
                    for stream_name, entries in messages:
                        for entry_id, fields in entries:
                            message_count += 1

                            # bytes → str 변환
                            data = {}
                            for k, v in fields.items():
                                key = k.decode("utf-8") if isinstance(k, bytes) else k
                                val = v.decode("utf-8") if isinstance(v, bytes) else v
                                data[key] = val

                            # 데이터 추출
                            stock_code = data.get("stock_code", "N/A")
                            symbol = data.get("symbol", "N/A")
                            time_str = data.get("time", "N/A")
                            price = data.get("price", "N/A")
                            volume = data.get("volume", "N/A")

                            # Django Channels를 통해 클라이언트에게 전송
                            await channel_layer.group_send(
                                "stock_prices",  # StockPriceConsumer의 group_name
                                {
                                    "type": "stock_price_update",  # Consumer 메서드 이름
                                    "stock_code": stock_code,
                                    "symbol": symbol,
                                    "time": time_str,
                                    "price": price,
                                    "volume": volume,
                                },
                            )
                            broadcast_count += 1

                            # 메시지 처리 완료 → ACK
                            await r.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)

                            # 로그 출력 (100개마다)
                            if message_count % 100 == 0:
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"[BROADCAST] Processed {message_count} messages, "
                                        f"broadcasted {broadcast_count} to clients"
                                    )
                                )

            except redis.ConnectionError as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"[ERROR] Redis connection error: {e}. Reconnecting..."
                    )
                )
                await asyncio.sleep(5)
                r = redis.from_url(settings.REDIS_URL)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[ERROR] Unexpected error: {e}"))
                import traceback

                traceback.print_exc()
                await asyncio.sleep(1)
