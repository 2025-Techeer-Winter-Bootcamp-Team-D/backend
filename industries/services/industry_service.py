# industries/services/industry_service.py
import pandas as pd
from django.db.models import Count
from industries.models import IndustryMapping, KisIndustry
from company.models import Company

class IndustryService:
    def get_representative_kis_index(self, ksic_3digit):
        """
        DART KSIC 3자리 코드를 받아 대응하는 가장 적절한 KIS 업종 객체를 반환합니다.
        """
        # 1. 해당 KSIC 3자리 코드를 가진 기업들의 티커 리스트 추출
        tickers = Company.objects.filter(
            induty_code__startswith=ksic_3digit  # 5자리여도 앞 3자리로 검색
        ).values_list('ticker', flat=True)

        if not tickers:
            return None

        # 2. IndustryMapping에서 해당 티커들이 어떤 KIS 업종에 분포해 있는지 집계
        # 가장 많이 나타나는(최빈값) KIS 업종 코드를 찾습니다.
        most_frequent_kis = IndustryMapping.objects.filter(
            ticker__in=tickers
        ).values('kis').annotate(
            count=Count('kis')
        ).order_by('-count').first()

        if not most_frequent_kis:
            return None

        # 3. 최종 매핑된 KIS 업종 객체 반환
        return KisIndustry.objects.get(kis_code=most_frequent_kis['kis'])

    def get_industry_chart_data(self, ksic_3digit):
        """
        최종적으로 차트 데이터를 가져오기 위한 진입점입니다.
        """
        kis_industry = self.get_representative_kis_index(ksic_3digit)
        
        if not kis_industry:
            return {"error": "매핑된 산업 지수가 없습니다."}

        # 여기서 기존에 구현하신 KISIndexService를 호출하여 차트 데이터를 가져옵니다.
        # return KISIndexService().fetch_index_history(kis_industry.kis_code)
        return {
            "ksic_3digit": ksic_3digit,
            "matched_kis_code": kis_industry.kis_code,
            "matched_kis_name": kis_industry.name
        }