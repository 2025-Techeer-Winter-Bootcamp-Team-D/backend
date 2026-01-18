import requests, zipfile, io
from django.core.management.base import BaseCommand
from django.db import connection
from industries.models import KisIndustry, KsicCategory, IndustryMapping

class Command(BaseCommand):
    help = "구조체 도면 기반 정밀 파싱으로 데이터를 교정합니다."

    def handle(self, *args, **options):
        # 1. 테이블 초기화 (ID 1번부터 다시 시작)
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE industry_industrymapping RESTART IDENTITY CASCADE;")
            cursor.execute("TRUNCATE TABLE kis_industry RESTART IDENTITY CASCADE;")
        self.stdout.write(self.style.SUCCESS("🧹 테이블 초기화 완료"))

        base_url = "https://new.real.download.dws.co.kr/common/master/"
        targets = [
            {"name": "KOSPI", "file": "kospi_code.mst.zip", "ksic_off": 253},
            {"name": "KOSDAQ", "file": "kosdaq_code.mst.zip", "ksic_off": 248}
        ]

        for target in targets:
            res = requests.get(base_url + target['file'])
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                content = z.read(z.namelist()[0])

            # 줄바꿈 없이 고정 길이로 붙어 있는 경우를 대비해 처리
            # (한 줄의 길이는 통상적으로 280~300바이트 사이입니다)
            lines = content.split(b'\n')
            
            for line in lines:
                if len(line) < 260 or b'ST' not in line: continue
                
                # 2. 정밀 슬라이싱 적용 (구조체 기반)
                kis_code = line[65:69].decode('cp949').strip()
                ksic_code = line[target['ksic_off']:target['ks_off']+5].decode('cp949').strip()

                if kis_code.isdigit() and ksic_code.isdigit():
                    kis_obj, _ = KisIndustry.objects.get_or_create(kis_code=kis_code)
                    ksic_obj, _ = KsicCategory.objects.get_or_create(ksic_code=ksic_code)
                    IndustryMapping.objects.get_or_create(ksic=ksic_obj, kis=kis_obj)

        self.stdout.write(self.style.SUCCESS("✨ 정밀 매핑 완료!"))