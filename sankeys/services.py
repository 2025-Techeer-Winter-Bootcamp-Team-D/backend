import os
import requests
from decimal import Decimal
from .models import FinancialFlow

class FinancialFlowService:
    def __init__(self):
        self.api_key = os.getenv('DART_API_KEY')
        self.data_url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

    def _clean_decimal(self, value):
        if not value or value in ["-", "", " "]: return Decimal('0')
        try:
            return Decimal(str(value).replace(',', '').strip())
        except:
            return Decimal('0')

    def fetch_and_save_financials(self, company, year):
        params = {
            'crtfc_key': self.api_key, 
            'corp_code': company.corp_code, 
            'bsns_year': str(year), 
            'reprt_code': '11011', 
            'fs_div': 'CFS'
        }
        
        try:
            res = requests.get(self.data_url, params=params, timeout=10).json()
            if res.get('status') != '000':
                return None
            
            lines = res.get('list', [])
            d = {k: Decimal('0') for k in ['rev', 'fin_inc', 'oth_inc', 'cost', 'sga', 'fin_cost', 'tax', 'net_profit']}

            for row in lines:
                if row.get('sj_div') != 'IS': continue
                aid = row.get('account_id', '')
                nm = row.get('account_nm', '').replace(" ", "") 
                val = self._clean_decimal(row.get('thstrm_amount'))

                if 'Revenue' in aid or any(x in nm for x in ['매출액', '영업수익', '수익(매출액)']):
                    if val > d['rev']: d['rev'] = val
                elif 'CostOfSales' in aid or '매출원가' in nm:
                    d['cost'] = val
                elif 'AdministrativeExpenses' in aid or any(x in nm for x in ['판매비와관리비', '판관비', '영업비용']):
                    d['sga'] = val
                elif 'FinanceIncome' in aid or '금융수익' in nm:
                    d['fin_inc'] = val
                elif 'FinanceCosts' in aid or '금융비용' in nm:
                    d['fin_cost'] = val
                elif 'IncomeTaxExpense' in aid or '법인세비용' in nm:
                    d['tax'] = val
                elif ('ProfitLoss' in aid or '당기순이익' in nm) and 'Comprehensive' not in aid and '포괄' not in nm:
                    d['net_profit'] = val
                elif 'OtherNonOperatingIncome' in aid or '기타수익' in nm:
                    d['oth_inc'] = val

            # --- 밸런싱 로직 시작 ---
            income = d['net_profit'] if d['net_profit'] > 0 else Decimal('0')
            loss = abs(d['net_profit']) if d['net_profit'] < 0 else Decimal('0')
            
            raw_in = d['rev'] + d['fin_inc'] + d['oth_inc'] + loss
            raw_out = d['cost'] + d['sga'] + d['fin_cost'] + d['tax'] + income

            # 더 큰 값을 기준으로 총액 설정
            total_val = max(raw_in, raw_out)
            
            # 유입이 부족하면 기타 유입(etc_inc)으로 채움
            etc_inc = total_val - raw_in
            # 유출이 부족하면 순이익(adjusted_net_income)을 조정하여 수평 유지
            adjusted_net_income = income + (total_val - raw_out)

            flow, _ = FinancialFlow.objects.update_or_create(
                company=company, 
                year=year,
                defaults={
                    'total_revenue': total_val,
                    'source_rev_val': d['rev'], 
                    'source_fin_val': d['fin_inc'], 
                    'source_oth_val': d['oth_inc'], 
                    'source_etc_val': etc_inc,
                    'net_loss_val': loss, 
                    'cost_of_sales': d['cost'], 
                    'sg_and_a': d['sga'], 
                    'finance_costs': d['fin_cost'], 
                    'tax_costs': d['tax'], 
                    'net_income_val': adjusted_net_income
                }
            )
            return flow
        except Exception as e:
            print(f"❌ Error for {company.stock_code}: {e}")
            return None