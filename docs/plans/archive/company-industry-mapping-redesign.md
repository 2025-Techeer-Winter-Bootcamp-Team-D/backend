# 기업-산업 매핑 로직 재설계 계획서

## 배경 및 문제 정의

### 현재 상황

1. **복잡한 매핑 체인**
   ```
   DART API (KSIC 코드) → KsicCategory → KisIndustry → Industry → Company
   ```
   - 여러 단계를 거치면서 매핑 정확도가 낮아짐

2. **통계 기반 자동 매핑의 실패**
   - KIS 마스터 파일에서 종목별 업종코드를 파싱
   - 같은 KSIC 코드를 가진 기업들의 KIS 업종코드를 통계적으로 집계
   - 가장 많이 나타나는 KIS 코드를 해당 KSIC의 대표 코드로 지정
   - **문제**: 금융업(KSIC 64-66)에 제조업 기업이 매핑되는 등 논리적 오류 발생

3. **KIS 마스터 파일 파싱의 불확실성**
   - 바이너리 파일의 오프셋(line[61:63], line[68:72])이 정확하지 않을 수 있음
   - 인코딩 오류를 무시하면서 파싱 (`errors="ignore"`)

4. **수동 매핑 테이블의 과도한 복잡성**
   - `KsicKisManualMapping` 클래스에 200개 이상의 매핑 룰
   - 유지보수가 어렵고, 새로운 KSIC 코드 추가 시 수동 업데이트 필요

### 근본 원인

**KSIC(한국표준산업분류)와 KIS(한국투자증권 업종지수)는 서로 다른 목적의 분류 체계**

| 구분 | KSIC | KIS |
|------|------|-----|
| 목적 | 통계청 표준 산업 분류 | 증권사 투자 분석용 업종 지수 |
| 분류 수 | 500개 이상 (5자리 세분류) | 약 30개 (대/중분류) |
| 관점 | 생산 활동 기준 | 투자 섹터 기준 |
| 예시 | "264" (반도체 제조업) | "0009" (반도체) |

두 분류 체계를 1:1로 매핑하려는 시도 자체가 근본적인 문제였습니다.

---

## 재설계 목표

### 핵심 원칙

1. **단순화**: 불필요한 중간 단계 제거
2. **명시적 매핑**: 자동 통계 기반 대신 명시적 규칙 기반
3. **분리 관심사**: 기업-산업 연결과 산업-지수 연결을 별도로 관리
4. **유연성**: 향후 분류 체계 변경에 유연하게 대응

### 성공 기준

- [ ] 대표 기업 30개 샘플의 산업 매핑 정확도 100%
- [ ] 전체 기업의 90% 이상이 적절한 Industry에 연결
- [ ] KIS 산업 지수 차트 데이터 정상 조회 가능
- [ ] 매핑 로직 코드 라인 수 50% 감소

---

## 설계 옵션

### Option A: KIS 지수 기반 단순화 (권장)

**핵심 아이디어**: Industry 테이블을 KIS 업종 지수와 1:1 매칭

```
[데이터 흐름]
1. DART API → Company.original_ksic_code (원본 보관)
2. KIS 마스터 → Industry (KIS 업종 지수 = Industry)
3. Company ↔ Industry (KSIC 코드 기반 규칙 매핑)
```

**장점**:
- Industry 테이블이 곧 KIS 업종 지수이므로 차트 연동이 자연스러움
- 분류 체계가 단순 (약 30개 산업)
- 투자자 관점에서 익숙한 분류

**단점**:
- KSIC 코드의 세부 분류 정보를 활용하기 어려움
- KIS 지수에 없는 산업은 표현 불가

### Option B: KSIC 기반 자체 분류

**핵심 아이디어**: KSIC 대분류(2자리)를 Industry로 사용

```
[데이터 흐름]
1. DART API → Company.original_ksic_code
2. KSIC 대분류 → Industry (21개 대분류)
3. Industry ↔ KisIndustry (별도 매핑 테이블)
```

**장점**:
- 국가 표준 분류 체계 사용
- KSIC 코드에서 Industry 자동 유추 가능 (앞 2자리)

**단점**:
- KIS 지수 연동을 위해 추가 매핑 필요
- 투자 관점과 불일치 (예: "제조업"이 너무 넓음)

### Option C: 하이브리드 (자체 정의 산업 분류)

**핵심 아이디어**: 우리 서비스에 최적화된 산업 분류 직접 정의

```
[데이터 흐름]
1. DART API → Company.original_ksic_code
2. 자체 정의 → Industry (우리가 정의한 산업 목록)
3. Company ↔ Industry (KSIC 규칙 + 예외 처리)
4. Industry ↔ KisIndustry (N:M 매핑, 선택적)
```

**장점**:
- 서비스 목적에 맞는 최적 분류 가능
- 유연한 확장 가능

**단점**:
- 초기 산업 목록 정의 필요
- KIS 지수와의 매핑 복잡도 증가

---

## 권장 설계: Option A (KIS 지수 기반 단순화)

### 1. 모델 재설계

#### 1.1 테이블 구조 (변경 후)

```
┌─────────────────────────────────────────────────────────────┐
│                        Company                               │
├─────────────────────────────────────────────────────────────┤
│ stock_code (PK)          # 종목코드                          │
│ company_name             # 기업명                            │
│ original_ksic_code       # DART 원본 KSIC 코드 (보관용)      │
│ industry_id (FK)         # Industry 연결                     │
│ market                   # KOSPI/KOSDAQ                      │
│ ...                                                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Industry                              │
├─────────────────────────────────────────────────────────────┤
│ industry_id (PK)         # 산업 ID                           │
│ kis_code (UNIQUE)        # KIS 업종 코드 (0009, 0014 등)     │
│ name                     # 산업명 (반도체, 전기전자 등)       │
│ description              # 설명                              │
│ display_order            # 표시 순서 (선택)                  │
└─────────────────────────────────────────────────────────────┘
```

#### 1.2 제거 대상 테이블/필드

- `KsicCategory` 테이블 → **삭제**
- `KisIndustry` 테이블 → `Industry`로 통합
- `Company.induty_code` → `original_ksic_code`로 대체 (또는 제거)

#### 1.3 마이그레이션 계획

```python
# companies/migrations/XXXX_simplify_industry_mapping.py

# 1. Industry 테이블에 kis_code 필드 추가 (이미 induty_code로 존재하면 rename)
# 2. KisIndustry 데이터를 Industry로 마이그레이션
# 3. Company.induty_code 제거 (original_ksic_code 사용)
# 4. KsicCategory 테이블 삭제
# 5. KisIndustry 테이블 삭제 (Industry로 통합됨)
```

### 2. 매핑 규칙 정의

#### 2.1 KSIC → Industry 매핑 규칙

**원칙**: KSIC 앞 2자리 기반 규칙 + 예외 처리

```python
# companies/services/industry_mapping_rules.py

class IndustryMappingRules:
    """KSIC 코드 기반 Industry 매핑 규칙"""

    # KIS 업종 코드 상수
    class KIS:
        FOOD_TOBACCO = "0005"       # 음식료·담배
        TEXTILE = "0006"            # 섬유의복
        PAPER_WOOD = "0007"         # 종이목재
        CHEMICAL = "0008"           # 화학
        PHARMACEUTICAL = "0009"     # 제약
        NON_METAL = "0010"          # 비금속
        STEEL = "0011"              # 철강
        MACHINERY = "0012"          # 기계
        ELECTRICAL = "0014"         # 전기전자
        TRANSPORT_EQUIP = "0015"    # 운송장비·부품
        DISTRIBUTION = "0016"       # 유통
        ELECTRIC_GAS = "0017"       # 전기가스
        CONSTRUCTION = "0018"       # 건설
        TRANSPORT = "0019"          # 운수창고
        TELECOM = "0020"            # 통신
        FINANCIAL = "0021"          # 금융
        BANK = "0022"               # 은행
        SECURITIES = "0023"         # 증권
        INSURANCE = "0024"          # 보험
        SERVICE = "0026"            # 서비스
        SEMICONDUCTOR = "0027"      # 반도체 (실제 KIS 코드 확인 필요)

    # KSIC 앞 2자리 → KIS 업종 코드 매핑
    DEFAULT_MAPPINGS = {
        # 제조업 (KSIC 10-33)
        "10": KIS.FOOD_TOBACCO,    # 식료품 제조업
        "11": KIS.FOOD_TOBACCO,    # 음료 제조업
        "12": KIS.FOOD_TOBACCO,    # 담배 제조업
        "13": KIS.TEXTILE,         # 섬유제품 제조업
        "14": KIS.TEXTILE,         # 의복, 의복액세서리 및 모피제품 제조업
        "15": KIS.TEXTILE,         # 가죽, 가방 및 신발 제조업
        "16": KIS.PAPER_WOOD,      # 목재 및 나무제품 제조업
        "17": KIS.PAPER_WOOD,      # 펄프, 종이 및 종이제품 제조업
        "19": KIS.CHEMICAL,        # 코크스, 연탄 및 석유정제품 제조업
        "20": KIS.CHEMICAL,        # 화학물질 및 화학제품 제조업
        "21": KIS.PHARMACEUTICAL,  # 의료용 물질 및 의약품 제조업
        "22": KIS.CHEMICAL,        # 고무 및 플라스틱제품 제조업
        "23": KIS.NON_METAL,       # 비금속 광물제품 제조업
        "24": KIS.STEEL,           # 1차 금속 제조업
        "25": KIS.STEEL,           # 금속가공제품 제조업
        "26": KIS.ELECTRICAL,      # 전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업
        "27": KIS.ELECTRICAL,      # 의료, 정밀, 광학기기 및 시계 제조업
        "28": KIS.ELECTRICAL,      # 전기장비 제조업
        "29": KIS.MACHINERY,       # 기타 기계 및 장비 제조업
        "30": KIS.TRANSPORT_EQUIP, # 자동차 및 트레일러 제조업
        "31": KIS.TRANSPORT_EQUIP, # 기타 운송장비 제조업

        # 전기/가스/건설 (KSIC 35, 41-43)
        "35": KIS.ELECTRIC_GAS,    # 전기, 가스, 증기 및 공기조절 공급업
        "41": KIS.CONSTRUCTION,    # 종합 건설업
        "42": KIS.CONSTRUCTION,    # 전문직별 공사업

        # 도소매 (KSIC 45-47)
        "45": KIS.DISTRIBUTION,    # 자동차 및 부품 판매업
        "46": KIS.DISTRIBUTION,    # 도매 및 상품 중개업
        "47": KIS.DISTRIBUTION,    # 소매업

        # 운수/창고 (KSIC 49-52)
        "49": KIS.TRANSPORT,       # 육상운송 및 파이프라인 운송업
        "50": KIS.TRANSPORT,       # 수상 운송업
        "51": KIS.TRANSPORT,       # 항공 운송업
        "52": KIS.TRANSPORT,       # 창고 및 운송관련 서비스업

        # 정보통신 (KSIC 58-63)
        "58": KIS.SERVICE,         # 출판업
        "59": KIS.SERVICE,         # 영상·오디오 기록물 제작 및 배급업
        "60": KIS.TELECOM,         # 방송업
        "61": KIS.TELECOM,         # 우편 및 통신업
        "62": KIS.SERVICE,         # 컴퓨터 프로그래밍, 시스템 통합 및 관리업
        "63": KIS.SERVICE,         # 정보서비스업

        # 금융/보험 (KSIC 64-66)
        "64": KIS.FINANCIAL,       # 금융업
        "65": KIS.INSURANCE,       # 보험 및 연금업
        "66": KIS.FINANCIAL,       # 금융 및 보험 관련 서비스업

        # 부동산/서비스 (KSIC 68-82)
        "68": KIS.SERVICE,         # 부동산업
        "70": KIS.SERVICE,         # 연구개발업
        "71": KIS.SERVICE,         # 전문서비스업
        "72": KIS.SERVICE,         # 건축기술, 엔지니어링 및 기타 과학기술 서비스업
        "73": KIS.SERVICE,         # 기타 전문, 과학 및 기술 서비스업
    }

    # KSIC 3자리 예외 매핑 (DEFAULT_MAPPINGS보다 우선)
    EXCEPTION_MAPPINGS = {
        # 반도체는 전기전자(26)이지만 별도 분류가 필요한 경우
        "261": KIS.SEMICONDUCTOR,  # 반도체 제조업 (전자부품)
        "264": KIS.SEMICONDUCTOR,  # 반도체 제조업

        # 은행/증권/보험 세분화
        "641": KIS.BANK,           # 은행업
        "642": KIS.BANK,           # 저축기관
        "661": KIS.SECURITIES,     # 금융투자업 (증권)
        "651": KIS.INSURANCE,      # 보험업
        "652": KIS.INSURANCE,      # 재보험업
    }

    @classmethod
    def get_kis_code(cls, ksic_code: str) -> str | None:
        """KSIC 코드로 KIS 업종 코드 조회

        Args:
            ksic_code: KSIC 코드 (3-5자리)

        Returns:
            KIS 업종 코드 또는 None
        """
        if not ksic_code or len(ksic_code) < 2:
            return None

        # 1. 예외 매핑 확인 (3자리)
        if len(ksic_code) >= 3:
            prefix_3 = ksic_code[:3]
            if prefix_3 in cls.EXCEPTION_MAPPINGS:
                return cls.EXCEPTION_MAPPINGS[prefix_3]

        # 2. 기본 매핑 확인 (2자리)
        prefix_2 = ksic_code[:2]
        return cls.DEFAULT_MAPPINGS.get(prefix_2)
```

#### 2.2 특수 기업 수동 매핑 (예외 처리)

```python
# companies/services/industry_mapping_rules.py (계속)

class SpecialCompanyMappings:
    """특수한 경우의 기업별 수동 매핑"""

    # 종목코드 → KIS 업종 코드 (KSIC 규칙으로 해결 안 되는 경우만)
    MANUAL_MAPPINGS = {
        # 지주회사는 주력 사업 기준으로 매핑
        "000660": IndustryMappingRules.KIS.SEMICONDUCTOR,  # SK하이닉스 (반도체)
        "035420": IndustryMappingRules.KIS.SERVICE,        # NAVER (서비스/IT)
        "035720": IndustryMappingRules.KIS.SERVICE,        # 카카오 (서비스/IT)

        # 복합 사업 기업
        "005930": IndustryMappingRules.KIS.ELECTRICAL,     # 삼성전자 (전기전자)
        "005380": IndustryMappingRules.KIS.TRANSPORT_EQUIP,# 현대차 (운송장비)
    }

    @classmethod
    def get_kis_code(cls, stock_code: str) -> str | None:
        """종목코드로 수동 매핑된 KIS 업종 코드 조회"""
        return cls.MANUAL_MAPPINGS.get(stock_code)
```

### 3. 동기화 로직 재설계

#### 3.1 새로운 `sync_corp_codes.py` 로직

```python
# 의사 코드

def handle():
    # STEP 1: Industry 테이블 초기화 (KIS 업종 지수 기반)
    # - KIS 마스터 파일에서 업종 지수 목록 로드
    # - Industry 테이블에 upsert

    # STEP 2: Company 데이터 동기화
    # - DART API에서 기업 정보 조회
    # - original_ksic_code에 원본 KSIC 코드 저장

    # STEP 3: Company-Industry 매핑
    for company in companies:
        # 3-1. 수동 매핑 확인 (특수 기업)
        kis_code = SpecialCompanyMappings.get_kis_code(company.stock_code)

        # 3-2. KSIC 규칙 기반 매핑
        if not kis_code:
            kis_code = IndustryMappingRules.get_kis_code(company.original_ksic_code)

        # 3-3. Industry 연결
        if kis_code:
            industry = Industry.objects.get(kis_code=kis_code)
            company.industry = industry
            company.save()
```

### 4. 구현 단계

#### Phase 1: 준비 (1일)

1. **현재 데이터 백업**
   ```bash
   docker-compose exec db pg_dump -U postgres -d postgres \
       -t company -t industry -t ksic_category -t kis_industry \
       > backup_before_redesign.sql
   ```

2. **KIS 업종 지수 목록 확정**
   - KIS 마스터 파일에서 실제 사용 가능한 업종 코드 목록 확인
   - 각 업종 코드의 정확한 이름 확인

3. **매핑 규칙 검증**
   - 상위 100개 기업의 KSIC 코드 샘플링
   - 규칙 적용 결과 수동 검증

#### Phase 2: 모델 마이그레이션 (1일)

1. **Industry 모델 수정**
   ```python
   # industries/models.py
   class Industry(models.Model):
       industry_id = models.BigAutoField(primary_key=True)
       kis_code = models.CharField(max_length=4, unique=True)  # 신규
       name = models.CharField(max_length=255)
       description = models.TextField(null=True, blank=True)
       # induty_code 필드 제거 예정
   ```

2. **마이그레이션 스크립트 작성**
   - KisIndustry → Industry 데이터 이전
   - Company.industry 재연결
   - 기존 테이블 정리

#### Phase 3: 매핑 서비스 구현 (1일)

1. **IndustryMappingRules 클래스 구현**
2. **SpecialCompanyMappings 클래스 구현**
3. **sync_corp_codes.py 단순화**

#### Phase 4: 검증 및 정리 (1일)

1. **전체 기업 매핑 실행**
   ```bash
   python manage.py sync_corp_codes
   ```

2. **매핑 결과 검증**
   ```bash
   python manage.py validate_industry_mapping
   ```

3. **불필요한 코드/테이블 제거**
   - `KsicCategory` 모델 삭제
   - `KisIndustry` 모델 삭제 (Industry로 통합됨)
   - `KsicKisManualMapping` 클래스 삭제
   - `KsicKisValidator` 클래스 삭제

---

## 삭제 대상 파일 목록

```
companies/services/ksic_kis_manual_mapping.py  # 삭제
companies/services/ksic_kis_validator.py       # 삭제
companies/services/industry_mapper.py          # 삭제 또는 대폭 수정

industries/models.py:
  - KsicCategory 모델 삭제
  - KisIndustry 모델 삭제 (Industry로 통합)
```

## 새로 생성할 파일

```
companies/services/industry_mapping_rules.py   # 신규 (매핑 규칙)
```

## 수정할 파일

```
industries/models.py                                    # Industry 모델 수정
companies/models.py                                     # induty_code 필드 정리
companies/management/commands/sync_corp_codes.py        # 대폭 단순화
companies/management/commands/validate_industry_mapping.py  # 검증 로직 수정
```

---

## 검증 계획

### 샘플 검증 (Phase 4)

| 종목코드 | 기업명 | 원본 KSIC | 기대 Industry | 실제 Industry |
|---------|--------|-----------|---------------|---------------|
| 005930 | 삼성전자 | 264 | 전기전자 | |
| 000660 | SK하이닉스 | 264 | 반도체 | |
| 055550 | 신한지주 | 641 | 은행 | |
| 035720 | 카카오 | 620 | 서비스 | |
| 005380 | 현대차 | 304 | 운송장비 | |
| 012330 | 현대모비스 | 303 | 운송장비 | |
| 207940 | 삼성바이오로직스 | 212 | 제약 | |
| 051910 | LG화학 | 201 | 화학 | |
| 017670 | SK텔레콤 | 612 | 통신 | |
| 032830 | 삼성생명 | 651 | 보험 | |

### 통계 검증

```python
# 검증 스크립트
from companies.models import Company
from industries.models import Industry

# 1. Industry별 기업 수 확인
for industry in Industry.objects.all():
    count = Company.objects.filter(industry=industry).count()
    print(f"{industry.name}: {count}개")

# 2. 매핑 안 된 기업 확인
unmapped = Company.objects.filter(industry__isnull=True).count()
print(f"매핑 안 됨: {unmapped}개")

# 3. 비율 확인
total = Company.objects.count()
mapped = total - unmapped
print(f"매핑률: {mapped/total*100:.1f}%")
```

---

## 롤백 계획

```bash
# 백업에서 복원
docker-compose exec db psql -U postgres -d postgres < backup_before_redesign.sql

# 코드 롤백
git checkout main -- companies/ industries/
```

---

## 일정 요약

| Phase | 작업 | 예상 소요 |
|-------|------|----------|
| Phase 1 | 준비 (백업, 규칙 검증) | 1일 |
| Phase 2 | 모델 마이그레이션 | 1일 |
| Phase 3 | 매핑 서비스 구현 | 1일 |
| Phase 4 | 검증 및 정리 | 1일 |
| **합계** | | **4일** |

---

## 작성 정보

- **작성자**: Claude Code
- **작성일**: 2026-01-24
- **상태**: Draft (검토 대기)
- **관련 이슈**: #83
