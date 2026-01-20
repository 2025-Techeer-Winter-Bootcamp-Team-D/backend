import os, requests, logging, re
from django.db import transaction
from companies.models import Company, RevenueComposition, FinancialStatement
from .models import SankeyData

logger = logging.getLogger(__name__)

class SankeyDataService:
   

    def __init__(self):
        self.api_key = os.getenv('DART_API_KEY')
        self.url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

    def _safe_float(self, val):
        if not val or val == '-': return 0.0
        try: return float(re.sub(r'[^0-9.-]', '', str(val)))
        except: return 0.0

    # [신규] 전체 기업 일괄 업데이트 기능
    def sync_all_companies(self, year=2024):
        companies = Company.objects.filter(is_deleted=False)
        success_count = 0
        failed_list = []
        
        for company in companies:
            # 아래의 검증된 로직을 그대로 호출
            if self.sync_right_side(company, year):
                success_count += 1
            else:
                failed_list.append(company.company_name)
        return {"success_count": success_count, "failed_companies": failed_list}

    REQUEST_TIMEOUT = 30

    def sync_right_side(self, company, year=2024):
        """
        데이터 정합성 로직 유지: 수치 계산식 절대 안 건드림
        """
        try:
            # 1. 팀원 데이터 가져오기
            fs = FinancialStatement.objects.filter(company=company, fiscal_year=year, report_code='11011').first()
            if not fs or not fs.revenue:
                logger.warning(f"데이터 없음: {company.company_name}")
                return None
            
            teammate_total_rev = fs.revenue
            rev_comps = RevenueComposition.objects.filter(company=company, fiscal_year=year)

            # 2. DART 데이터 낚기
            params = {'crtfc_key': self.api_key, 'corp_code': company.corp_code, 'bsns_year': str(year), 'reprt_code': '11011', 'fs_div': 'CFS'}
            res = requests.get(self.url, params=params, timeout=self.REQUEST_TIMEOUT).json()
            if res.get('status') != '000':
                params['fs_div'] = 'OFS'
                res = requests.get(self.url, params=params, timeout=self.REQUEST_TIMEOUT).json()
            
            items = res.get('list', [])
            dart_raw = {'cogs': 0, 'sg_a': 0, 'net_income': 0}
            
            id_map = {
                'cogs': ['ifrs-full_CostOfSales', 'ifrs_CostOfSales', 'ifrs-full_OperatingExpenses'],
                'sg_a': ['ifrs-full_SellingGeneralAndAdministrativeExpenses', 'ifrs_SellingGeneralAndAdministrativeExpenses'],
                'net_income': ['ifrs-full_ProfitLoss', 'ifrs_ProfitLoss', 'ifrs-full_ProfitLossAttributableToOwnersOfParent']
            }

            for key, ids in id_map.items():
                for item in items:
                    if item.get('account_id') in ids:
                        val = self._safe_float(item.get('thstrm_amount'))
                        if val != 0: dart_raw[key] = val; break
                if dart_raw[key] == 0:
                    for item in items:
                        nm = item.get('account_nm', '').replace(' ', '')
                        val = self._safe_float(item.get('thstrm_amount'))
                        if key == 'cogs' and any(k in nm for k in ['매출원가', '영업원가']): dart_raw[key] = val
                        elif key == 'sg_a' and '판매비와관리비' in nm: dart_raw[key] = val
                        elif key == 'net_income' and ('순이익' in nm and '차감전' not in nm): dart_raw[key] = val
                        if dart_raw[key] != 0: break

            # 3. 로직 유지
            is_loss = dart_raw['net_income'] <= 0
            display_ni = 0 if is_loss else dart_raw['net_income']

            # 4. 산술 계산 (기존 수식 유지)
            seg_sum = sum(rc.revenue for rc in rev_comps)
            left_other = teammate_total_rev - seg_sum
            if left_other < 0: left_other = 0

            right_other = teammate_total_rev - (dart_raw['cogs'] + dart_raw['sg_a'] + display_ni)
            if right_other < 0: right_other = 0

            # 5. 구성 (이름만 '기타' -> '기타 비용'으로 수정)
            center = "영업수익" if any(x in company.company_name for x in ["금융", "지주", "은행"]) else "매출액"
            nodes = [{"name": center}]
            links = []

            for rc in rev_comps:
                nodes.append({"name": rc.segment_name})
                links.append({"source": rc.segment_name, "target": center, "value": rc.revenue})
            if left_other > 0:
                nodes.append({"name": "기타 매출"})
                links.append({"source": "기타 매출", "target": center, "value": left_other})

            
            for n, v in [("원가비용", dart_raw['cogs']), ("판관비", dart_raw['sg_a']), ("순수익", display_ni), ("기타 비용", right_other)]:
                if v > 0: # 0원인 건 안 나오게 필터링 추가
                    nodes.append({"name": n})
                    links.append({"source": center, "target": n, "value": v})

            # 6. 저장
            with transaction.atomic():
                sankey, _ = SankeyData.objects.update_or_create(
                    company=company, fiscal_year=year,
                    defaults={
                        'nodes': nodes, 'links': links, 'is_loss': is_loss,
                        'raw_values': {
                            'total_revenue': teammate_total_rev,
                            'cogs': dart_raw['cogs'], 'sg_a': dart_raw['sg_a'], 
                            'net_income': dart_raw['net_income'], 'other_expense': right_other
                        }
                    }
                )
            return sankey
        except Exception as e:
            logger.error(f"Sankey Sync Error: {e}")
            return None