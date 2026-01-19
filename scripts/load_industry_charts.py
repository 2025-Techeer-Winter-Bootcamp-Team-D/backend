"""
산업 지수 차트 초기 로드 스크립트
1년치 데이터를 조회하여 각 차트 타입별로 DB에 저장합니다.

실행: python scripts/load_industry_charts.py
"""
import os
import sys
import django
from pathlib import Path

# 스크립트 파일의 위치를 기준으로 프로젝트 루트 계산
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from industries.models import Industry, IndustryChart1d, IndustryChart3d, IndustryChart1w, IndustryChart2w
from industries.services.kis_index_service import KISIndexService
from django.db import transaction
from datetime import datetime


def load_industry_charts():
    """산업별 1년치 차트 데이터 로드"""
    
    service = KISIndexService()
    
    # KIS 업종코드가 등록된 산업만
    industries = Industry.objects.filter(is_deleted=False).exclude(induty_code__isnull=True)
    
    print("=" * 60)
    print("산업 지수 차트 초기 로드 시작")
    print("=" * 60)
    
    total_industries = industries.count()
    success_count = 0
    error_count = 0
    
    for idx, industry in enumerate(industries, 1):
        print(f"\n[{idx}/{total_industries}] {industry.name} ({industry.induty_code}) 처리 중...")
        
        try:
            with transaction.atomic():
                # 1년치 원본 데이터 수집
                raw_data = service.fetch_1y_history_raw(industry.induty_code)
                
                # 1년치 차트 데이터 생성
                charts = service.get_industry_charts_1y(raw_data)
                
                # 기존 데이터 삭제 (갱신용)
                IndustryChart1d.objects.filter(industry=industry).delete()
                IndustryChart3d.objects.filter(industry=industry).delete()
                IndustryChart1w.objects.filter(industry=industry).delete()
                IndustryChart2w.objects.filter(industry=industry).delete()
                
                # 1. 일봉 (IndustryChart1d) - 1개월
                print(f"  └─ 일봉: {len(charts['chart_1d'])}개 저장 중...", end=" ")
                chart_1d_objs = [
                    IndustryChart1d(
                        industry=industry,
                        base_date=candle['date'] if isinstance(candle, dict) else candle.date,
                        open=candle['open'] if isinstance(candle, dict) else candle.open,
                        high=candle['high'] if isinstance(candle, dict) else candle.high,
                        low=candle['low'] if isinstance(candle, dict) else candle.low,
                        close=candle['close'] if isinstance(candle, dict) else candle.close,
                        change_value=candle.get('change_value', 0) if isinstance(candle, dict) else candle.change_value,
                        change_rate=candle.get('change_rate', 0) if isinstance(candle, dict) else candle.change_rate,
                    )
                    for candle in charts['chart_1d']
                ]
                IndustryChart1d.objects.bulk_create(chart_1d_objs, batch_size=100)
                print("✅")
                
                # 2. 3일봉 (IndustryChart3d) - 3개월
                print(f"  └─ 3일봉: {len(charts['chart_3d'])}개 저장 중...", end=" ")
                chart_3d_objs = [
                    IndustryChart3d(
                        industry=industry,
                        base_date=candle.date,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        change_value=candle.change_value,
                        change_rate=candle.change_rate,
                    )
                    for candle in charts['chart_3d']
                ]
                IndustryChart3d.objects.bulk_create(chart_3d_objs, batch_size=100)
                print("✅")
                
                # 3. 주봉 (IndustryChart1w) - 6개월
                print(f"  └─ 주봉: {len(charts['chart_1w'])}개 저장 중...", end=" ")
                chart_1w_objs = [
                    IndustryChart1w(
                        industry=industry,
                        base_date=candle.date,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        change_value=candle.change_value,
                        change_rate=candle.change_rate,
                    )
                    for candle in charts['chart_1w']
                ]
                IndustryChart1w.objects.bulk_create(chart_1w_objs, batch_size=100)
                print("✅")
                
                # 4. 2주봉 (IndustryChart2w) - 1년
                print(f"  └─ 2주봉: {len(charts['chart_2w'])}개 저장 중...", end=" ")
                chart_2w_objs = [
                    IndustryChart2w(
                        industry=industry,
                        base_date=candle.date,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        change_value=candle.change_value,
                        change_rate=candle.change_rate,
                    )
                    for candle in charts['chart_2w']
                ]
                IndustryChart2w.objects.bulk_create(chart_2w_objs, batch_size=100)
                print("✅")
                
                success_count += 1
                print(f"✅ {industry.name} 완료")
        
        except Exception as e:
            error_count += 1
            print(f"\n {industry.name} 처리 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("초기 로드 완료")
    print(f"성공: {success_count}/{total_industries}")
    print(f"실패: {error_count}/{total_industries}")
    print("=" * 60)


if __name__ == "__main__":
    load_industry_charts()
