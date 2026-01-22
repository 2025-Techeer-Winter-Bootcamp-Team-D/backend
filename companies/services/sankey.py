import os
import requests
import logging
import re
from django.db import transaction
from companies.models import Company, FinancialStatement, Report
from ..models import SankeyData

logger = logging.getLogger(__name__)

class SankeyDataService:
    def __init__(self):
        self.api_key = os.getenv('DART_API_KEY')
        self.url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
        self.REQUEST_TIMEOUT = 30

    def _safe_float(self, val):
        if not val or val == '-': 
            return 0.0
        try: 
            return float(re.sub(r'[^0-9.-]', '', str(val)))
        except (ValueError, TypeError): 
            return 0.0

    def _normalize_nm(self, nm):
        if not nm:  
            return ""
        return re.sub(r'[\s와및]', '', nm)

    def sync_all_companies(self, year=2024):
        companies = Company.objects.filter(is_deleted=False)
        target_year=int(year)
        for company in companies:
            self.sync_right_side(company, target_year)
        return {"status": "success"}

    def sync_right_side(self, company, year=2024):
        try:
            fs = FinancialStatement.objects.filter(company=company, fiscal_year=year, report_code='11011').first()
            report = Report.objects.filter(company=company, report_name__contains=str(year)).first()
            ext_info = report.extracted_info if report else {}
            
            params = {
                'crtfc_key': self.api_key, 
                'corp_code': company.corp_code, 
                'bsns_year': str(year), 
                'reprt_code': '11011', 
                'fs_div': 'CFS'
            }
            
            try:
                response = requests.get(self.url, params=params, timeout=self.REQUEST_TIMEOUT)
                response.raise_for_status()
                res = response.json()
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"CFS API 호출 실패 ({company.company_name}): {e}")
                return False

            if res.get('status') != '000':
                params['fs_div'] = 'OFS' 
                try:
                    response = requests.get(self.url, params=params, timeout=self.REQUEST_TIMEOUT)
                    response.raise_for_status()
                    res = response.json()
                except (requests.RequestException, ValueError) as e:
                    logger.warning(f"OFS API 호출 실패 ({company.company_name}): {e}")
                    return False
            
            items = res.get('list', [])
            dart = {'rev': 0, 'cogs': 0, 'sg_a': 0, 'ope': 0, 'ni': 0}
            
            for item in items:
                nm = self._normalize_nm(item.get('account_nm', ''))
                val = self._safe_float(item.get('thstrm_amount'))
                aid = item.get('account_id', '')

                if (any(k in nm for k in ['매출액', '영업수익', '수익(매출액)', '수익']) or 
                    aid in ['ifrs-full_Revenue', 'ifrs_Revenue']):
                    if dart['rev'] == 0: 
                        dart['rev'] = val
                elif (('순이익' in nm and '차감전' not in nm) or 
                      aid in ['ifrs-full_ProfitLoss', 'ifrs_ProfitLoss']):
                    if dart['ni'] == 0: 
                        dart['ni'] = val
                elif (any(k in nm for k in ['매출원가', '영업원가']) or 
                      aid in ['ifrs-full_CostOfSales', 'ifrs_CostOfSales']):
                    if dart['cogs'] == 0: 
                        dart['cogs'] = val
                elif (any(k in nm for k in ['판매비관리비', '일반관리비']) or 
                      aid in [
                          'ifrs-full_SellingGeneralAndAdministrativeExpenses', 
                          'ifrs_SellingGeneralAndAdministrativeExpenses'
                      ]):
                    if dart['sg_a'] == 0: 
                        dart['sg_a'] = val
                elif '영업비용' in nm:
                    if dart['ope'] == 0: 
                        dart['ope'] = val

            f_cogs = dart['cogs']
            f_sga = dart['sg_a']
            f_ni = dart['ni']
            
            if f_cogs == 0 and f_sga == 0 and dart['ope'] > 0:
                f_sga = dart['ope']

            total_rev = fs.revenue if fs and fs.revenue > 0 else dart['rev']
            sum_parts = f_cogs + f_sga + max(0, f_ni)

            # 총 매출액 단위 보정 (재무제표 데이터 기준)
            if total_rev > 0 and sum_parts > total_rev * 500:
                total_rev *= 1000000
            
            if sum_parts > total_rev:
                total_rev = sum_parts

            if total_rev == 0: 
                return None

            display_ni = max(0, f_ni)

            if any(x in company.company_name for x in ["금융", "지주", "은행", "보험"]):
                center = "영업수익"
            else:
                center = "매출액"
            
            nodes, links = [{"name": center}], []
            segments_list = []
            rev_comps = ext_info.get('revenue_composition', [])
            
            # --- 수정된 부분: 비율(Ratio) 기반 매출 역산 ---
            for rc in rev_comps:
                s_name = rc.get('segment', '미분류')
                s_ratio = self._safe_float(rc.get('ratio', 0))
                
                # 총 매출액에 비율을 곱하여 사업부 매출 결정
                s_val = total_rev * (s_ratio / 100)
                
                # 비중이 없거나 기타 항목은 건너뜀 (사용자 요청)
                if s_val <= 0 or '기타' in s_name:
                    continue
                
                nodes.append({"name": s_name})
                links.append({"source": s_name, "target": center, "value": s_val})
                segments_list.append({"name": s_name, "value": s_val})

            # --- 수정된 부분: 인위적인 '기타 매출' 생성 로직 삭제 ---
            # (기존의 left_other 계산 및 추가 코드를 제거했습니다.)

            # 오른쪽 노드 (비용 및 이익) 로직 유지
            right_other = max(0, total_rev - sum_parts)
            for n, v in [("원가비용", f_cogs), ("판관비", f_sga), ("순수익", display_ni), ("기타 비용", right_other)]:
                if v > 0:
                    nodes.append({"name": n})
                    links.append({"source": center, "target": n, "value": v})

            with transaction.atomic():
                SankeyData.objects.update_or_create(
                    company=company, fiscal_year=year,
                    defaults={
                        'nodes': nodes, 
                        'links': links,
                        'is_loss': f_ni < 0,
                        'raw_values': {
                            'total_revenue': total_rev,
                            'segments': segments_list,
                            'cogs': f_cogs, 
                            'sg_a': f_sga, 
                            'net_income': f_ni, 
                            'other_expense': right_other
                        }
                    }
                )
            return True
        except Exception as e:
            logger.error(f"Sankey Error: {e}")
            return False