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
    help = "한국표준산업분류(KSIC) 공식 코드를 사용하여 산업 데이터를 초기화합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="기존 산업 데이터를 삭제하고 새로 생성합니다 (기본값: False)",
        )

    def handle(self, *args, **options):
        reset = options["reset"]

        # 한국표준산업분류(KSIC) 공식 중분류 코드 및 명칭
        # 출처: 통계청 한국표준산업분류(KSIC)
        industries_data = [
            # 제조업 (C)
            {
                "name": "제조업",
                "induty_code": "C",
                "description": "제조업 (KSIC 대분류)",
            },
            # 제조업 중분류
            {
                "name": "식품제조업",
                "induty_code": "10",
                "description": "식료품 제조업 (KSIC 10)",
            },
            {
                "name": "음료제조업",
                "induty_code": "11",
                "description": "음료 제조업 (KSIC 11)",
            },
            {
                "name": "섬유제품 제조업",
                "induty_code": "13",
                "description": "섬유제품 제조업 (KSIC 13)",
            },
            {
                "name": "의복의류 제조업",
                "induty_code": "14",
                "description": "의복, 의류 제조업 (KSIC 14)",
            },
            {
                "name": "가죽, 가방 및 신발 제조업",
                "induty_code": "15",
                "description": "가죽, 가방 및 신발 제조업 (KSIC 15)",
            },
            {
                "name": "목재 및 나무제품 제조업",
                "induty_code": "16",
                "description": "목재 및 나무제품 제조업 (KSIC 16)",
            },
            {
                "name": "펄프, 종이 및 종이제품 제조업",
                "induty_code": "17",
                "description": "펄프, 종이 및 종이제품 제조업 (KSIC 17)",
            },
            {
                "name": "인쇄 및 기록매체 복제업",
                "induty_code": "18",
                "description": "인쇄 및 기록매체 복제업 (KSIC 18)",
            },
            {
                "name": "화학물질 및 화학제품 제조업",
                "induty_code": "20",
                "description": "화학물질 및 화학제품 제조업 (KSIC 20)",
            },
            {
                "name": "의료용 물질 및 의약품 제조업",
                "induty_code": "21",
                "description": "의료용 물질 및 의약품 제조업 (KSIC 21)",
            },
            {
                "name": "고무제품 및 플라스틱제품 제조업",
                "induty_code": "22",
                "description": "고무제품 및 플라스틱제품 제조업 (KSIC 22)",
            },
            {
                "name": "비금속 광물제품 제조업",
                "induty_code": "23",
                "description": "비금속 광물제품 제조업 (KSIC 23)",
            },
            {
                "name": "1차 금속 제조업",
                "induty_code": "24",
                "description": "1차 금속 제조업 (KSIC 24)",
            },
            {
                "name": "금속가공제품 제조업",
                "induty_code": "25",
                "description": "금속가공제품 제조업 (KSIC 25)",
            },
            {
                "name": "전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업",
                "induty_code": "26",
                "description": "전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업 (KSIC 26)",
            },
            {
                "name": "의료, 정밀, 광학기기 및 시계 제조업",
                "induty_code": "27",
                "description": "의료, 정밀, 광학기기 및 시계 제조업 (KSIC 27)",
            },
            {
                "name": "기타 기계 및 장비 제조업",
                "induty_code": "28",
                "description": "기타 기계 및 장비 제조업 (KSIC 28)",
            },
            {
                "name": "자동차 및 트레일러 제조업",
                "induty_code": "30",
                "description": "자동차 및 트레일러 제조업 (KSIC 30)",
            },
            {
                "name": "기타 운송장비 제조업",
                "induty_code": "31",
                "description": "기타 운송장비 제조업 (KSIC 31)",
            },
            {
                "name": "가구 제조업",
                "induty_code": "32",
                "description": "가구 제조업 (KSIC 32)",
            },
            {
                "name": "기타 제조업",
                "induty_code": "33",
                "description": "기타 제조업 (KSIC 33)",
            },
            # 건설업 (F)
            {
                "name": "건설업",
                "induty_code": "F",
                "description": "건설업 (KSIC 대분류)",
            },
            {
                "name": "건물 건설업",
                "induty_code": "41",
                "description": "건물 건설업 (KSIC 41)",
            },
            {
                "name": "토목 공사 건설업",
                "induty_code": "42",
                "description": "토목 공사 건설업 (KSIC 42)",
            },
            {
                "name": "전문 건설업",
                "induty_code": "43",
                "description": "전문 건설업 (KSIC 43)",
            },
            # 도매 및 소매업 (G)
            {
                "name": "도매 및 소매업",
                "induty_code": "G",
                "description": "도매 및 소매업 (KSIC 대분류)",
            },
            {
                "name": "자동차 및 부품 판매업",
                "induty_code": "45",
                "description": "자동차 및 부품 판매업 (KSIC 45)",
            },
            {"name": "도매업", "induty_code": "46", "description": "도매업 (KSIC 46)"},
            {"name": "소매업", "induty_code": "47", "description": "소매업 (KSIC 47)"},
            # 운수업 (H)
            {
                "name": "운수업",
                "induty_code": "H",
                "description": "운수업 (KSIC 대분류)",
            },
            {
                "name": "육상 운수 및 파이프라인 운수업",
                "induty_code": "49",
                "description": "육상 운수 및 파이프라인 운수업 (KSIC 49)",
            },
            {
                "name": "수상 운수업",
                "induty_code": "50",
                "description": "수상 운수업 (KSIC 50)",
            },
            {
                "name": "항공 운수업",
                "induty_code": "51",
                "description": "항공 운수업 (KSIC 51)",
            },
            {
                "name": "창고 및 운송 관련 서비스업",
                "induty_code": "52",
                "description": "창고 및 운송 관련 서비스업 (KSIC 52)",
            },
            # 숙박 및 음식점업 (I)
            {
                "name": "숙박 및 음식점업",
                "induty_code": "I",
                "description": "숙박 및 음식점업 (KSIC 대분류)",
            },
            {"name": "숙박업", "induty_code": "55", "description": "숙박업 (KSIC 55)"},
            {
                "name": "음식점 및 주점업",
                "induty_code": "56",
                "description": "음식점 및 주점업 (KSIC 56)",
            },
            # 정보통신업 (J)
            {
                "name": "정보통신업",
                "induty_code": "J",
                "description": "정보통신업 (KSIC 대분류)",
            },
            {"name": "출판업", "induty_code": "58", "description": "출판업 (KSIC 58)"},
            {
                "name": "영화, 비디오물, 방송프로그램 제조 및 배급업",
                "induty_code": "59",
                "description": "영화, 비디오물, 방송프로그램 제조 및 배급업 (KSIC 59)",
            },
            {"name": "방송업", "induty_code": "60", "description": "방송업 (KSIC 60)"},
            {
                "name": "전기통신업",
                "induty_code": "61",
                "description": "전기통신업 (KSIC 61)",
            },
            {
                "name": "컴퓨터 프로그래밍, 시스템 통합 및 관리업",
                "induty_code": "62",
                "description": "컴퓨터 프로그래밍, 시스템 통합 및 관리업 (KSIC 62)",
            },
            {
                "name": "정보서비스업",
                "induty_code": "63",
                "description": "정보서비스업 (KSIC 63)",
            },
            # 금융 및 보험업 (K)
            {
                "name": "금융 및 보험업",
                "induty_code": "K",
                "description": "금융 및 보험업 (KSIC 대분류)",
            },
            {"name": "금융업", "induty_code": "64", "description": "금융업 (KSIC 64)"},
            {"name": "보험업", "induty_code": "65", "description": "보험업 (KSIC 65)"},
            {
                "name": "금융투자업",
                "induty_code": "66",
                "description": "금융투자업 (KSIC 66)",
            },
            {
                "name": "기타 금융업",
                "induty_code": "67",
                "description": "기타 금융업 (KSIC 67)",
            },
            # 부동산업 (L)
            {
                "name": "부동산업",
                "induty_code": "L",
                "description": "부동산업 (KSIC 대분류)",
            },
            {
                "name": "부동산업",
                "induty_code": "68",
                "description": "부동산업 (KSIC 68)",
            },
            # 전문, 과학 및 기술 서비스업 (M)
            {
                "name": "전문, 과학 및 기술 서비스업",
                "induty_code": "M",
                "description": "전문, 과학 및 기술 서비스업 (KSIC 대분류)",
            },
            {
                "name": "법률 및 회계 서비스업",
                "induty_code": "69",
                "description": "법률 및 회계 서비스업 (KSIC 69)",
            },
            {
                "name": "건축 및 엔지니어링 서비스업",
                "induty_code": "71",
                "description": "건축 및 엔지니어링 서비스업 (KSIC 71)",
            },
            {
                "name": "연구개발업",
                "induty_code": "72",
                "description": "연구개발업 (KSIC 72)",
            },
            # 사업시설 관리, 사업지원 및 임대 서비스업 (N)
            {
                "name": "사업시설 관리, 사업지원 및 임대 서비스업",
                "induty_code": "N",
                "description": "사업시설 관리, 사업지원 및 임대 서비스업 (KSIC 대분류)",
            },
            {
                "name": "사업시설 관리, 사업지원 및 임대 서비스업",
                "induty_code": "81",
                "description": "사업시설 관리, 사업지원 및 임대 서비스업 (KSIC 81)",
            },
            # 교육 서비스업 (P)
            {
                "name": "교육 서비스업",
                "induty_code": "P",
                "description": "교육 서비스업 (KSIC 대분류)",
            },
            {
                "name": "교육 서비스업",
                "induty_code": "85",
                "description": "교육 서비스업 (KSIC 85)",
            },
            # 보건업 및 사회복지 서비스업 (Q)
            {
                "name": "보건업 및 사회복지 서비스업",
                "induty_code": "Q",
                "description": "보건업 및 사회복지 서비스업 (KSIC 대분류)",
            },
            {
                "name": "보건업 및 사회복지 서비스업",
                "induty_code": "86",
                "description": "보건업 및 사회복지 서비스업 (KSIC 86)",
            },
            # 예술, 스포츠 및 여가관련 서비스업 (R)
            {
                "name": "예술, 스포츠 및 여가관련 서비스업",
                "induty_code": "R",
                "description": "예술, 스포츠 및 여가관련 서비스업 (KSIC 대분류)",
            },
            {
                "name": "예술, 스포츠 및 여가관련 서비스업",
                "induty_code": "90",
                "description": "예술, 스포츠 및 여가관련 서비스업 (KSIC 90)",
            },
            # 협회 및 단체, 수리 및 기타 개인 서비스업 (S)
            {
                "name": "협회 및 단체, 수리 및 기타 개인 서비스업",
                "induty_code": "S",
                "description": "협회 및 단체, 수리 및 기타 개인 서비스업 (KSIC 대분류)",
            },
            {
                "name": "협회 및 단체, 수리 및 기타 개인 서비스업",
                "induty_code": "94",
                "description": "협회 및 단체, 수리 및 기타 개인 서비스업 (KSIC 94)",
            },
            # 기타
            {
                "name": "기타",
                "induty_code": None,
                "description": "기타 산업 (분류되지 않은 산업)",
            },
        ]

        if reset:
            self.stdout.write(self.style.WARNING("기존 산업 데이터 삭제 중..."))
            Industry.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("기존 산업 데이터 삭제 완료"))

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
