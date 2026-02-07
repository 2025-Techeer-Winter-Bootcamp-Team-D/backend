import requests
import json
import time
import logging
from django.conf import settings
from django.core.cache import cache
from datetime import datetime
from .candlestick_converter import CandlestickConverter
from datetime import timedelta

logger = logging.getLogger(__name__)

# Rate Limiting: 요청 간 최소 딜레이 (초)
# KIS API는 초당 2회로 제한되어 있으므로 최소 500ms 딜레이 필요
# 안전 마진을 두어 600ms로 설정 (초당 약 1.67회)
REQUEST_DELAY = 0.6  # 600ms 딜레이 (초당 2회 제한 준수)

# HTTP 요청 타임아웃 (초)
REQUEST_TIMEOUT = 10

# 분산 락 및 마지막 요청 시간 관리용 Redis 키
KIS_RATE_LIMIT_LOCK_KEY = "kis_api_rate_limit_lock"
KIS_LAST_REQUEST_TIME_KEY = "kis_api_last_request_time"


class KISIndexService:
    def __init__(self):
        # 모든 주소를 '모의투자'용으로 통일합니다.
        self.base_url = "https://openapivts.koreainvestment.com:29443"
        self.app_key = settings.KIS_APP_KEY
        self.app_secret = settings.KIS_APP_SECRET
        self.token = None
        self.converter = CandlestickConverter()
        # self.token = None 대신 캐시에서 먼저 찾아봅니다.
        self.token = cache.get("kis_access_token")

    def get_access_token(self):
        # 1. 인스턴스 변수에 이미 있다면 즉시 반환
        if self.token:
            return self.token

        # 2. [중요] API 호출 직전, 다른 워커가 방금 저장했는지 캐시 다시 확인 (Double Check)
        self.token = cache.get("kis_access_token")
        if self.token:
            return self.token

        # 3. [분산 락] 여러 워커가 동시에 API를 쏘지 못하게 '락'을 겁니다.
        # cache.add는 키가 없을 때만 True를 반환하므로 원자적(Atomic)입니다.
        lock_acquired = cache.add("kis_token_lock", "true", timeout=10)

        if not lock_acquired:
            # 락을 얻지 못했다면 다른 워커가 이미 발급 중인 것입니다.
            # 잠시 대기 후 캐시에서 가져옵니다.
            time.sleep(2)
            self.token = cache.get("kis_access_token")
            if self.token:
                return self.token
            raise Exception(
                "다른 프로세스에서 토큰을 발급 중입니다. 잠시 후 시도하세요."
            )

        try:
            # 4. 실제 API 호출
            path = "/oauth2/tokenP"
            url = f"{self.base_url}{path}"
            data = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            }

            try:
                res = requests.post(url, data=json.dumps(data), timeout=REQUEST_TIMEOUT)
            except requests.exceptions.Timeout:
                logger.error("KIS 토큰 발급 요청 타임아웃")
                raise Exception("KIS 토큰 발급 요청 타임아웃")
            except requests.exceptions.RequestException as e:
                logger.error(f"KIS 토큰 발급 요청 실패: {e}")
                raise Exception(f"KIS 토큰 발급 요청 실패: {e}")

            if res.status_code == 200:
                new_token = res.json().get("access_token")
                # 캐시에 저장 (12시간 유효)
                cache.set("kis_access_token", new_token, 60 * 60 * 12)
                self.token = new_token
                return self.token
            else:
                # 에러 로그 상세 출력
                error_msg = res.json().get("msg1", res.text)
                raise Exception(f"KIS 토큰 발급 실패: {error_msg}")
        finally:
            # 5. 작업 완료 후 락 해제
            cache.delete("kis_token_lock")

    def _wait_for_rate_limit(self):
        """
        분산 환경에서 KIS API rate limit 준수를 위한 전역 딜레이 관리

        Redis 분산 락을 사용하여 동시성 문제를 해결하고,
        마지막 요청 시간을 공유하여 초당 2회 제한을 준수합니다.
        """
        lock_ttl = REQUEST_DELAY + 0.1  # 초 단위
        max_retries = 10
        retry_backoff = 0.01  # 10ms
        max_wait_time = 30  # 최대 대기 시간 (초) - 무한 대기 방지

        start_time = time.time()

        # 분산 락 획득 시도
        lock_acquired = False
        for attempt in range(max_retries):
            lock_acquired = cache.add(
                KIS_RATE_LIMIT_LOCK_KEY, "locked", timeout=lock_ttl
            )
            if lock_acquired:
                break

            if attempt < max_retries - 1:
                time.sleep(retry_backoff)
            else:
                # 최종 시도 실패 시 락이 해제될 때까지 대기 (타임아웃 포함)
                logger.debug("KIS rate limit 락 획득 대기 중...")
                while True:
                    elapsed = time.time() - start_time
                    if elapsed > max_wait_time:
                        logger.warning(
                            f"KIS rate limit 락 획득 타임아웃 ({max_wait_time}초 초과). "
                            "강제로 진행합니다."
                        )
                        break

                    if cache.add(KIS_RATE_LIMIT_LOCK_KEY, "locked", timeout=lock_ttl):
                        lock_acquired = True
                        break

                    time.sleep(retry_backoff)
                break

        try:
            # 락 획득 후 마지막 요청 시간 조회 및 업데이트
            last_request_time = cache.get(KIS_LAST_REQUEST_TIME_KEY)
            current_time = time.time()

            if last_request_time:
                elapsed = current_time - last_request_time
                if elapsed < REQUEST_DELAY:
                    # 아직 대기 시간이 지나지 않았으면 남은 시간만큼 대기
                    sleep_time = REQUEST_DELAY - elapsed
                    logger.debug(f"KIS API rate limit 대기: {sleep_time:.3f}초")
                    time.sleep(sleep_time)

            # 마지막 요청 시간 업데이트
            cache.set(KIS_LAST_REQUEST_TIME_KEY, time.time(), timeout=60)
        finally:
            # 락 해제
            if lock_acquired:
                cache.delete(KIS_RATE_LIMIT_LOCK_KEY)

    def fetch_index_history(self, industry_code, start_date=None, end_date=None):
        """
        KIS API를 호출하여 지수 일봉 데이터를 가져옵니다.
        TR_ID: FHKUP03500100 (국내지수 기간별 시세 조회)
        """
        if not self.token:
            self.get_access_token()

        # Rate limiting 적용 (초당 2회 제한 준수)
        self._wait_for_rate_limit()

        industry_code = industry_code.strip().upper()

        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
        url = f"{self.base_url}{path}"

        # KIS 지수 전용 TR_ID 및 헤더 설정
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKUP03500100",  # 지수 조회용 TR_ID
        }

        # API 필수 파라미터
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",  # 업종(U)
            "FID_INPUT_ISCD": industry_code,  # 업종코드 (예: 0001)
            "FID_PERIOD_DIV_CODE": "D",  # 일봉(D)
            "FID_ORG_ADJ_PRC": "0",  # 수정주가 반영 여부 (0: 반영)
        }

        # 날짜 범위 지정 (있을 경우)
        if start_date:
            params["FID_INPUT_DATE_1"] = start_date
        if end_date:
            params["FID_INPUT_DATE_2"] = end_date

        try:
            res = requests.get(
                url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.Timeout:
            logger.error(f"KIS API 호출 타임아웃: {industry_code}")
            raise Exception(f"KIS API 호출 타임아웃: {industry_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"KIS API 호출 실패: {industry_code} - {e}")
            raise Exception(f"KIS API 호출 실패: {industry_code} - {e}")

        if res.status_code == 200:
            res_json = res.json()
            output2 = res_json.get("output2", [])

            # [수정] 데이터가 실제로 없을 때만 "데이터 없음" 로그를 찍도록 변경
            if not output2:
                print(
                    f"❓ {industry_code} 응답 성공했으나 실제 데이터 0건: {res_json.get('msg1')}"
                )

            return output2

        else:
            # TPS 제한(EGW00201) 등 에러 발생 시 상세 출력
            print(f"❌ KIS API 호출 실패 ({res.status_code}): {res.text}")
            return []

    def fetch_1y_history_raw(self, industry_code):
        """100일씩 끊어서 호출하여 1년치(300일 이상) 원본 데이터를 수집합니다."""
        logger.info(f"📡 {industry_code} 1년치 데이터 수집 시작")
        all_raw_data = []
        target_end_date = datetime.now()

        for batch_num in range(5):  # 100일씩 5번 호출
            end_str = target_end_date.strftime("%Y%m%d")
            start_str = (target_end_date - timedelta(days=100)).strftime("%Y%m%d")

            logger.debug(
                f"📡 {industry_code} 배치 {batch_num + 1}/5: {start_str} ~ {end_str}"
            )
            raw = self.fetch_index_history(industry_code, start_str, end_str)
            if not raw:
                logger.warning(
                    f"⚠️ {industry_code} 배치 {batch_num + 1}/5: 데이터 없음, 수집 중단"
                )
                break
            all_raw_data.extend(raw)
            logger.debug(
                f"✅ {industry_code} 배치 {batch_num + 1}/5: {len(raw)}건 수집 완료"
            )

            # 다음 구간을 위해 날짜 조정
            last_date_str = raw[-1]["stck_bsop_date"]
            target_end_date = datetime.strptime(last_date_str, "%Y%m%d") - timedelta(
                days=1
            )
            # Rate limiting은 fetch_index_history 내부에서 처리되므로 추가 대기 불필요

        logger.info(
            f"✅ {industry_code} 1년치 데이터 수집 완료: 총 {len(all_raw_data)}건"
        )
        return all_raw_data

    def save_charts_to_db(self, industry, charts_dict, delete_from_date=None):
        """가공된 차트 데이터를 4개의 테이블에 분산 저장합니다."""
        from industries.models import (
            IndustryChart1d,
            IndustryChart3d,
            IndustryChart1w,
            IndustryChart2w,
        )

        model_map = {
            "chart_1d": IndustryChart1d,
            "chart_3d": IndustryChart3d,
            "chart_1w": IndustryChart1w,
            "chart_2w": IndustryChart2w,
        }

        for key, model in model_map.items():
            data_list = charts_dict.get(key, [])
            if not data_list:
                continue

            # '진행 중인 봉' 문제를 해결하기 위해 특정 날짜 이후 삭제
            if delete_from_date:
                model.objects.filter(
                    industry=industry, base_date__gte=delete_from_date
                ).delete()

            for c in data_list:
                c_date = c.date if hasattr(c, "date") else c["date"]
                model.objects.update_or_create(
                    industry=industry,
                    base_date=c_date,
                    defaults={
                        "open": c.open if hasattr(c, "open") else c["open"],
                        "high": c.high if hasattr(c, "high") else c["high"],
                        "low": c.low if hasattr(c, "low") else c["low"],
                        "close": c.close if hasattr(c, "close") else c["close"],
                        "change_value": (
                            c.change_value
                            if hasattr(c, "change_value")
                            else c.get("change_value", 0)
                        ),
                        "change_rate": (
                            c.change_rate
                            if hasattr(c, "change_rate")
                            else c.get("change_rate", 0)
                        ),
                    },
                )

    def _normalize_daily_candles(self, raw_data: list) -> list:
        """
        KIS API 응답 데이터를 표준 형식으로 변환

        Args:
            raw_data: KIS API 응답 (output2)

        Returns:
            표준 캔들 데이터 리스트
        """
        normalized = []

        for item in raw_data:
            # 날짜 형식 변환: YYYYMMDD -> YYYY-MM-DD
            date_str = item.get("stck_bsop_date", "")
            if len(date_str) == 8:
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            else:
                formatted_date = date_str

            normalized.append(
                {
                    "date": formatted_date,
                    "open": float(item.get("bstp_nmix_oprc", 0)),
                    "high": float(item.get("bstp_nmix_hgpr", 0)),
                    "low": float(item.get("bstp_nmix_lwpr", 0)),
                    "close": float(item.get("bstp_nmix_prpr", 0)),
                    "change_value": float(item.get("bstp_nmix_prdy_vrss", 0)),
                    "change_rate": float(item.get("bstp_nmix_prdy_ctrt", 0)),
                }
            )

        return normalized

    def get_industry_charts_1y(self, raw_data: list) -> dict:
        """받아온 원본 데이터를 1d, 3d, 1w, 2w 주기로 변환합니다."""
        if not raw_data:
            return {"chart_1d": [], "chart_3d": [], "chart_1w": [], "chart_2w": []}

        daily_candles = self._normalize_daily_candles(raw_data)
        daily_candles.sort(key=lambda x: x["date"])  # 과거순 정렬

        for i in range(1, len(daily_candles)):
            prev_close = daily_candles[i - 1]["close"]
            curr_close = daily_candles[i]["close"]

            # 변동값 계산
            change_value = curr_close - prev_close
            # 변동률 계산 공식:
            # Change Rate = ((Curr - Prev) / Prev) * 100
            change_rate = (change_value / prev_close) * 100 if prev_close != 0 else 0

            daily_candles[i]["change_value"] = round(change_value, 2)
            daily_candles[i]["change_rate"] = round(change_rate, 2)

        return {
            "chart_1d": daily_candles,
            "chart_3d": self.converter.convert_daily_to_3d(daily_candles),
            "chart_1w": self.converter.convert_daily_to_1w(daily_candles),
            "chart_2w": self.converter.convert_daily_to_2w(daily_candles),
        }
