"""기업-산업 매핑 규칙

KSIC(한국표준산업분류) 코드를 KIS 업종 코드로 변환하는 규칙을 정의합니다.
통계 기반 자동 매핑 대신 명시적 규칙 기반 매핑을 사용합니다.
"""

import logging

logger = logging.getLogger(__name__)


class KISIndustryCode:
    """KIS 업종 코드 상수 (KOSPI 기본 업종)"""

    FOOD_TOBACCO = "0005"  # 음식료·담배
    TEXTILE = "0006"  # 섬유·의류
    PAPER_WOOD = "0007"  # 종이·목재
    CHEMICAL = "0008"  # 화학
    PHARMACEUTICAL = "0009"  # 제약
    NON_METAL = "0010"  # 비금속
    METAL = "0011"  # 금속
    MACHINERY = "0012"  # 기계·장비
    ELECTRICAL = "0013"  # 전기·전자 (반도체 포함)
    MEDICAL_PRECISION = "0014"  # 의료·정밀기기
    TRANSPORT_EQUIP = "0015"  # 운송장비·부품
    DISTRIBUTION = "0016"  # 유통
    ELECTRIC_GAS = "0017"  # 전기·가스
    CONSTRUCTION = "0018"  # 건설
    TRANSPORT = "0019"  # 운송·창고
    TELECOM = "0020"  # 통신
    FINANCIAL = "0021"  # 금융
    SECURITIES = "0024"  # 증권
    INSURANCE = "0025"  # 보험
    SERVICE = "0026"  # 일반서비스
    MANUFACTURING = "0027"  # 제조 (기타)
    REAL_ESTATE = "0028"  # 부동산
    IT_SERVICE = "0029"  # IT 서비스
    ENTERTAINMENT = "0030"  # 오락·문화


class IndustryMappingRules:
    """KSIC 코드 기반 Industry 매핑 규칙

    KSIC 코드의 앞 2자리(대분류)를 기준으로 KIS 업종 코드로 매핑합니다.
    특수한 경우 3자리(중분류)로 예외 처리합니다.
    """

    # KSIC 앞 2자리 → KIS 업종 코드 기본 매핑
    DEFAULT_MAPPINGS = {
        # ========================================
        # 제조업 (KSIC 10-33)
        # ========================================
        # 식품/음료/담배 (10-12)
        "10": KISIndustryCode.FOOD_TOBACCO,  # 식료품 제조업
        "11": KISIndustryCode.FOOD_TOBACCO,  # 음료 제조업
        "12": KISIndustryCode.FOOD_TOBACCO,  # 담배 제조업
        # 섬유/의류/가죽 (13-15)
        "13": KISIndustryCode.TEXTILE,  # 섬유제품 제조업
        "14": KISIndustryCode.TEXTILE,  # 의복, 의복액세서리 및 모피제품 제조업
        "15": KISIndustryCode.TEXTILE,  # 가죽, 가방 및 신발 제조업
        # 목재/종이/인쇄 (16-18)
        "16": KISIndustryCode.PAPER_WOOD,  # 목재 및 나무제품 제조업
        "17": KISIndustryCode.PAPER_WOOD,  # 펄프, 종이 및 종이제품 제조업
        "18": KISIndustryCode.PAPER_WOOD,  # 인쇄 및 기록매체 복제업
        # 화학/석유 (19-22)
        "19": KISIndustryCode.CHEMICAL,  # 코크스, 연탄 및 석유정제품 제조업
        "20": KISIndustryCode.CHEMICAL,  # 화학물질 및 화학제품 제조업
        "21": KISIndustryCode.PHARMACEUTICAL,  # 의료용 물질 및 의약품 제조업
        "22": KISIndustryCode.CHEMICAL,  # 고무 및 플라스틱제품 제조업
        # 비금속/금속 (23-25)
        "23": KISIndustryCode.NON_METAL,  # 비금속 광물제품 제조업
        "24": KISIndustryCode.METAL,  # 1차 금속 제조업
        "25": KISIndustryCode.METAL,  # 금속가공제품 제조업
        # 전자/전기/정밀 (26-28)
        "26": KISIndustryCode.ELECTRICAL,  # 전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업
        "27": KISIndustryCode.MEDICAL_PRECISION,  # 의료, 정밀, 광학기기 및 시계 제조업
        "28": KISIndustryCode.ELECTRICAL,  # 전기장비 제조업
        # 기계/운송장비 (29-31)
        "29": KISIndustryCode.MACHINERY,  # 기타 기계 및 장비 제조업
        "30": KISIndustryCode.TRANSPORT_EQUIP,  # 자동차 및 트레일러 제조업
        "31": KISIndustryCode.TRANSPORT_EQUIP,  # 기타 운송장비 제조업
        # 가구/기타제조 (32-33)
        "32": KISIndustryCode.MANUFACTURING,  # 가구 제조업
        "33": KISIndustryCode.MANUFACTURING,  # 기타 제품 제조업
        # ========================================
        # 전기/가스/수도/건설 (35-43)
        # ========================================
        "35": KISIndustryCode.ELECTRIC_GAS,  # 전기, 가스, 증기 및 공기조절 공급업
        "36": KISIndustryCode.ELECTRIC_GAS,  # 수도사업
        "37": KISIndustryCode.SERVICE,  # 하수, 폐수 및 분뇨 처리업
        "38": KISIndustryCode.SERVICE,  # 폐기물 수집운반, 처리 및 원료재생업
        "39": KISIndustryCode.SERVICE,  # 환경 정화 및 복원업
        "41": KISIndustryCode.CONSTRUCTION,  # 종합 건설업
        "42": KISIndustryCode.CONSTRUCTION,  # 전문직별 공사업
        "43": KISIndustryCode.CONSTRUCTION,  # 건물 설비 설치 공사업
        # ========================================
        # 도소매 (45-47)
        # ========================================
        "45": KISIndustryCode.DISTRIBUTION,  # 자동차 및 부품 판매업
        "46": KISIndustryCode.DISTRIBUTION,  # 도매 및 상품 중개업
        "47": KISIndustryCode.DISTRIBUTION,  # 소매업
        # ========================================
        # 운수/창고 (49-52)
        # ========================================
        "49": KISIndustryCode.TRANSPORT,  # 육상운송 및 파이프라인 운송업
        "50": KISIndustryCode.TRANSPORT,  # 수상 운송업
        "51": KISIndustryCode.TRANSPORT,  # 항공 운송업
        "52": KISIndustryCode.TRANSPORT,  # 창고 및 운송관련 서비스업
        # ========================================
        # 숙박/음식 (55-56)
        # ========================================
        "55": KISIndustryCode.SERVICE,  # 숙박업
        "56": KISIndustryCode.SERVICE,  # 음식점 및 주점업
        # ========================================
        # 정보통신 (58-63)
        # ========================================
        "58": KISIndustryCode.IT_SERVICE,  # 출판업
        "59": KISIndustryCode.ENTERTAINMENT,  # 영상·오디오 기록물 제작 및 배급업
        "60": KISIndustryCode.TELECOM,  # 방송업
        "61": KISIndustryCode.TELECOM,  # 우편 및 통신업
        "62": KISIndustryCode.IT_SERVICE,  # 컴퓨터 프로그래밍, 시스템 통합 및 관리업
        "63": KISIndustryCode.IT_SERVICE,  # 정보서비스업
        # ========================================
        # 금융/보험 (64-66)
        # ========================================
        "64": KISIndustryCode.FINANCIAL,  # 금융업
        "65": KISIndustryCode.INSURANCE,  # 보험 및 연금업
        "66": KISIndustryCode.FINANCIAL,  # 금융 및 보험 관련 서비스업
        # ========================================
        # 부동산 (68)
        # ========================================
        "68": KISIndustryCode.REAL_ESTATE,  # 부동산업
        # ========================================
        # 전문/과학/기술 서비스 (70-73)
        # ========================================
        "70": KISIndustryCode.SERVICE,  # 연구개발업
        "71": KISIndustryCode.SERVICE,  # 전문서비스업
        "72": KISIndustryCode.SERVICE,  # 건축기술, 엔지니어링 및 기타 과학기술 서비스업
        "73": KISIndustryCode.SERVICE,  # 기타 전문, 과학 및 기술 서비스업
        # ========================================
        # 사업시설관리/사업지원/임대 (74-76)
        # ========================================
        "74": KISIndustryCode.SERVICE,  # 사업시설 관리 및 조경 서비스업
        "75": KISIndustryCode.SERVICE,  # 사업 지원 서비스업
        "76": KISIndustryCode.SERVICE,  # 임대업
        # ========================================
        # 공공행정/교육/보건 (84-87)
        # ========================================
        "84": KISIndustryCode.SERVICE,  # 공공행정, 국방 및 사회보장 행정
        "85": KISIndustryCode.SERVICE,  # 교육 서비스업
        "86": KISIndustryCode.SERVICE,  # 보건업
        "87": KISIndustryCode.SERVICE,  # 사회복지 서비스업
        # ========================================
        # 예술/스포츠/여가 (90-91)
        # ========================================
        "90": KISIndustryCode.ENTERTAINMENT,  # 창작, 예술 및 여가관련 서비스업
        "91": KISIndustryCode.ENTERTAINMENT,  # 스포츠 및 오락관련 서비스업
        # ========================================
        # 기타 (94-99)
        # ========================================
        "94": KISIndustryCode.SERVICE,  # 협회 및 단체
        "95": KISIndustryCode.SERVICE,  # 수리업
        "96": KISIndustryCode.SERVICE,  # 기타 개인 서비스업
    }

    # KSIC 3자리 예외 매핑 (DEFAULT_MAPPINGS보다 우선)
    EXCEPTION_MAPPINGS = {
        # ========================================
        # 금융업 세분화 (KSIC 64)
        # ========================================
        "641": KISIndustryCode.FINANCIAL,  # 은행업 → 금융
        "642": KISIndustryCode.FINANCIAL,  # 저축기관 → 금융
        "643": KISIndustryCode.FINANCIAL,  # 신용카드업 → 금융
        "649": KISIndustryCode.FINANCIAL,  # 기타 금융업 → 금융
        # ========================================
        # 증권업 (KSIC 66)
        # ========================================
        "661": KISIndustryCode.SECURITIES,  # 금융투자업 → 증권
        "662": KISIndustryCode.FINANCIAL,  # 금융지원 서비스업 → 금융
        "663": KISIndustryCode.INSURANCE,  # 보험대리 및 중개업 → 보험
        # ========================================
        # 보험업 세분화 (KSIC 65)
        # ========================================
        "651": KISIndustryCode.INSURANCE,  # 보험업 → 보험
        "652": KISIndustryCode.INSURANCE,  # 재보험업 → 보험
        "653": KISIndustryCode.INSURANCE,  # 공제업 → 보험
        # ========================================
        # 방송/통신 세분화 (KSIC 60-61)
        # ========================================
        "601": KISIndustryCode.ENTERTAINMENT,  # 라디오 방송업 → 오락·문화
        "602": KISIndustryCode.ENTERTAINMENT,  # TV 방송업 → 오락·문화
        "612": KISIndustryCode.TELECOM,  # 전기통신업 → 통신
        # ========================================
        # 게임/엔터테인먼트 (KSIC 58-59)
        # ========================================
        "582": KISIndustryCode.IT_SERVICE,  # 소프트웨어 개발 및 공급업 → IT서비스
        "591": KISIndustryCode.ENTERTAINMENT,  # 영화/비디오물 제작 → 오락·문화
        "592": KISIndustryCode.ENTERTAINMENT,  # 음악 기록물 제작업 → 오락·문화
    }

    @classmethod
    def get_kis_code(cls, ksic_code: str) -> str | None:
        """KSIC 코드로 KIS 업종 코드 조회

        Args:
            ksic_code: KSIC 코드 (3-5자리)

        Returns:
            KIS 업종 코드 또는 None
        """
        if not ksic_code:
            return None

        # 숫자만 추출 (알파벳 prefix 제거)
        ksic_code = "".join(filter(str.isdigit, str(ksic_code)))

        if len(ksic_code) < 2:
            return None

        # 1. 예외 매핑 확인 (3자리)
        if len(ksic_code) >= 3:
            prefix_3 = ksic_code[:3]
            if prefix_3 in cls.EXCEPTION_MAPPINGS:
                return cls.EXCEPTION_MAPPINGS[prefix_3]

        # 2. 기본 매핑 확인 (2자리)
        prefix_2 = ksic_code[:2]
        return cls.DEFAULT_MAPPINGS.get(prefix_2)

    @classmethod
    def get_all_kis_codes(cls) -> set[str]:
        """매핑에 사용되는 모든 KIS 업종 코드 반환"""
        codes = set(cls.DEFAULT_MAPPINGS.values())
        codes.update(cls.EXCEPTION_MAPPINGS.values())
        return codes


class SpecialCompanyMappings:
    """특수 기업별 수동 매핑

    KSIC 규칙으로 정확하게 매핑되지 않는 특수한 경우에 사용합니다.
    지주회사, 복합 사업 기업 등이 해당됩니다.
    """

    # 종목코드 → KIS 업종 코드
    MANUAL_MAPPINGS = {
        # 지주회사 (주력 사업 기준 매핑)
        # - SK, LG 등 지주회사는 대표 사업 기준으로 매핑
        # 필요 시 여기에 추가
    }

    @classmethod
    def get_kis_code(cls, stock_code: str) -> str | None:
        """종목코드로 수동 매핑된 KIS 업종 코드 조회

        Args:
            stock_code: 종목코드 (6자리)

        Returns:
            KIS 업종 코드 또는 None
        """
        return cls.MANUAL_MAPPINGS.get(stock_code)


def get_industry_kis_code(stock_code: str, ksic_code: str) -> str | None:
    """기업의 KIS 업종 코드 조회

    1. 수동 매핑 확인 (특수 기업)
    2. KSIC 규칙 기반 매핑

    Args:
        stock_code: 종목코드
        ksic_code: KSIC 코드

    Returns:
        KIS 업종 코드 또는 None
    """
    # 1. 수동 매핑 확인
    kis_code = SpecialCompanyMappings.get_kis_code(stock_code)
    if kis_code:
        logger.debug(f"수동 매핑 적용: {stock_code} → {kis_code}")
        return kis_code

    # 2. KSIC 규칙 기반 매핑
    kis_code = IndustryMappingRules.get_kis_code(ksic_code)
    if kis_code:
        logger.debug(f"KSIC 규칙 매핑: {ksic_code} → {kis_code}")
        return kis_code

    logger.warning(f"매핑 실패: {stock_code}, KSIC={ksic_code}")
    return None
