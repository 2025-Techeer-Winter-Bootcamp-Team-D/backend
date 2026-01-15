import os
import django

# 장고 환경 설정 로드
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from industries.models import Industry
from companies.models import Company
from django.db import transaction

def run():
    try:
        with transaction.atomic():
            # 1. 기존 데이터 삭제
            print("기존 데이터 삭제 중...")
            Company.objects.all().delete()
            Industry.objects.all().delete()

            # 2. 산업군(Industry) 생성
            semi = Industry.objects.create(name="반도체", description="메모리 및 비메모리 반도체 제조")
            it = Industry.objects.create(name="IT 서비스", description="플랫폼, 소프트웨어 및 클라우드")
            auto = Industry.objects.create(name="자동차", description="완성차 및 모빌리티 제조")
            bio = Industry.objects.create(name="바이오/헬스케어", description="제약, 신약 개발 및 바이오 시밀러")
            energy = Industry.objects.create(name="에너지/화학", description="2차전지, 신재생 에너지 및 석유화학")
            finance = Industry.objects.create(name="금융", description="은행, 지주사 및 핀테크")

            # 3. 상세 기업(Company) 데이터 삽입
            companies_data = [
                {
                    "stock_code": "005930", "corp_code": "00126380", "industry": semi,
                    "company_name": "삼성전자", "market_amount": 450000000000000,
                    "ceo_name": "한종희, 경계현", "establishment_date": "1969-01-13",
                    "homepage_url": "https://www.samsung.com", "address": "경기도 수원시 영통구 삼성로 129",
                    "logo_url": "https://upload.wikimedia.org/wikipedia/commons/2/24/Samsung_Logo.svg"
                },
                {
                    "stock_code": "000660", "corp_code": "00164779", "industry": semi,
                    "company_name": "SK하이닉스", "market_amount": 150000000000000,
                    "ceo_name": "박정호, 곽노정", "establishment_date": "1983-02-01",
                    "homepage_url": "https://www.skhynix.com", "address": "경기도 이천시 부발읍 경충대로 2091",
                    "logo_url": "https://example.com/sk_hynix_logo.png"
                },
                {
                    "stock_code": "005380", "corp_code": "00164742", "industry": auto,
                    "company_name": "현대자동차", "market_amount": 105000000000000,
                    "ceo_name": "정의선, 장재훈", "establishment_date": "1967-12-29",
                    "homepage_url": "https://www.hyundai.com", "address": "서울특별시 서초구 바우뫼로12길 70",
                    "logo_url": "https://example.com/hyundai_logo.png"
                },
                {
                    "stock_code": "000270", "corp_code": "00106641", "industry": auto,
                    "company_name": "기아", "market_amount": 50000000000000,
                    "ceo_name": "송호성, 최준영", "establishment_date": "1944-12-01",
                    "homepage_url": "https://www.kia.com", "address": "서울특별시 서초구 헌릉로 12",
                    "logo_url": "https://example.com/kia_logo.png"
                },
                {
                    "stock_code": "035420", "corp_code": "00266961", "industry": it,
                    "company_name": "NAVER", "market_amount": 35000000000000,
                    "ceo_name": "최수연", "establishment_date": "1999-06-02",
                    "homepage_url": "https://www.navercorp.com", "address": "경기도 성남시 분당구 불정로 6",
                    "logo_url": "https://example.com/naver_logo.png"
                },
                {
                    "stock_code": "035720", "corp_code": "00258838", "industry": it,
                    "company_name": "카카오", "market_amount": 20000000000000,
                    "ceo_name": "정신아", "establishment_date": "1995-02-16",
                    "homepage_url": "https://www.kakaocorp.com", "address": "제주특별자치도 제주시 첨단로 242",
                    "logo_url": "https://example.com/kakao_logo.png"
                },
                {
                    "stock_code": "373220", "corp_code": "01521404", "industry": energy,
                    "company_name": "LG에너지솔루션", "market_amount": 95000000000000,
                    "ceo_name": "김동명", "establishment_date": "2020-12-01",
                    "homepage_url": "https://www.lgensol.com", "address": "서울특별시 영등포구 여의대로 108",
                    "logo_url": "https://example.com/lgensol_logo.png"
                },
                {
                    "stock_code": "207940", "corp_code": "00877059", "industry": bio,
                    "company_name": "삼성바이오로직스", "market_amount": 90000000000000,
                    "ceo_name": "존림", "establishment_date": "2011-04-22",
                    "homepage_url": "https://www.samsungbiologics.com", "address": "인천광역시 연수구 송도바이오대로 300",
                    "logo_url": "https://example.com/sambio_logo.png"
                }
            ]

            for data in companies_data:
                Company.objects.create(**data)

            print(f"성공적으로 {len(companies_data)}개의 기업 데이터를 삽입했습니다.")
    except Exception as e:
        print(f"에러 발생: {e}")

if __name__ == "__main__":
    run()