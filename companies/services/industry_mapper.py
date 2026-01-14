# companies/services/industry_mapper.py
"""
업종코드와 Industry 매핑 서비스
DART API의 업종코드를 Industry 모델과 매핑하는 서비스
"""
from typing import Optional
import logging

from industries.models import Industry

logger = logging.getLogger(__name__)


class IndustryMapper:
    """업종코드와 Industry 매핑 서비스"""

    # DART 업종코드 → Industry 이름 매핑
    # 참고: DART API는 한국표준산업분류(KSIC) 코드를 사용
    # DART API는 숫자 형식(예: "264") 또는 문자 형식(예: "C26")으로 반환할 수 있음
    # 주요 업종코드 매핑 (실제 DART 응답에 따라 조정 필요)
    INDUSTRY_CODE_MAP = {
        # 제조업 (문자 형식)
        "C": "제조업",
        "C26": "전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업",
        "C27": "의료, 정밀, 광학기기 및 시계 제조업",
        "C28": "전기장비 제조업",
        "C29": "기타 기계 및 장비 제조업",
        # 제조업 (숫자 형식 - KSIC 코드)
        "26": "전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업",  # 26으로 시작하는 모든 코드
        "264": "전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업",
        "2641": "반도체 제조업",
        "2642": "디스플레이 패널 제조업",
        "26410": "반도체 제조업",
        "26429": "기타 디스플레이 패널 제조업",
        "265": "의료, 정밀, 광학기기 및 시계 제조업",
        "27": "전기장비 제조업",  # 27로 시작하는 모든 코드
        "271": "전기장비 제조업",
        "272": "기타 기계 및 장비 제조업",
        "28": "기타 기계 및 장비 제조업",  # 28로 시작하는 모든 코드
        "29": "기타 기계 및 장비 제조업",  # 29로 시작하는 모든 코드
        "10": "식품제조업",
        "11": "음료제조업",
        "13": "섬유제품 제조업",
        "14": "의복의류 제조업",
        "15": "가죽, 가방 및 신발 제조업",
        "16": "목재 및 나무제품 제조업",
        "17": "펄프, 종이 및 종이제품 제조업",
        "18": "인쇄 및 기록매체 복제업",
        "20": "화학물질 및 화학제품 제조업",
        "21": "의료용 물질 및 의약품 제조업",
        "22": "고무제품 및 플라스틱제품 제조업",
        "23": "비금속 광물제품 제조업",
        "24": "1차 금속 제조업",
        "25": "금속가공제품 제조업",
        "30": "자동차 및 트레일러 제조업",
        "31": "기타 운송장비 제조업",
        "32": "가구 제조업",
        "33": "기타 제조업",
        # 정보통신업
        "J": "정보통신업",
        "J58": "출판업",
        "J59": "영화, 비디오물, 방송프로그램 제조 및 배급업",
        "J60": "방송업",
        "J61": "전기통신업",
        "J62": "컴퓨터 프로그래밍, 시스템 통합 및 관리업",
        "J63": "정보서비스업",
        "58": "출판업",
        "59": "영화, 비디오물, 방송프로그램 제조 및 배급업",
        "60": "방송업",
        "61": "전기통신업",
        "62": "컴퓨터 프로그래밍, 시스템 통합 및 관리업",
        "63": "정보서비스업",
        # 금융 및 보험업
        "K": "금융 및 보험업",
        "K64": "금융업",
        "K65": "보험업",
        "K66": "금융투자업",
        "64": "금융업",
        "65": "보험업",
        "66": "금융투자업",
        # 전문, 과학 및 기술 서비스업
        "M": "전문, 과학 및 기술 서비스업",
        "M70": "연구개발업",
        "M71": "전문 서비스업",
        "70": "연구개발업",
        "71": "전문 서비스업",
        # 기타
        "G": "도매 및 소매업",
        "H": "운수업",
        "I": "숙박 및 음식점업",
        "L": "부동산업",
        "N": "사업시설 관리, 사업지원 및 임대 서비스업",
        "O": "공공행정, 국방 및 사회보장 행정",
        "P": "교육 서비스업",
        "Q": "보건업 및 사회복지 서비스업",
        "R": "예술, 스포츠 및 여가관련 서비스업",
        "S": "협회 및 단체, 수리 및 기타 개인 서비스업",
    }

    @classmethod
    def get_industry_by_code(cls, industry_code: Optional[str]) -> Optional[Industry]:
        """
        업종코드로 Industry 찾기 또는 생성

        Args:
            industry_code: DART API의 업종코드 (예: "C26", "J62")

        Returns:
            Industry 인스턴스 또는 None
        """
        if not industry_code:
            return None

        # 업종코드 정규화 (앞뒤 공백 제거, 대문자 변환)
        industry_code = industry_code.strip().upper()

        # 1. 업종코드로 직접 Industry 찾기
        industry = Industry.objects.filter(
            induty_code=industry_code, is_deleted=False
        ).first()
        if industry:
            return industry

        # 2. 상위 분류 코드로 찾기 (예: "26410" → "264" → "26")
        for code_length in range(len(industry_code) - 1, 0, -1):
            parent_code = industry_code[:code_length]
            industry = Industry.objects.filter(
                induty_code=parent_code, is_deleted=False
            ).first()
            if industry:
                logger.debug(
                    f"업종코드 '{industry_code}'를 상위 코드 '{parent_code}'로 매핑"
                )
                return industry

        # 3. 매핑 테이블에서 Industry 이름 찾기 (fallback - DB에 업종코드가 없는 경우)
        industry_name = cls.INDUSTRY_CODE_MAP.get(industry_code)

        if not industry_name:
            # 정확한 매칭이 없으면 상위 분류 코드로 시도
            # 예: "26410" → "2641" → "264" → "26"
            for code_length in range(len(industry_code) - 1, 0, -1):
                parent_code = industry_code[:code_length]
                # 먼저 DB에서 상위 코드로 찾기 시도
                industry = Industry.objects.filter(
                    induty_code=parent_code, is_deleted=False
                ).first()
                if industry:
                    logger.debug(
                        f"업종코드 '{industry_code}'를 상위 코드 '{parent_code}'로 매핑 (DB)"
                    )
                    return industry
                # 매핑 테이블에서도 확인
                industry_name = cls.INDUSTRY_CODE_MAP.get(parent_code)
                if industry_name:
                    break

        # 4. 여전히 매핑이 없으면 숫자 코드의 첫 자리로 대분류 시도
        if not industry_name and industry_code and industry_code[0].isdigit():
            first_digit = industry_code[0]
            # KSIC 대분류 매핑
            major_category_map = {
                "1": "제조업",  # 10-33
                "2": "제조업",  # 20-33
                "3": "제조업",  # 30-33
                "4": "건설업",  # 41-43
                "5": "도매 및 소매업",  # 46-47
                "6": "운수업",  # 49-53
                "7": "숙박 및 음식점업",  # 55-56
                "8": "정보통신업",  # 58-63
                "9": "금융 및 보험업",  # 64-66
            }
            major_category = major_category_map.get(first_digit)
            if major_category:
                # 대분류로 DB에서 찾기 시도
                industry = Industry.objects.filter(
                    name=major_category, is_deleted=False
                ).first()
                if industry:
                    logger.debug(
                        f"업종코드 '{industry_code}'를 대분류 '{major_category}'로 매핑"
                    )
                    return industry
                industry_name = major_category

        if not industry_name:
            # 로그를 디버그 레벨로 변경 (너무 많은 경고 방지)
            logger.debug(f"업종코드 '{industry_code}'에 대한 매핑을 찾을 수 없습니다.")
            return None

        # Industry 찾기 또는 생성 (이름으로 찾고, 업종코드 업데이트)
        # 업종코드로 먼저 찾기 시도 (같은 이름이지만 다른 업종코드일 수 있음)
        industry = Industry.objects.filter(name=industry_name, is_deleted=False).first()

        if industry:
            # 기존 Industry에 업종코드가 없으면 업데이트
            if not industry.induty_code:
                industry.induty_code = industry_code
                industry.save()
                logger.debug(
                    f"기존 Industry '{industry_name}'에 업종코드 '{industry_code}' 추가"
                )
            return industry
        else:
            # 새 Industry 생성
            industry = Industry.objects.create(
                name=industry_name,
                induty_code=industry_code,
                description=f"업종코드: {industry_code}",
            )
            logger.info(f"새 산업 생성: {industry_name} (업종코드: {industry_code})")
            return industry

    @classmethod
    def get_default_industry(cls) -> Optional[Industry]:
        """
        기본 Industry 반환 (매핑 실패 시 사용)

        Returns:
            첫 번째 Industry 또는 None
        """
        return Industry.objects.first()
