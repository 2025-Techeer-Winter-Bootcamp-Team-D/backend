"""
캔들 데이터 변환 유틸리티
일봉 데이터를 다양한 주기(3일봉, 주봉, 2주봉)로 변환합니다.
"""
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Candle:
    """단일 캔들 데이터"""
    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    change_value: Optional[float] = None
    change_rate: Optional[float] = None


class CandlestickConverter:
    """캔들 데이터 변환기"""
    
    @staticmethod
    def convert_daily_to_3d(candles: List[Dict]) -> List[Candle]:
        """
        일봉 데이터를 3일봉으로 변환

        Args:
            candles: [{"date": "2025-01-15", "open": 100, "high": 110, "low": 90, "close": 105}, ...]

        Returns:
            3일봉 캔들 리스트
        """
        if not candles:
            return []

        result = []
        i = 0

        while i < len(candles):
            # 3개의 캔들 또는 남은 캔들을 그룹화
            group = candles[i:i+3]

            if not group:
                break

            # 그룹의 시가(첫 번째), 종가(마지막)
            open_price = float(group[0]['open'])
            close_price = float(group[-1]['close'])

            # 그룹의 고가와 저가
            high_price = max(float(c['high']) for c in group)
            low_price = min(float(c['low']) for c in group)

            # 기준 날짜는 마지막 일자
            base_date = group[-1]['date']

            # 변동값은 변환 후 재계산하므로 일단 0으로 설정
            result.append(Candle(
                date=base_date,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                change_value=0,
                change_rate=0
            ))

            i += 3

        # 변환된 캔들들의 변동값 재계산
        CandlestickConverter._recalculate_changes(result)

        return result
    
    @staticmethod
    def convert_daily_to_1w(candles: List[Dict]) -> List[Candle]:
        """
        일봉 데이터를 주봉으로 변환 (월-금)

        Args:
            candles: 일봉 캔들 리스트

        Returns:
            주봉 캔들 리스트
        """
        if not candles:
            return []

        result = []
        week_group = []

        for candle in candles:
            date_obj = datetime.strptime(candle['date'], '%Y-%m-%d')

            # 월요일(0)부터 시작하는 경우 새 주 시작
            if date_obj.weekday() == 0 and week_group:
                # 이전 주의 캔들 처리
                result.append(CandlestickConverter._create_candle_from_group(week_group))
                week_group = []

            week_group.append(candle)

        # 마지막 주 처리
        if week_group:
            result.append(CandlestickConverter._create_candle_from_group(week_group))

        # 변환된 캔들들의 변동값 재계산
        CandlestickConverter._recalculate_changes(result)

        return result
    
    @staticmethod
    def convert_daily_to_2w(candles: List[Dict]) -> List[Candle]:
        """
        일봉 데이터를 2주봉으로 변환

        Args:
            candles: 일봉 캔들 리스트

        Returns:
            2주봉 캔들 리스트
        """
        if not candles:
            return []

        result = []
        i = 0

        while i < len(candles):
            # 10거래일(약 2주) 또는 남은 캔들을 그룹화
            group = candles[i:i+10]

            if not group:
                break

            result.append(CandlestickConverter._create_candle_from_group(group))
            i += 10

        # 변환된 캔들들의 변동값 재계산
        CandlestickConverter._recalculate_changes(result)

        return result
    
    @staticmethod
    def _create_candle_from_group(group: List[Dict]) -> Candle:
        """
        캔들 그룹에서 하나의 캔들 생성

        Args:
            group: 캔들 데이터 리스트

        Returns:
            병합된 캔들 데이터
        """
        open_price = float(group[0]['open'])
        close_price = float(group[-1]['close'])
        high_price = max(float(c['high']) for c in group)
        low_price = min(float(c['low']) for c in group)

        base_date = group[-1]['date']

        # 변동값은 변환 후 _recalculate_changes에서 재계산
        return Candle(
            date=base_date,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            change_value=0,
            change_rate=0
        )

    @staticmethod
    def _recalculate_changes(candles: List[Candle]) -> None:
        """
        변환된 캔들 리스트의 변동값을 재계산합니다.
        이전 캔들의 종가 대비 현재 캔들의 종가 변동을 계산합니다.

        Args:
            candles: 변환된 캔들 리스트 (in-place 수정)
        """
        if len(candles) < 2:
            return

        for i in range(1, len(candles)):
            prev_close = candles[i - 1].close
            curr_close = candles[i].close

            # 변동값 계산
            change_value = curr_close - prev_close
            # 변동률 계산: ((현재 - 이전) / 이전) * 100
            change_rate = (change_value / prev_close) * 100 if prev_close != 0 else 0

            candles[i].change_value = round(change_value, 2)
            candles[i].change_rate = round(change_rate, 2)
    
    @staticmethod
    def validate_candles(candles: List[Dict]) -> bool:
        """캔들 데이터 유효성 검증"""
        required_fields = ['date', 'open', 'high', 'low', 'close']
        
        for candle in candles:
            if not all(field in candle for field in required_fields):
                return False
            
            # 고가 >= 종가, 저가 및 시가 확인
            if not (float(candle['high']) >= float(candle['low'])):
                return False
        
        return True
