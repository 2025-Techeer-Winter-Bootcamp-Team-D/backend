"""
산업 데이터 초기화 Management Command

한국표준산업분류(KSIC) 공식 코드를 사용하여 산업 데이터를 초기화합니다.

사용법:
    python manage.py seed_industries
    python manage.py seed_industries --reset  # 기존 데이터 삭제 후 재생성
"""

from django.core.management.base import BaseCommand
from industries.models import Industry


class Command(BaseCommand):
    help = "kis 코드를 사용하여 산업 데이터를 초기화합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="기존 산업 데이터를 삭제하고 새로 생성합니다 (기본값: False)",
        )

    def handle(self, *args, **options):
        reset = options["reset"]

        # KSIC 기반 KIS 산업 분류 데이터
        industries_data = [
            # --- A. 농업, 임업 및 어업 (통합 지수 사용) ---
            {"name": "농업/어업", "induty_code": "0027", "description": "KOSPI 농림수산업 통합 지수"},

            # --- C. 제조업 (KOSPI/KOSDAQ 주요 지수) ---
            {"name": "제조업", "induty_code": "1015", "description": "코스닥 제조 지수"},
            {"name": "음식료품", "induty_code": "0006", "description": "KOSPI 음식료품 업종 지수"},
            {"name": "화학/정유", "induty_code": "0009", "description": "KOSPI 화학 및 석유정제 통합 지수"},
            {"name": "의약품", "induty_code": "0010", "description": "KOSPI 의약품 업종 지수 (바이오 포함)"},
            {"name": "전기전자", "induty_code": "0014", "description": "KOSPI 전기전자 지수 (반도체/IT 핵심)"},
            {"name": "운수장비", "induty_code": "0015", "description": "KOSPI 운수장비 지수 (자동차/조선)"},
            {"name": "반도체(코스닥)", "induty_code": "1047", "description": "KOSDAQ 반도체 업종 지수"},
            {"name": "IT(코스닥)", "induty_code": "1012", "description": "KOSDAQ IT 업종지수"},

            # --- F. 건설업 ---
            {"name": "건설업", "induty_code": "0018", "description": "KOSPI 건설업 업종 지수"},

            # --- G. 도매 및 소매업 ---
            {"name": "유통업", "induty_code": "0016", "description": "KOSPI 유통업 및 소매 지수"},

            # --- H. 운수 및 창고업 ---
            {"name": "운수창고", "induty_code": "0019", "description": "KOSPI 육상/해상/항공 운송 통합 지수"},

            # --- J. 정보통신업 ---
            {"name": "통신업", "induty_code": "0020", "description": "KOSPI 통신업 업종 지수"},
            {"name": "소프트웨어", "induty_code": "1042", "description": "KOSDAQ 소프트웨어 지수"},
        

            # --- K. 금융 및 보험업 ---
            {"name": "금융업", "induty_code": "0021", "description": "KOSPI 금융업 통합 지수"},
            {"name": "보험", "induty_code": "0025", "description": "KOSPI 보험 업종 지수"},

            # --- M. 전문, 과학 및 기술 서비스업 ---
            {"name": "서비스업", "induty_code": "0026", "description": "KOSPI 서비스업 및 연구개발 통합 지수"},
            
            # --- 대표 시장 지수 (추가 권장) ---
            {"name": "코스피", "induty_code": "0001", "description": "KOSPI 종합 지수"},
            {"name": "코스닥", "induty_code": "1001", "description": "KOSDAQ 종합 지수"},
            {"name": "KRX 300", "induty_code": "2001", "description": "코스피/코스닥 통합 우량 300 지수"},
        ]
    

        if reset:
            self.stdout.write(self.style.WARNING("기존 산업 데이터 삭제 및 ID 초기화 중..."))
            
            # DELETE 대신 Raw SQL로 TRUNCATE RESTART IDENTITY 실행
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE industry RESTART IDENTITY CASCADE;")
                
            self.stdout.write(self.style.SUCCESS("기존 데이터 삭제 및 ID 1번 초기화 완료"))

        created_count = 0
        updated_count = 0

        for industry_data in industries_data:
            induty_code = industry_data.get("induty_code")
            defaults = {
                "name": industry_data["name"],
                "description": industry_data["description"],
            }

            # 업종코드가 있으면 업종코드로 조회/생성, 없으면 이름으로 조회/생성
            if induty_code:
                industry, created = Industry.objects.get_or_create(
                    induty_code=induty_code,
                    defaults=defaults,
                )
            else:
                # 업종코드가 없는 경우 (예: "기타") 이름으로만 조회/생성
                industry, created = Industry.objects.get_or_create(
                    name=industry_data["name"],
                    defaults=defaults,
                )

            # 기존 데이터 업데이트 (이름, 설명, 업종코드)
            if not created:
                updated = False
                # 이름 업데이트
                if industry.name != industry_data["name"]:
                    industry.name = industry_data["name"]
                    updated = True
                # 설명 업데이트
                if industry.description != industry_data["description"]:
                    industry.description = industry_data["description"]
                    updated = True
                # 업종코드 업데이트 (업종코드가 없었던 경우)
                if induty_code and not industry.induty_code:
                    industry.induty_code = induty_code
                    updated = True
                if updated:
                    industry.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  업데이트: {industry.name} (업종코드: {induty_code or 'N/A'})"
                        )
                    )
            else:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  생성: {industry.name} (업종코드: {induty_code or 'N/A'})"
                    )
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("산업 데이터 초기화 완료"))
        self.stdout.write(f"  생성: {created_count}개")
        if updated_count > 0:
            self.stdout.write(f"  업데이트: {updated_count}개")
        self.stdout.write(f"  전체: {Industry.objects.count()}개")
        self.stdout.write(self.style.SUCCESS("=" * 50))
