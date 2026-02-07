"""
RabbitMQ에서 실시간 주가 틱 데이터를 구독하여 WebSocket 클라이언트에게 브로드캐스트.

종목별 Channels 그룹(stock_{code})으로 선택적 전송.
"""

import asyncio
import os
import json
import aio_pika
from channels.layers import get_channel_layer
from django.core.management.base import BaseCommand

# RabbitMQ 설정
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
EXCHANGE_NAME = "stock.realtime"
QUEUE_NAME = "stock.ticks.channels"


class Command(BaseCommand):
    help = "RabbitMQ에서 주가 틱 데이터를 받아 WebSocket으로 브로드캐스트합니다."

    def handle(self, *args, **options):
        asyncio.run(self.main())

    async def main(self):
        self.stdout.write(f"[INIT] Connecting to RabbitMQ: {RABBITMQ_URL}")
        self.stdout.write(
            f"[INIT] Queue: {QUEUE_NAME}, Exchange: {EXCHANGE_NAME}"
        )

        # RabbitMQ 연결
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=100)
            self.stdout.write("[INIT] RabbitMQ connected")

            # Exchange 선언
            exchange = await channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.FANOUT,
                durable=True
            )

            # Queue 선언
            queue = await channel.declare_queue(
                QUEUE_NAME,
                durable=True,
                arguments={"x-max-length": 100000}
            )

            # Queue를 Exchange에 바인딩
            await queue.bind(exchange)
            self.stdout.write(f"[INIT] Queue '{QUEUE_NAME}' bound to '{EXCHANGE_NAME}'")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] RabbitMQ connection failed: {e}"))
            raise

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
        self.stdout.write("[INIT] Broadcasting to stock-specific groups (stock_{code})")
        self.stdout.write("[INIT] Listening for messages...")

        message_count = 0
        broadcast_count = 0

        # Consumer
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    async with message.process():  # 자동 ACK
                        message_count += 1

                        # 메시지 파싱
                        data = json.loads(message.body)

                        # 데이터 추출
                        stock_code = data.get("stock_code", "N/A")
                        symbol = data.get("symbol", "N/A")
                        time_str = data.get("time", "N/A")
                        price = data.get("price", "N/A")
                        volume = data.get("volume", "N/A")

                        # 종목별 그룹으로 브로드캐스트
                        group_name = f"stock_{stock_code}"
                        await channel_layer.group_send(
                            group_name,
                            {
                                "type": "stock_price_update",
                                "stock_code": stock_code,
                                "symbol": symbol,
                                "time": time_str,
                                "price": price,
                                "volume": volume,
                            },
                        )
                        broadcast_count += 1

                        # 로그 출력 (100개마다)
                        if message_count % 100 == 0:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"[BROADCAST] Processed {message_count} messages, "
                                    f"broadcasted {broadcast_count} to stock groups"
                                )
                            )

                except json.JSONDecodeError as e:
                    self.stdout.write(self.style.ERROR(f"[ERROR] JSON decode error: {e}"))
                    # JSON 파싱 실패 시 메시지 버림 (ACK)
                    await message.ack()
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"[ERROR] Unexpected error: {e}"))
                    import traceback
                    traceback.print_exc()
                    # 예외 발생 시 NACK (재큐잉)
                    # message.process()가 자동으로 처리
