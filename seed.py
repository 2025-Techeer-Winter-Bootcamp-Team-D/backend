import os
import django

# 1. 장고 환경 설정 로드
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from industries.models import Industry
from companies.models import Company
from django.db import transaction, connection
from django.core.management import call_command

def run():
    try:
        with transaction.atomic():
            # 2. 기존 데이터 삭제
            print("기존 데이터 삭제 중...")
            company_count, _ = Company.objects.all().delete()
            industry_count, _ = Industry.objects.all().delete()
            print(f"✅ 삭제 완료 - Company: {company_count}개, Industry: {industry_count}개")
            
            # 3. 시퀀스 리셋 (auto_increment 초기화)
            print("시퀀스 리셋 중...")
            with connection.cursor() as cursor:
                cursor.execute("ALTER SEQUENCE industry_industry_id_seq RESTART WITH 1")
            print("✅ 시퀀스 리셋 완료")

            # 3. 산업군(Industry) 생성
            semi = Industry.objects.create(name="반도체", description="반도체 제조")
            it = Industry.objects.create(name="IT 서비스", description="소프트웨어/플랫폼")
            auto = Industry.objects.create(name="자동차", description="자동차 제조")
            bio = Industry.objects.create(name="바이오", description="바이오/제약")
            energy = Industry.objects.create(name="에너지", description="에너지/화학")

            # 4. 사용자님의 모델 필드에 1:1 매칭된 데이터
            # [매핑 가이드]
            # - stock_code: 6자리 종목코드
            # - corp_code: 8자리 DART 고유번호
            # - industry: Industry 객체 (ForeignKey)
            # - induty_code: 업종코드 (예: 261, 301 등)
            companies_data = [
                {
                    "stock_code": "005930", 
                    "corp_code": "00126380", 
                    "industry": semi, 
                    "induty_code": "261", 
                    "company_name": "삼성전자", 
                    "market_amount": 450000000000000,
                    "ceo_name": "한종희, 경계현", 
                    "establishment_date": "1969-01-13",
                    "homepage_url": "https://www.samsung.com", 
                    "address": "경기도 수원시 영통구 삼성로 129",
                    "logo_url": "https://upload.wikimedia.org/wikipedia/commons/2/24/Samsung_Logo.svg",
                    "description": "세계 최대의 메모리 반도체 제조사"
                },
                {
                    "stock_code": "000660", 
                    "corp_code": "00164779", 
                    "industry": semi, 
                    "induty_code": "261", 
                    "company_name": "SK하이닉스", 
                    "market_amount": 150000000000000,
                    "ceo_name": "박정호, 곽노정", 
                    "establishment_date": "1983-02-01",
                    "homepage_url": "https://www.skhynix.com", 
                    "address": "경기도 이천시 부발읍 경충대로 2091",
                    "logo_url": "https://example.com/sk_hynix.png"
                },
                {
                    "stock_code": "005380", 
                    "corp_code": "00164742", 
                    "industry": auto, 
                    "induty_code": "301", 
                    "company_name": "현대자동차", 
                    "market_amount": 105000000000000,
                    "ceo_name": "정의선, 장재훈", 
                    "establishment_date": "1967-12-29",
                    "homepage_url": "https://www.hyundai.com", 
                    "address": "서울특별시 서초구 바우뫼로12길 70",
                    "logo_url": "https://example.com/hyundai.png"
                },
                {
                    "stock_code": "035420", 
                    "corp_code": "00266961", 
                    "industry": it, 
                    "induty_code": "631", 
                    "company_name": "NAVER", 
                    "market_amount": 35000000000000,
                    "ceo_name": "최수연", 
                    "establishment_date": "1999-06-02",
                    "homepage_url": "https://www.navercorp.com", 
                    "address": "경기도 성남시 분당구 불정로 6",
                    "logo_url": "https://example.com/naver.png"
                }
            ]

            # 5. 데이터 삽입 실행
            for data in companies_data:
                Company.objects.create(**data)

            print(f"✅ 총 {len(companies_data)}개의 기업 데이터를 성공적으로 삽입했습니다.")

    except Exception as e:
        print(f"❌ 데이터 삽입 중 에러 발생: {e}")

if __name__ == "__main__":
    run()