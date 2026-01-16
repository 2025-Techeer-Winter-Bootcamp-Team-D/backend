import os
import requests
from datetime import datetime
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class KISIndexService:
    def __init__(self):
        self.app_key = os.getenv("KIS_APP_KEY")
        self.app_secret = os.getenv("KIS_APP_SECRET")
        #self.base_url = "https://openapi.koreainvestment.com:9443" 실제 계좌용
        self.base_url = "https://openapivts.koreainvestment.com:29443" # 모의계좌 (잠깐 사용)
        self._token = None  # [추가] 토큰 저장용 변수

    def get_token(self):
        # [수정] 실행 중에는 저장된 토큰을 쓰고, 없거나 에러 날 때만 새로 받음
        # 이렇게 해야 '연속 토큰 발급'으로 인한 403 에러를 피할 수 있습니다.
        if self._token:
            return self._token
            
        url = f"{self.base_url}/oauth2/tokenP"
        try:
            res = requests.post(url, json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret
            }, timeout=10)
            res.raise_for_status()
            self._token = res.json().get("access_token")
            print(">>> [알림] KIS 새로운 접근 토큰 발급됨")
            return self._token
        except Exception as e:
            logger.error(f"KIS 토큰 발급 실패: {e}")
            raise

    def fetch_index_data(self, iscd, start_date, end_date):
        # 여기서는 get_token()을 불러도 위에서 캐싱하니까 안전합니다.
        token = self.get_token()
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKUP03500100",
            "custtype": "P",
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": iscd,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0"
        }
        
        try:
            # [수정] 타임아웃 추가 및 에러 처리
            response = requests.get(url, headers=headers, params=params, timeout=60)
            response.raise_for_status()
            return response.json().get('output2', [])
        except Exception as e:
            logger.error(f"지수 데이터 조회 실패 ({iscd}): {e}")
            return [] 