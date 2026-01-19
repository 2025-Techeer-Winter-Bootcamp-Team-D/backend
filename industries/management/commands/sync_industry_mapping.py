import requests, zipfile, io
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Count
from industries.models import KisIndustry, IndustryMapping, KsicCategory, Industry
from companies.models import Company

class Command(BaseCommand):
    help = "대분류/중분류 통합 분석을 통해 NAVER, Kakao 등 누락 종목 없이 매핑을 완료합니다."

    def handle(self, *args, **options):
        
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE industry_mapping, kis_industry RESTART IDENTITY CASCADE;")
        
        base_url = "https://new.real.download.dws.co.kr/common/master/"

        # STEP 1: 업종 마스터 적재
        res_idx = requests.get(base_url + "idxcode.mst.zip")
        with zipfile.ZipFile(io.BytesIO(res_idx.content)) as z:
            content = z.read(z.namelist()[0])
            for line in content.splitlines():
                if len(line) < 45: continue
                kis_code = line[1:5].decode('cp949', errors='ignore').strip()
                name = line[5:45].decode('cp949', errors='ignore').strip()
                if kis_code:
                    KisIndustry.objects.update_or_create(kis_code=kis_code, defaults={'name': name})

        # STEP 2: 종목 매핑 (대분류 64:68 와 중분류 68:72를 모두 체크)
        for target in [{"name": "KOSPI", "file": "kospi_code.mst.zip"}, {"name": "KOSDAQ", "file": "kosdaq_code.mst.zip"}]:
            res_stk = requests.get(base_url + target['file'])
            with zipfile.ZipFile(io.BytesIO(res_stk.content)) as z:
                content = z.read(z.namelist()[0])
                for line in content.splitlines():
                    if len(line) < 100 or line[61:63] != b'ST': continue
                    ticker = line[1:7].decode('cp949', errors='ignore').strip().zfill(6)
                    
                    # [로직 변경] 중분류(68:72)가 없으면 대분류(64:68)를 사용
                    mid_code = line[68:72].decode('cp949', errors='ignore').strip()
                    large_code = line[64:68].decode('cp949', errors='ignore').strip()
                    
                    kis_code = mid_code if mid_code != "0000" else large_code

                    if kis_code and kis_code != "0000":
                        kis_obj = KisIndustry.objects.filter(kis_code=kis_code).first()
                        if kis_obj:
                            IndustryMapping.objects.get_or_create(ticker=ticker, kis=kis_obj)

        # STEP 3: KSIC 마스터 생성
        unique_ksic_codes = Company.objects.filter(induty_code__isnull=False).values_list('induty_code', flat=True).distinct()
        for code in unique_ksic_codes:
            KsicCategory.objects.get_or_create(ksic_code=code)

        # STEP 4: 최종 매핑 및 통합 출력
        self.stdout.write("\n" + "="*90)
        self.stdout.write(f"{'KSIC':<6} | {'KIS':<6} | {'산업명':<15} | {'종목코드 리스트'}")
        self.stdout.write("="*90)

        for cat in KsicCategory.objects.all():
            tickers = list(Company.objects.filter(induty_code=cat.ksic_code).values_list('stock_code', flat=True))
            if not tickers: continue

            best_match = IndustryMapping.objects.filter(ticker__in=tickers)\
                .exclude(kis__kis_code='0001')\
                .values('kis', 'kis__name')\
                .annotate(cnt=Count('kis'))\
                .order_by('-cnt').first()
            
            if best_match:
                cat.representative_kis_id = best_match['kis']
                cat.name = best_match['kis__name']
                cat.save()
                
                # 요청하신 대로 종목코드들을 콤마로 이어 출력
                stock_str = ", ".join(tickers[:5]) + ("..." if len(tickers) > 5 else "")
                self.stdout.write(f"{cat.ksic_code:<6} | {best_match['kis']:<6} | {cat.name:<15} | {stock_str}")

            # STEP 5: Company 테이블의 induty_code를 KIS 코드로 변환
            self.stdout.write("\n🏢 STEP 5: Company 테이블 업종 코드(KSIC -> KIS) 변환 중...")
            updated_companies = 0
            with transaction.atomic():
                for cat in KsicCategory.objects.filter(representative_kis__isnull=False):
                    # 해당 KSIC 코드를 가진 기업들을 찾아 KIS 코드로 일괄 업데이트
                    count = Company.objects.filter(induty_code=cat.ksic_code)\
                        .update(induty_code=cat.representative_kis_id)
                    updated_companies += count
            self.stdout.write(self.style.SUCCESS(f"✅ {updated_companies}개 기업의 코드가 KIS 지수 코드로 변경되었습니다."))

            # ---------------------------------------------------------
            # STEP 6: Industry 테이블의 induty_code 갱신
            # ---------------------------------------------------------
            self.stdout.write("\n📊 STEP 6: Industry 테이블 최신화 중...")
            updated_industries = 0
            for cat in KsicCategory.objects.filter(representative_kis__isnull=False):
                # Industry 테이블에 해당 KIS 코드가 있다면 이름을 DART 카테고리 명칭 등으로 동기화
                industry, created = Industry.objects.update_or_create(
                    induty_code=cat.representative_kis_id,
                    defaults={
                        "name": cat.name, # KIS 지수명 사용 (예: 전기·전자)
                        "description": f"{cat.name} 지수 (KSIC:{cat.ksic_code} 매핑 결과)"
                    }
                )
                updated_industries += 1
            
        self.stdout.write(self.style.SUCCESS(f"✨ 완료: {updated_industries}개 산업군 정보 갱신 완료!"))