import requests
import json
import time
from django.conf import settings
from django.core.cache import cache
from datetime import datetime
from .candlestick_converter import CandlestickConverter
from datetime import timedelta

class KISIndexService:
    def __init__(self):
        # 모든 주소를 '모의투자'용으로 통일합니다.
        self.base_url = "https://openapivts.koreainvestment.com:29443" 
        self.app_key = settings.KIS_APP_KEY
        self.app_secret = settings.KIS_APP_SECRET
        self.token = None
        self.converter = CandlestickConverter()
        # self.token = None 대신 캐시에서 먼저 찾아봅니다.
        self.token = cache.get('kis_access_token')
        
    def get_access_token(self):
        # 1. 인스턴스 변수에 이미 있다면 즉시 반환
        if self.token:
            return self.token

        # 2. [중요] API 호출 직전, 다른 워커가 방금 저장했는지 캐시 다시 확인 (Double Check)
        self.token = cache.get('kis_access_token')
        if self.token:
            return self.token

        # 3. [분산 락] 여러 워커가 동시에 API를 쏘지 못하게 '락'을 겁니다.
        # cache.add는 키가 없을 때만 True를 반환하므로 원자적(Atomic)입니다.
        lock_acquired = cache.add('kis_token_lock', 'true', timeout=10)
        
        if not lock_acquired:
            # 락을 얻지 못했다면 다른 워커가 이미 발급 중인 것입니다.
            # 잠시 대기 후 캐시에서 가져옵니다.
            time.sleep(2) 
            self.token = cache.get('kis_access_token')
            if self.token: return self.token
            raise Exception("다른 프로세스에서 토큰을 발급 중입니다. 잠시 후 시도하세요.")

        try:
            # 4. 실제 API 호출
            path = "/oauth2/tokenP"
            url = f"{self.base_url}{path}"
            data = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret
            }
            
            res = requests.post(url, data=json.dumps(data))
            
            if res.status_code == 200:
                new_token = res.json().get('access_token')
                # 캐시에 저장 (12시간 유효)
                cache.set('kis_access_token', new_token, 60 * 60 * 12)
                self.token = new_token
                return self.token
            else:
                # 에러 로그 상세 출력
                error_msg = res.json().get('msg1', res.text)
                raise Exception(f"KIS 토큰 발급 실패: {error_msg}")
        finally:
            # 5. 작업 완료 후 락 해제
            cache.delete('kis_token_lock')
            

    def fetch_index_history(self, industry_code, start_date=None, end_date=None):
        """
        KIS API를 호출하여 지수 일봉 데이터를 가져옵니다.
        TR_ID: FHKUP03500100 (국내지수 기간별 시세 조회)
        """
        if not self.token:
            self.get_access_token()

        industry_code = industry_code.strip().upper()
        
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
        url = f"{self.base_url}{path}"
        
        # KIS 지수 전용 TR_ID 및 헤더 설정
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKUP03500100"  # 지수 조회용 TR_ID
        }
        
        # API 필수 파라미터
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",  # 업종(U)
            "FID_INPUT_ISCD": industry_code, # 업종코드 (예: 0001)
            "FID_PERIOD_DIV_CODE": "D",     # 일봉(D)
            "FID_ORG_ADJ_PRC": "0",         # 수정주가 반영 여부 (0: 반영)
        }
        
        # 날짜 범위 지정 (있을 경우)
        if start_date: params["FID_INPUT_DATE_1"] = start_date
        if end_date: params["FID_INPUT_DATE_2"] = end_date
        
        res = requests.get(url, headers=headers, params=params)
        
        if res.status_code == 200:
            res_json = res.json()
            output2 = res_json.get('output2', [])
            
            # [수정] 데이터가 실제로 없을 때만 "데이터 없음" 로그를 찍도록 변경
            if not output2:
                print(f"❓ {industry_code} 응답 성공했으나 실제 데이터 0건: {res_json.get('msg1')}")
            
            return output2
        
        else:
            # TPS 제한(EGW00201) 등 에러 발생 시 상세 출력
            print(f"❌ KIS API 호출 실패 ({res.status_code}): {res.text}")
            return []
 
        
    def fetch_1y_history_raw(self, industry_code):
        """100일씩 끊어서 호출하여 1년치(300일 이상) 원본 데이터를 수집합니다."""
        all_raw_data = []
        target_end_date = datetime.now()

        for _ in range(5): # 100일씩 3번 호출
            end_str = target_end_date.strftime('%Y%m%d')
            start_str = (target_end_date - timedelta(days=100)).strftime('%Y%m%d')
            
            raw = self.fetch_index_history(industry_code, start_str, end_str)
            if not raw: break
            all_raw_data.extend(raw)
            
            # 다음 구간을 위해 날짜 조정
            last_date_str = raw[-1]['stck_bsop_date']
            target_end_date = datetime.strptime(last_date_str, '%Y%m%d') - timedelta(days=1)
            time.sleep(0.2)  # API 호출 간 약간의 딜레이 추가

        return all_raw_data

    def save_charts_to_db(self, industry, charts_dict, delete_from_date=None):
        """가공된 차트 데이터를 4개의 테이블에 분산 저장합니다."""
        from industries.models import IndustryChart1d, IndustryChart3d, IndustryChart1w, IndustryChart2w
        
        model_map = {
            'chart_1d': IndustryChart1d, 'chart_3d': IndustryChart3d,
            'chart_1w': IndustryChart1w, 'chart_2w': IndustryChart2w
        }

        for key, model in model_map.items():
            data_list = charts_dict.get(key, [])
            if not data_list: continue

            # '진행 중인 봉' 문제를 해결하기 위해 특정 날짜 이후 삭제
            if delete_from_date:
                model.objects.filter(industry=industry, base_date__gte=delete_from_date).delete()

            for c in data_list:
                c_date = c.date if hasattr(c, 'date') else c['date']
                model.objects.update_or_create(
                    industry=industry, base_date=c_date,
                    defaults={
                        'open': c.open if hasattr(c, 'open') else c['open'],
                        'high': c.high if hasattr(c, 'high') else c['high'],
                        'low': c.low if hasattr(c, 'low') else c['low'],
                        'close': c.close if hasattr(c, 'close') else c['close'],
                        'change_value': c.change_value if hasattr(c, 'change_value') else c.get('change_value', 0),
                        'change_rate': c.change_rate if hasattr(c, 'change_rate') else c.get('change_rate', 0),
                    }
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
            date_str = item.get('stck_bsop_date', '')
            if len(date_str) == 8:
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            else:
                formatted_date = date_str
            
            normalized.append({
                'date': formatted_date,
                'open': float(item.get('bstp_nmix_oprc', 0)),
                'high': float(item.get('bstp_nmix_hgpr', 0)),
                'low': float(item.get('bstp_nmix_lwpr', 0)),
                'close': float(item.get('bstp_nmix_prpr', 0)),
                'change_value': float(item.get('bstp_nmix_prdy_vrss', 0)),
                'change_rate': float(item.get('bstp_nmix_prdy_ctrt', 0)),
            })
        
        return normalized
    
    def get_industry_charts_1y(self, raw_data: list) -> dict:
        """받아온 원본 데이터를 1d, 3d, 1w, 2w 주기로 변환합니다."""
        if not raw_data:
            return {'chart_1d': [], 'chart_3d': [], 'chart_1w': [], 'chart_2w': []}

        daily_candles = self._normalize_daily_candles(raw_data)
        daily_candles.sort(key=lambda x: x['date']) # 과거순 정렬
        
        for i in range(1, len(daily_candles)):
            prev_close = daily_candles[i-1]['close']
            curr_close = daily_candles[i]['close']
            
            # 변동값 계산
            change_value = curr_close - prev_close
            # 변동률 계산 공식: $$\text{change\_rate} = \frac{\text{curr\_close} - \text{prev\_close}}{\text{prev\_close}} \times 100$$
            change_rate = (change_value / prev_close) * 100 if prev_close != 0 else 0
            
            daily_candles[i]['change_value'] = round(change_value, 2)
            daily_candles[i]['change_rate'] = round(change_rate, 2)
            
        return {
            'chart_1d': daily_candles,
            'chart_3d': self.converter.convert_daily_to_3d(daily_candles),
            'chart_1w': self.converter.convert_daily_to_1w(daily_candles),
            'chart_2w': self.converter.convert_daily_to_2w(daily_candles),
        }
        
    