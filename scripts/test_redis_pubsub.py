#!/usr/bin/env python3
"""
Redis Pub/Sub 테스트 스크립트

사용법:
1. Publisher 실행: python scripts/test_redis_pubsub.py publish
2. Subscriber 실행: python scripts/test_redis_pubsub.py subscribe
"""

import asyncio
import json
import sys
import redis.asyncio as redis
from datetime import datetime


REDIS_URL = "redis://localhost:6379/0"


async def test_publisher():
    """테스트 메시지를 Redis에 발행합니다."""
    print(f"[INIT] Connecting to Redis: {REDIS_URL}")
    r = redis.from_url(REDIS_URL)

    try:
        await r.ping()
        print("[INIT] Redis ping successful")
    except Exception as e:
        print(f"[ERROR] Redis ping failed: {e}")
        return

    print("[INIT] Starting publisher...")
    print("[INFO] Press Ctrl+C to stop")

    count = 0
    try:
        while True:
            count += 1
            # 테스트 데이터 생성
            test_data = {
                "symbol": "005930",
                "time": datetime.now().strftime("%H%M%S"),
                "price": 70000 + (count % 100),
                "volume": 100 * count,
            }

            channel = f"stock:realtime:{test_data['symbol']}"
            payload = json.dumps(test_data)

            # 발행
            num_subscribers = await r.publish(channel, payload)
            print(
                f"[PUBLISH #{count}] channel={channel}, data={test_data}, subscribers={num_subscribers}"
            )

            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Publisher stopped")
    finally:
        await r.close()


async def test_subscriber():
    """Redis 채널을 구독하고 메시지를 수신합니다."""
    print(f"[INIT] Connecting to Redis: {REDIS_URL}")
    r = redis.from_url(REDIS_URL)

    try:
        await r.ping()
        print("[INIT] Redis ping successful")
    except Exception as e:
        print(f"[ERROR] Redis ping failed: {e}")
        return

    pubsub = r.pubsub()
    await pubsub.psubscribe("stock:realtime:*")
    print("[INIT] Subscribed to Redis channel: stock:realtime:*")
    print("[INIT] Listening for messages...")
    print("[INFO] Press Ctrl+C to stop")

    message_count = 0
    try:
        async for message in pubsub.listen():
            print(f"[DEBUG] Received raw message: type={message['type']}")

            if message["type"] == "pmessage":
                message_count += 1
                channel = (
                    message["channel"].decode("utf-8")
                    if isinstance(message["channel"], bytes)
                    else message["channel"]
                )
                data_raw = (
                    message["data"].decode("utf-8")
                    if isinstance(message["data"], bytes)
                    else message["data"]
                )

                try:
                    data = json.loads(data_raw)
                    print(
                        f"[RECV #{message_count}] channel={channel}, data={data}"
                    )
                except json.JSONDecodeError as e:
                    print(f"[ERROR] Failed to parse JSON: {e}, raw={data_raw}")
    except KeyboardInterrupt:
        print("\n[INFO] Subscriber stopped")
    finally:
        await pubsub.unsubscribe()
        await r.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_redis_pubsub.py [publish|subscribe]")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "publish":
        asyncio.run(test_publisher())
    elif mode == "subscribe":
        asyncio.run(test_subscriber())
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python test_redis_pubsub.py [publish|subscribe]")
        sys.exit(1)


if __name__ == "__main__":
    main()
