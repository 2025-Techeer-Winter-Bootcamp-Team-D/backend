# companies/services/kis_quote.py
"""
KIS (한국투자증권) REST API 시세 클라이언트
시가총액 등 현재가 시세 정보를 조회하는 서비스
"""
import os
import logging
import time
import requests
from typing import Optional
from datetime import datetime, timedelta
from django.core.cache import cache

logger = logging.getLogger(__name__)

# KIS API 환경 설정
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
# 실전투자: https://openapi.koreainvestment.com:9443
# 모의투자: https://openapivts.koreainvestment.com:29443
KIS_BASE_URL = os.getenv(
    "KIS_REST_BASE_URL", "https://openapivts.koreainvestment.com:29443"
)

# 토큰 캐시 키
TOKEN_CACHE_KEY = "kis_access_token"
TOKEN_CACHE_TIMEOUT = 60 * 60 * 23  # 23시간 (토큰 유효기간 24시간)

# Rate Limiting: 요청 간 최소 딜레이 (초)
# KIS API는 초당 2회로 제한되어 있으므로 최소 500ms 딜레이 필요
# 네트워크 지연 및 안전 마진을 위해 520ms로 설정 (초당 약 1.92회)
REQUEST_DELAY = 0.52  # 520ms 딜레이 (초당 2회 제한 준수 + 안전 마진)

# 분산 락 및 마지막 요청 시간 관리용 Redis 키
KIS_RATE_LIMIT_LOCK_KEY = "kis_api_rate_limit_lock"
KIS_LAST_REQUEST_TIME_KEY = "kis_api_last_request_time"


class KISQuoteError(Exception):
    """KIS API 호출 오류"""

    pass


class KISQuoteClient:
    """KIS REST API 시세 클라이언트"""

    def __init__(self):
        self.app_key = KIS_APP_KEY
        self.app_secret = KIS_APP_SECRET
        self.base_url = KIS_BASE_URL

        if not self.app_key or not self.app_secret:
            logger.warning(
                "KIS_APP_KEY 또는 KIS_APP_SECRET 환경변수가 설정되지 않았습니다."
            )

    def _get_access_token(self) -> Optional[str]:
        """
        KIS REST API 접속 토큰 발급 (캐싱 포함)

        Returns:
            access_token 문자열 또는 None
        """
        # 캐시에서 토큰 조회 (캐시 연결 오류 시 무시)
        try:
            cached_token = cache.get(TOKEN_CACHE_KEY)
            if cached_token:
                logger.debug("캐시된 KIS 토큰 사용")
                return cached_token
        except Exception as e:
            # 캐시 연결 오류 시 무시하고 토큰 신규 발급
            logger.debug(f"캐시 조회 실패 (토큰 신규 발급): {e}")

        # 토큰 신규 발급
        if not self.app_key or not self.app_secret:
            logger.error("KIS API 인증 정보가 없습니다.")
            return None

        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            access_token = data.get("access_token")
            if not access_token:
                logger.error(f"토큰 발급 응답에 access_token 없음: {data}")
                return None

            # 캐시에 토큰 저장 (캐시 연결 오류 시 무시)
            try:
                cache.set(TOKEN_CACHE_KEY, access_token, TOKEN_CACHE_TIMEOUT)
                logger.info("KIS 토큰 발급 및 캐싱 완료")
            except Exception as e:
                # 캐시 저장 실패해도 토큰은 반환
                logger.debug(f"캐시 저장 실패 (토큰은 사용 가능): {e}")
                logger.info("KIS 토큰 발급 완료 (캐싱 실패)")

            return access_token

        except requests.RequestException as e:
            logger.error(f"KIS 토큰 발급 실패: {e}")
            return None

    def _wait_for_rate_limit(self) -> None:
        """
        분산 환경에서 KIS API rate limit 준수를 위한 전역 딜레이 관리

        Redis 분산 락을 사용하여 동시성 문제를 해결하고,
        마지막 요청 시간을 공유하여 초당 2회 제한을 준수합니다.

        여러 워커가 동시에 실행되어도 하나의 워커만 rate limit을 체크하고
        업데이트하도록 보장합니다.

        캐시 연결 오류 시 단순 딜레이로 fallback
        """
        try:
            # 락 TTL: REQUEST_DELAY보다 약간 길게 설정 (안전 마진)
            lock_ttl = REQUEST_DELAY + 0.1  # 초 단위 (Django cache timeout은 초 단위)
            max_retries = 10
            retry_backoff = 0.01  # 10ms

            # 분산 락 획득 시도
            lock_acquired = False
            for attempt in range(max_retries):
                # cache.add는 키가 존재하지 않을 때만 True 반환 (원자적 연산)
                try:
                    lock_acquired = cache.add(
                        KIS_RATE_LIMIT_LOCK_KEY, "locked", timeout=lock_ttl
                    )
                    if lock_acquired:
                        break
                except Exception:
                    # 캐시 연결 오류 시 락 획득 실패로 간주
                    break

                # 락 획득 실패 시 짧은 backoff 후 재시도
                if attempt < max_retries - 1:
                    time.sleep(retry_backoff)
                else:
                    logger.warning(
                        "KIS rate limit 락 획득 실패 (최대 재시도 횟수 초과). "
                        "락이 해제될 때까지 대기합니다."
                    )
                    # 최종 시도 실패 시 락이 해제될 때까지 대기
                    try:
                        while not cache.add(
                            KIS_RATE_LIMIT_LOCK_KEY, "locked", timeout=lock_ttl
                        ):
                            time.sleep(retry_backoff)
                        lock_acquired = True
                        break
                    except Exception:
                        # 캐시 연결 오류 시 락 획득 실패
                        break

            try:
                # 락 획득 후 마지막 요청 시간 조회 및 업데이트
                last_request_time = cache.get(KIS_LAST_REQUEST_TIME_KEY)
                current_time = time.time()

                if last_request_time:
                    elapsed = current_time - last_request_time
                    # 마지막 요청 이후 REQUEST_DELAY 시간이 지나지 않았으면 대기
                    if elapsed < REQUEST_DELAY:
                        wait_time = REQUEST_DELAY - elapsed
                        logger.debug(f"KIS API rate limit 대기: {wait_time:.3f}초")
                        time.sleep(wait_time)
                        current_time = time.time()

                # 현재 시간을 마지막 요청 시간으로 저장 (타임아웃 1초)
                try:
                    cache.set(KIS_LAST_REQUEST_TIME_KEY, current_time, timeout=1)
                except Exception:
                    # 캐시 저장 실패 시 무시
                    pass

            finally:
                # 락 해제 (항상 실행되도록 보장)
                if lock_acquired:
                    try:
                        cache.delete(KIS_RATE_LIMIT_LOCK_KEY)
                    except Exception:
                        # 캐시 삭제 실패 시 무시
                        pass
        except Exception as e:
            # 캐시 연결 오류 시 단순 딜레이로 fallback
            logger.debug(f"캐시 기반 rate limit 실패, 단순 딜레이 사용: {e}")
            time.sleep(REQUEST_DELAY)

    def get_stock_quote(self, stock_code: str) -> Optional[dict]:
        """
        주식 현재가 시세 조회

        Args:
            stock_code: 종목코드 (6자리)

        Returns:
            시세 정보 딕셔너리 또는 None
        """
        access_token = self._get_access_token()
        if not access_token:
            return None

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100",  # 주식현재가 시세 (모의투자)
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 주식, ETF, ETN
            "FID_INPUT_ISCD": stock_code,
        }

        try:
            # 분산 환경에서 전역 rate limit 준수
            self._wait_for_rate_limit()

            response = requests.get(url, headers=headers, params=params, timeout=10)

            # HTTP 상태 코드 확인
            if response.status_code == 500:
                # 500 에러는 서버 측 문제이므로 상세 로깅
                logger.error(
                    f"KIS 시세 조회 요청 실패 ({stock_code}): "
                    f"{response.status_code} Server Error: {response.reason} for url: {response.url}"
                )
                # 응답 본문이 있으면 로깅
                try:
                    error_body = response.text[:500]  # 최대 500자만
                    if error_body:
                        logger.debug(
                            f"KIS API 에러 응답 본문 ({stock_code}): {error_body}"
                        )
                except Exception as e:
                    logger.debug(
                        f"KIS API 에러 응답 본문 읽기 실패 ({stock_code}): {e}"
                    )
                return None

            response.raise_for_status()
            data = response.json()

            # 응답 코드 확인
            rt_cd = data.get("rt_cd")
            if rt_cd != "0":
                msg = data.get("msg1", "알 수 없는 오류")
                logger.warning(f"KIS 시세 조회 실패 ({stock_code}): {msg}")
                return None

            return data.get("output")

        except requests.RequestException as e:
            logger.error(f"KIS 시세 조회 요청 실패 ({stock_code}): {e}")
            return None

    def get_stock_quote_or_raise(self, stock_code: str) -> dict:
        """
        주식 현재가 시세 조회 (일시적 오류 시 예외 발생)

        Args:
            stock_code: 종목코드 (6자리)

        Returns:
            시세 정보 딕셔너리

        Raises:
            requests.RequestException: 네트워크 오류, 타임아웃 등 일시적 오류
            requests.HTTPError: HTTP 5xx 서버 오류
        """
        access_token = self._get_access_token()
        if not access_token:
            # 토큰 발급 실패는 일시적 오류로 간주하지 않음 (None 반환)
            return None

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100",  # 주식현재가 시세 (모의투자)
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 주식, ETF, ETN
            "FID_INPUT_ISCD": stock_code,
        }

        # 분산 환경에서 전역 rate limit 준수
        self._wait_for_rate_limit()

        response = requests.get(url, headers=headers, params=params, timeout=10)

        # HTTP 5xx 서버 오류는 일시적 오류로 간주하여 예외 발생
        if response.status_code >= 500:
            # 상세한 오류 정보 로깅
            logger.error(
                f"KIS 시세 조회 서버 오류 ({stock_code}): "
                f"{response.status_code} Server Error: {response.reason} for url: {response.url}"
            )
            # 응답 본문이 있으면 로깅 (디버깅용)
            try:
                error_body = response.text[:500]  # 최대 500자만
                if error_body:
                    logger.debug(
                        f"KIS API 서버 오류 응답 본문 ({stock_code}): {error_body}"
                    )
            except Exception as e:
                logger.debug(f"KIS API 오류 응답 본문 읽기 실패 ({stock_code}): {e}")
            response.raise_for_status()  # HTTPError 발생

        response.raise_for_status()
        data = response.json()

        # 응답 코드 확인
        rt_cd = data.get("rt_cd")
        if rt_cd != "0":
            msg = data.get("msg1", "알 수 없는 오류")
            logger.warning(f"KIS 시세 조회 실패 ({stock_code}): {msg}")
            # 비일시적 오류로 간주 (None 반환)
            return None

        return data.get("output")

    def get_market_amount(self, stock_code: str) -> Optional[int]:
        """
        시가총액 조회

        KIS API 응답 구조 (get_stock_quote):
        - output: 시세 정보 딕셔너리
        - hts_avls: HTS 시가총액 (억 단위, 문자열, 콤마 포함 가능)
        - stck_prpr: 현재가 (원 단위)
        - lstg_stcnt: 상장주식수 (주 단위)
        - 예: "500,000" → 500,000억원 → 50,000,000,000,000원

        검증 방법:
        1. hts_avls 필드 사용 (우선)
        2. 현재가 × 상장주식수로 계산하여 검증 (hts_avls가 없거나 검증 필요 시)

        Args:
            stock_code: 종목코드 (6자리)

        Returns:
            시가총액 (원 단위, BigInt) 또는 None
        """
        quote = self.get_stock_quote(stock_code)
        if not quote:
            logger.warning(f"KIS 시세 조회 실패: {stock_code}")
            return None

        # hts_avls: HTS 시가총액 (억 단위)
        # KIS API 공식 문서 기준: hts_avls는 억 단위로 제공됨
        hts_avls = quote.get("hts_avls")

        # 대체 계산을 위한 필드 확인
        stck_prpr = quote.get("stck_prpr")  # 현재가
        lstg_stcnt = quote.get("lstg_stcnt")  # 상장주식수

        # hts_avls 우선 사용
        if hts_avls:
            try:
                # 문자열에서 콤마 제거 후 정수 변환
                hts_avls_clean = str(hts_avls).replace(",", "").strip()
                if not hts_avls_clean:
                    logger.warning(f"시가총액 값이 비어있음: {stock_code}")
                    return None

                # 억 단위 → 원 단위 변환
                # 1억 = 100,000,000원
                market_amount = int(hts_avls_clean) * 100_000_000

                # 검증: 현재가 × 상장주식수로 계산하여 비교 (가능한 경우)
                if stck_prpr and lstg_stcnt:
                    try:
                        current_price = int(str(stck_prpr).replace(",", "").strip())
                        shares_outstanding = int(
                            str(lstg_stcnt).replace(",", "").strip()
                        )
                        calculated_market_cap = current_price * shares_outstanding

                        # 오차율 계산 (5% 이내면 정상으로 간주)
                        diff = abs(market_amount - calculated_market_cap)
                        diff_percent = (
                            (diff / calculated_market_cap * 100)
                            if calculated_market_cap > 0
                            else 0
                        )

                        if diff_percent > 5:
                            logger.warning(
                                f"시가총액 검증 경고 ({stock_code}): "
                                f"hts_avls 기반={market_amount:,}원, "
                                f"계산값(현재가×상장주식수)={calculated_market_cap:,}원, "
                                f"오차율={diff_percent:.2f}%"
                            )
                        else:
                            logger.debug(
                                f"시가총액 검증 통과 ({stock_code}): "
                                f"hts_avls={market_amount:,}원, 계산값={calculated_market_cap:,}원, "
                                f"오차율={diff_percent:.2f}%"
                            )
                    except (ValueError, TypeError) as e:
                        logger.debug(
                            f"시가총액 검증 계산 실패 ({stock_code}): {e} "
                            f"(stck_prpr={stck_prpr}, lstg_stcnt={lstg_stcnt})"
                        )

                logger.debug(
                    f"시가총액 조회 완료: {stock_code} → {hts_avls}억원 = {market_amount:,}원"
                )
                return market_amount
            except (ValueError, TypeError, AttributeError) as e:
                logger.error(
                    f"시가총액 파싱 실패 ({stock_code}): hts_avls={hts_avls}, 타입={type(hts_avls)}, 오류: {e}"
                )
                # 파싱 실패 시 대체 계산 시도
                pass

        # hts_avls가 없거나 파싱 실패 시 대체 계산: 현재가 × 상장주식수
        if stck_prpr and lstg_stcnt:
            try:
                current_price = int(str(stck_prpr).replace(",", "").strip())
                shares_outstanding = int(str(lstg_stcnt).replace(",", "").strip())
                market_amount = current_price * shares_outstanding

                logger.info(
                    f"시가총액 대체 계산 ({stock_code}): "
                    f"현재가({current_price:,}원) × 상장주식수({shares_outstanding:,}주) = {market_amount:,}원"
                )
                return market_amount
            except (ValueError, TypeError) as e:
                logger.error(
                    f"시가총액 대체 계산 실패 ({stock_code}): "
                    f"stck_prpr={stck_prpr}, lstg_stcnt={lstg_stcnt}, 오류: {e}"
                )

        # 모든 방법 실패
        logger.warning(
            f"시가총액 필드(hts_avls) 없음: {stock_code}, "
            f"사용 가능한 필드: {list(quote.keys())}"
        )
        return None


# 싱글톤 인스턴스
_client: Optional[KISQuoteClient] = None


def get_kis_quote_client() -> KISQuoteClient:
    """KISQuoteClient 싱글톤 인스턴스 반환"""
    global _client
    if _client is None:
        _client = KISQuoteClient()
    return _client


def get_market_amount(stock_code: str) -> Optional[int]:
    """
    시가총액 조회 (편의 함수)

    Args:
        stock_code: 종목코드 (6자리)

    Returns:
        시가총액 (원 단위) 또는 None
    """
    client = get_kis_quote_client()
    return client.get_market_amount(stock_code)
