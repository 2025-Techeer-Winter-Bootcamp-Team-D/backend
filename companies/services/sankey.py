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
        if not val or val == '-': return 0.0
        try: return float(re.sub(r'[^0-9.-]', '', str(val)))
        except (ValueError, TypeError): return 0.0

    def _normalize_nm(self, nm):
        if not nm: return ""
        return re.sub(r'[\s와및]', '', nm)

    def sync_all_companies(self, year=2024):
        companies = Company.objects.filter(is_deleted=False)
        target_year = int(year)
        for company in companies:
            self.sync_right_side(company, target_year)
        return {"status": "success"}

    def sync_right_side(self, company, year=2024):
        try:
            # 1. 데이터 로드 및 업종 분석
            fs = FinancialStatement.objects.filter(company=company, fiscal_year=year, report_code='11011').first()
            report = Report.objects.filter(company=company, report_name__contains=str(year)).first()
            ext_info = report.extracted_info if report else {}
            is_finance = any(x in company.company_name for x in ["금융", "지주", "은행", "보험", "생명", "화재"])
            
            params = {'crtfc_key': self.api_key, 'corp_code': company.corp_code, 'bsns_year': str(year), 'reprt_code': '11011', 'fs_div': 'CFS'}
            res = requests.get(self.url, params=params, timeout=self.REQUEST_TIMEOUT).json()
            if res.get('status') != '000':
                params['fs_div'] = 'OFS'
                res = requests.get(self.url, params=params, timeout=self.REQUEST_TIMEOUT).json()
            
            items = res.get('list', [])
            dart = {'rev': 0, 'cogs': 0, 'sg_a': 0, 'ope': 0, 'ni': 0}
            ni_candidates = []

            # 2. 정밀 추출
            for item in items:
                nm = self._normalize_nm(item.get('account_nm', ''))
                val = self._safe_float(item.get('thstrm_amount'))
                aid = item.get('account_id', '')

                # 매출/수익
                rev_keys = ['매출액', '영업수익', '수익(매출액)', '보험료수익', '이자수익', '수수료수익']
                if any(k in nm for k in rev_keys) or aid in ['ifrs-full_Revenue', 'ifrs-full_OperatingRevenue']:
                    if is_finance: dart['rev'] += val
                    else: dart['rev'] = max(dart['rev'], val)
                
                # 순이익 추출
                if (any(k in nm for k in ['순이익', '순손익', '분기순이익', '반기순이익'])) and '차감전' not in nm and '비지배' not in nm:
                    priority = 3 if aid in ['ifrs-full_ProfitLoss', 'ifrs_ProfitLoss'] else (2 if '지배' in nm else 1)
                    ni_candidates.append({'val': val, 'priority': priority})

                # 비용 계정
                if any(k in nm for k in ['매출원가', '영업원가']): dart['cogs'] = val
                if any(k in nm for k in ['판매비관리비', '일반관리비']): dart['sg_a'] = val
                if '영업비용' in nm: dart['ope'] = val

            if ni_candidates:
                ni_candidates.sort(key=lambda x: (x['priority'], abs(x['val'])), reverse=True)
                dart['ni'] = ni_candidates[0]['val']

            # 3. 핀포인트 자릿수 동기화 및 "음수 보정 방어"
            total_rev = fs.revenue if fs and fs.revenue > 10**10 else dart['rev']
            
            def align_value_final(val, reference, is_ni=False):
                if val == 0 or reference == 0: return val
                margin = abs(val / reference)
                if 0.001 <= margin <= 1.5: return val
                
                # [핵심 수리] 음수이면서 자릿수가 너무 작으면 보정하지 않고 원본 유지 (금융사 적자 방지)
                if is_ni and val < 0 and margin < 0.0001:
                    return val

                if margin < 0.0001:
                    boosted = val * 1_000_000
                    if 0.001 < abs(boosted / reference) < 0.6: return boosted
                if margin > 1000: return val / 1_000_000
                return val

            f_cogs = align_value_final(dart['cogs'], total_rev)
            f_sga = align_value_final(dart['sg_a'], total_rev)
            f_ni = align_value_final(dart['ni'], total_rev, is_ni=True)
            
            if f_cogs == 0 and f_sga == 0 and dart['ope'] > 0:
                f_sga = align_value_final(dart['ope'], total_rev)

            display_ni = max(0, f_ni)
            sum_parts = f_cogs + f_sga + display_ni
            if not is_finance and sum_parts > total_rev * 1.2:
                total_rev = sum_parts

            if total_rev == 0: return None

            # 4. 데이터 저장
            with transaction.atomic():
                center = "영업수익" if is_finance else "매출액"
                nodes, links, segments_list = [{"name": center}], [], []
                for rc in ext_info.get('revenue_composition', []):
                    s_name, s_ratio = rc.get('segment', '미분류'), self._safe_float(rc.get('ratio', 0))
                    s_val = total_rev * (s_ratio / 100)
                    if s_val <= 0 or '기타' in s_name: continue
                    nodes.append({"name": s_name}), links.append({"source": s_name, "target": center, "value": s_val})
                    segments_list.append({"name": s_name, "value": s_val})

                right_other = max(0, total_rev - (f_cogs + f_sga + display_ni))
                for n, v in [("원가비용", f_cogs), ("판관비", f_sga), ("순수익", display_ni), ("기타 비용", right_other)]:
                    if v > 0:
                        nodes.append({"name": n}), links.append({"source": center, "target": n, "value": v})

                SankeyData.objects.update_or_create(
                    company=company, fiscal_year=year,
                    defaults={
                        'nodes': nodes, 'links': links, 'is_loss': f_ni < 0,
                        'raw_values': {
                            'total_revenue': total_rev, 'segments': segments_list,
                            'cogs': f_cogs, 'sg_a': f_sga, 'net_income': f_ni, 'other_expense': right_other
                        }
                    }
                )
            return True
        except Exception as e:
            logger.error(f"Sankey Final Repair Error: {e}")
            return False