import time
from datetime import datetime, timedelta
from celery import shared_task
from indices.services import KISIndexService
from indices.models import MarketIndex

# 시장 정보 정의 (코스피, 코스닥)
MARKETS = [
    ('0001', 'KOSPI'),
    ('1001', 'KOSDAQ')
]

@shared_task
def initialize_indices_1year():
    """
    [배포 후 최초 1회 실행용] 
    CMD/Shell에서 수동 실행하여 DB에 1년치 데이터를 꽉 채웁니다.
    """
    service = KISIndexService()
    today = datetime.now()
    
    print("🚀 [초기화] 1년치 지수 수집 시작...")

    for iscd, market_name in MARKETS:
        print(f"==== [{market_name}] 집중 수집 시작 ====")
        
        # 50일씩 8번 쪼개서 약 400일치 확인 (주말 제외 1년치 확보용)
        for i in range(8):
            current_end = today - timedelta(days=i*50)
            current_start = current_end - timedelta(days=49)
            
            start_str = current_start.strftime('%Y%m%d')
            end_str = current_end.strftime('%Y%m%d')
            
            try:
                raw_data = service.fetch_index_data(iscd, start_str, end_str)
                if not raw_data:
                    continue

                for item in raw_data:
                    dt = datetime.strptime(item['stck_bsop_date'], '%Y%m%d').date()
                    MarketIndex.objects.update_or_create(
                        idx_date=dt,
                        market_type=market_name,
                        defaults={
                            'value': float(item.get('bstp_nmix_prpr', 0)),
                            'volume': int(item.get('acml_vol') or 0),
                            'amount': int(item.get('acml_tr_pbmn') or 0),
                        }
                    )
                
                print(f"[{market_name}] {i+1}회차 완료 ({start_str} ~ {end_str})")
                time.sleep(2) # KIS API 부하 방지
                
            except Exception as e:
                print(f"!!! [{market_name}] 에러 발생: {e}")
                continue

    print("✅ [초기화] 모든 시장 1년치 수집 종료")


@shared_task
def sync_indices_daily():
    """
    [매일 자동 실행용] 
    장 마감 후 Celery Beat가 호출하여 '오늘 하루치'만 업데이트합니다.
    """
    service = KISIndexService()
    today_str = datetime.now().strftime('%Y%m%d')
    
    print(f"📅 [데일리] {today_str} 지수 업데이트 시작")

    for iscd, market_name in MARKETS:
        try:
            raw_data = service.fetch_index_data(iscd, today_str, today_str)
            
            if raw_data:
                item = raw_data[0] # 오늘 데이터
                dt = datetime.strptime(item['stck_bsop_date'], '%Y%m%d').date()
                
                MarketIndex.objects.update_or_create(
                    idx_date=dt,
                    market_type=market_name,
                    defaults={
                        'value': float(item.get('bstp_nmix_prpr', 0)),
                        'volume': int(item.get('acml_vol') or 0),
                        'amount': int(item.get('acml_tr_pbmn') or 0),
                    }
                )
                print(f"✅ {market_name} 업데이트 완료 ({dt})")
            
            time.sleep(2) # 동시성 충돌 방지 (2초 휴식)
            
        except Exception as e:
            print(f"❌ {market_name} 업데이트 실패: {e}")

    print("🏁 [데일리] 업데이트 작업 종료")