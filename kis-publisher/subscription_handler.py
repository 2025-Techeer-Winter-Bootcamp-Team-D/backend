"""
KIS WebSocket 동적 구독/해제 핸들러.

RPC 명령을 받아 KIS WebSocket에 구독/해제 메시지를 전송합니다.
"""

import json
import os
import asyncio
from typing import Set


# KIS API 최대 구독 종목 수
MAX_SUBSCRIPTIONS = int(os.getenv("KIS_MAX_SUBSCRIPTIONS", "40"))

# 구독 딜레이 (서버 과부하 방지)
SUBSCRIPTION_DELAY = float(os.getenv("KIS_SUBSCRIPTION_DELAY", "0.3"))


class SubscriptionHandler:
    """
    KIS WebSocket 동적 구독 관리.

    - 구독/해제 메시지 생성
    - 40개 종목 제한 관리
    - 재연결 시 구독 복원
    """

    def __init__(self, websocket=None, approval_key: str = None, is_test_mode: bool = False):
        self._websocket = websocket
        self._approval_key = approval_key
        self._is_test_mode = is_test_mode
        self._subscribed_codes: Set[str] = set()
        self._app_key = os.getenv("KIS_APP_KEY")
        self._app_secret = os.getenv("KIS_APP_SECRET")

    def set_websocket(self, websocket, approval_key: str = None):
        """WebSocket 연결 설정"""
        self._websocket = websocket
        if approval_key:
            self._approval_key = approval_key

    def set_test_mode(self, is_test_mode: bool):
        """테스트 모드 설정"""
        self._is_test_mode = is_test_mode

    @property
    def subscribed_codes(self) -> Set[str]:
        """현재 구독 중인 종목 코드 목록"""
        return self._subscribed_codes.copy()

    @property
    def subscription_count(self) -> int:
        """현재 구독 종목 수"""
        return len(self._subscribed_codes)

    def _build_subscribe_message(self, stock_code: str, tr_type: str = "1") -> dict:
        """
        KIS 구독/해제 메시지 생성.

        Args:
            stock_code: 종목 코드
            tr_type: "1" = 구독, "2" = 해제

        Returns:
            KIS WebSocket 메시지 딕셔너리
        """
        if self._is_test_mode:
            # 테스트 모드: 간소화된 메시지
            return {
                "header": {"tr_type": tr_type},
                "body": {
                    "input": {"tr_id": "H0STCNT0", "tr_key": stock_code}
                },
            }
        else:
            # 실제 KIS API 메시지
            return {
                "header": {
                    "approval_key": self._approval_key,
                    "appkey": self._app_key,
                    "secretkey": self._app_secret,
                    "custtype": "P",
                    "tr_type": tr_type,
                    "content-type": "utf-8",
                },
                "body": {
                    "input": {"tr_id": "H0STCNT0", "tr_key": stock_code}
                },
            }

    async def subscribe(self, stock_codes: list[str]) -> dict:
        """
        종목 구독 요청.

        Args:
            stock_codes: 구독할 종목 코드 목록

        Returns:
            {
                "success": bool,
                "subscribed": list[str],
                "failed": list[str],
                "error": str
            }
        """
        if not self._websocket:
            return {
                "success": False,
                "subscribed": [],
                "failed": stock_codes,
                "error": "WebSocket not connected"
            }

        subscribed = []
        failed = []

        for code in stock_codes:
            # 최대 구독 수 체크
            if len(self._subscribed_codes) >= MAX_SUBSCRIPTIONS:
                print(f"[SubscriptionHandler] Max subscriptions ({MAX_SUBSCRIPTIONS}) reached")
                failed.append(code)
                continue

            # 이미 구독 중인 종목은 스킵
            if code in self._subscribed_codes:
                subscribed.append(code)
                continue

            try:
                message = self._build_subscribe_message(code, tr_type="1")
                await self._websocket.send(json.dumps(message))
                print(f"[SubscriptionHandler] Subscribe sent: {code}")

                # 테스트 모드에서는 응답 대기 없이 바로 성공 처리
                # (메인 루프에서 이미 recv()를 사용 중이므로 충돌 방지)
                if self._is_test_mode:
                    self._subscribed_codes.add(code)
                    subscribed.append(code)
                    print(f"[SubscriptionHandler] Subscribe success (test mode): {code}")
                else:
                    # 실제 KIS API: 응답 대기 (메인 루프 시작 전에만 사용)
                    # NOTE: 동적 구독 시에는 응답을 받지 않고 성공으로 간주
                    self._subscribed_codes.add(code)
                    subscribed.append(code)
                    print(f"[SubscriptionHandler] Subscribe sent (no wait): {code}")

                # 딜레이 적용
                await asyncio.sleep(SUBSCRIPTION_DELAY)

            except Exception as e:
                print(f"[SubscriptionHandler] Subscribe error: {code} - {e}")
                failed.append(code)

        return {
            "success": len(failed) == 0,
            "subscribed": subscribed,
            "failed": failed,
            "error": None if len(failed) == 0 else f"{len(failed)}개 종목 구독 실패"
        }

    async def unsubscribe(self, stock_codes: list[str]) -> dict:
        """
        종목 구독 해제 요청.

        Args:
            stock_codes: 해제할 종목 코드 목록

        Returns:
            {
                "success": bool,
                "unsubscribed": list[str],
                "error": str
            }
        """
        if not self._websocket:
            return {
                "success": False,
                "unsubscribed": [],
                "error": "WebSocket not connected"
            }

        unsubscribed = []

        for code in stock_codes:
            # 구독 중이 아닌 종목은 스킵
            if code not in self._subscribed_codes:
                continue

            try:
                message = self._build_subscribe_message(code, tr_type="2")
                await self._websocket.send(json.dumps(message))
                print(f"[SubscriptionHandler] Unsubscribe sent: {code}")

                # 응답 대기 없이 바로 구독 해제 처리
                self._subscribed_codes.discard(code)
                unsubscribed.append(code)

                # 딜레이 적용
                await asyncio.sleep(SUBSCRIPTION_DELAY)

            except Exception as e:
                print(f"[SubscriptionHandler] Unsubscribe error: {code} - {e}")

        return {
            "success": True,
            "unsubscribed": unsubscribed,
            "error": None
        }

    async def restore_subscriptions(self):
        """
        재연결 시 기존 구독 복원.

        저장된 구독 목록을 다시 구독합니다.
        """
        if not self._subscribed_codes:
            print("[SubscriptionHandler] No subscriptions to restore")
            return

        codes_to_restore = list(self._subscribed_codes)
        self._subscribed_codes.clear()  # 초기화 후 재구독

        print(f"[SubscriptionHandler] Restoring {len(codes_to_restore)} subscriptions...")
        result = await self.subscribe(codes_to_restore)
        print(f"[SubscriptionHandler] Restored: {len(result['subscribed'])}, "
              f"Failed: {len(result['failed'])}")

        return result

    def clear_subscriptions(self):
        """구독 목록 초기화"""
        self._subscribed_codes.clear()
