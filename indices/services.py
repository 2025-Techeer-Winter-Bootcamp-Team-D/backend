import os
import requests
from datetime import datetime

class KISIndexService:
    def __init__(self):
        self.app_key = os.getenv("KIS_APP_KEY")
        self.app_secret = os.getenv("KIS_APP_SECRET")
        #self.base_url = "https://openapi.koreainvestment.com:9443" 실제 계좌용
        self.base_url = "https://openapivts.koreainvestment.com:29443" # 모의계좌 (잠깐 사용)
        self._token = None  # [추가] 토큰 저장용 변수

    def get_token(self):
        # 이미 토큰이 있으면 새로 받지 않고 그대로 반환
        if self._token:
            return self._token
            
        url = f"{self.base_url}/oauth2/tokenP"
        res = requests.post(url, json={
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        })
        
        self._token = res.json().get("access_token")
        print(">>> [알림] KIS 새로운 접근 토큰 발급됨")
        return self._token

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
        
        response = requests.get(url, headers=headers, params=params)
        return response.json().get('output2', [])