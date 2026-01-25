# 기업-산업 매핑 오류 수정 계획서

## 문제 현황

### 증상
- 특정 산업에 전혀 관련 없는 기업이 매핑되는 현상 발생
- 예시: 금융업종에 SK, LG 등 제조업/IT 기업이 매핑됨

### 발견된 문제

#### 1. KSIC → KIS 매핑 로직의 취약점

**위치**: `companies/management/commands/sync_corp_codes.py` (line 209-239)

**현재 로직**:
```python
# STEP 4: KSIC → KIS 매핑 생성 중...
for cat in KsicCategory.objects.all():
    # 해당 KSIC 코드를 가진 기업들의 종목코드 수집
    tickers = list(
        Company.objects.filter(induty_code=cat.ksic_code).values_list(
            "stock_code", flat=True
        )
    )

    # 메모리 딕셔너리에서 통계 계산
    kis_counts = {}
    for ticker in tickers:
        kis_code = ticker_to_kis.get(ticker)
        if kis_code and kis_code != "0001":  # 종합지수 제외
            kis_counts[kis_code] = kis_counts.get(kis_code, 0) + 1

    if kis_counts:
        # ⚠️ 문제: 가장 많이 나타나는 KIS 코드를 선택
        best_kis_code = max(kis_counts.items(), key=lambda x: x[1])[0]
```

**문제점**:
- **통계 기반 매핑의 한계**: 단순히 "가장 많이 나타나는" KIS 코드를 선택하는 방식
- **ticker_to_kis 매핑의 신뢰성 부족**: KIS 마스터 파일에서 파싱한 데이터의 정확성이 검증되지 않음
- **소수 기업의 영향력**: 한 KSIC 카테고리에 속한 기업 수가 적을 경우, 잘못된 매핑이 전체에 적용됨

**구체적 시나리오**:
1. KSIC "649" (금융업)에 속한 기업 100개 중
2. 60개는 ticker_to_kis에 매핑 없음 (KIS 마스터에 없음)
3. 25개는 KIS "0014" (전기전자)로 **잘못** 매핑됨
4. 15개만 KIS "0032" (금융)로 **올바르게** 매핑됨
5. → 결과: "0014"가 best_kis_code로 선택되어 KSIC "649" 전체가 "전기전자"로 매핑

#### 2. KIS 마스터 파일 파싱의 불확실성

**위치**: `companies/management/commands/sync_corp_codes.py` (line 148-169)

**현재 로직**:
```python
for line in content.splitlines():
    if len(line) < 100 or line[61:63] != b"ST":
        continue
    ticker = (
        line[1:7].decode("cp949", errors="ignore").strip().zfill(6)
    )

    # 중분류(68:72)가 없으면 대분류(64:68)를 사용
    mid_code = line[68:72].decode("cp949", errors="ignore").strip()
    large_code = (
        line[64:68].decode("cp949", errors="ignore").strip()
    )

    kis_code = mid_code if mid_code != "0000" else large_code
```

**문제점**:
- **하드코딩된 오프셋**: 바이너리 파일의 오프셋(line[61:63], line[68:72] 등)이 정확하지 않을 수 있음
- **인코딩 오류 무시**: `errors="ignore"` 옵션으로 파싱 오류를 묵인
- **검증 부재**: 파싱된 데이터의 유효성을 검증하지 않음

#### 3. 매핑 검증 로직 부재

**현재 상태**:
- 생성된 KSIC → KIS 매핑이 논리적으로 맞는지 검증하는 로직이 없음
- 금융 KSIC 코드(64, 65, 66)가 전기전자 KIS 코드로 매핑되는 것을 감지하지 못함

#### 4. IndustryMapper의 문제

**위치**: `companies/services/industry_mapper.py` (line 166-179)

**현재 로직**:
```python
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
```

**문제점**:
- 대분류 매핑이 부정확: "8" (정보통신업)은 실제로 58-63이지만, "9" (금융)은 64-66임
- KSIC 코드 범위가 정확하지 않아 잘못된 대분류 매핑 가능

## 근본 원인 분석

### 데이터 흐름

```
1. DART API → Company.induty_code (KSIC 코드, 예: "264", "649")
2. KIS 마스터 파일 → ticker_to_kis (종목코드 → KIS 코드, 예: {"005930": "0014"})
3. 통계 계산 → KSIC → KIS 매핑 (예: KSIC "264" → KIS "0014")
4. Company.induty_code 변환 → KSIC → KIS (예: "264" → "0014")
5. Company.industry 연결 → Industry (induty_code="0014")
```

### 문제 발생 지점

1. **2단계 (KIS 마스터 파싱)**:
   - 파싱 오류로 잘못된 ticker_to_kis 매핑 생성
   - 예: "005930" (삼성전자)이 잘못된 KIS 코드로 매핑

2. **3단계 (통계 계산)**:
   - 잘못된 ticker_to_kis 데이터를 기반으로 통계 계산
   - 소수의 잘못된 매핑이 전체 KSIC 카테고리에 영향

3. **4단계 (induty_code 변환)**:
   - 모든 기업의 induty_code가 일괄 변환됨
   - 잘못된 매핑이 전파됨

## 해결 방안

### 1단계: 긴급 수정 (Hotfix)

#### 1.1 KIS 마스터 파싱 검증 강화

**목표**: KIS 마스터 파일 파싱의 정확성 검증

**작업 내용**:

1. **파싱 결과 샘플링 검증**:
```python
# sync_corp_codes.py의 _load_kis_master_and_mapping() 수정

def _validate_kis_mapping_sample(self, ticker_to_kis):
    """KIS 매핑 샘플 검증"""
    # 대표 기업의 매핑이 맞는지 확인
    known_mappings = {
        "005930": "0014",  # 삼성전자 → 전기전자
        "000660": "0009",  # SK하이닉스 → 반도체
        "055550": "0032",  # 신한지주 → 금융
        "105560": "0032",  # KB금융 → 금융
        "035720": "0005",  # 카카오 → 소프트웨어
    }

    errors = []
    for ticker, expected_kis in known_mappings.items():
        actual_kis = ticker_to_kis.get(ticker)
        if actual_kis != expected_kis:
            errors.append(
                f"매핑 오류: {ticker} - 기대값: {expected_kis}, 실제값: {actual_kis}"
            )

    if errors:
        self.stdout.write(self.style.ERROR("\n".join(errors)))
        raise ValueError("KIS 매핑 검증 실패")
    else:
        self.stdout.write(self.style.SUCCESS("KIS 매핑 샘플 검증 통과"))
```

2. **파싱 오프셋 재검증**:
   - KIS 마스터 파일 포맷 문서 확인
   - 수동으로 몇 개 라인을 디코딩하여 오프셋 검증
   - 필요 시 오프셋 조정

#### 1.2 KSIC → KIS 매핑 검증 로직 추가

**목표**: 논리적으로 맞지 않는 매핑을 감지하고 차단

**작업 내용**:

1. **KSIC - KIS 허용 매핑 테이블 생성**:
```python
# companies/services/ksic_kis_validator.py (신규 파일)

class KsicKisValidator:
    """KSIC - KIS 매핑 검증"""

    # KSIC 대분류 → 허용 가능한 KIS 코드 매핑
    VALID_MAPPINGS = {
        # 제조업 (KSIC 10-33)
        "제조업": ["0009", "0014", "0018", "0021", "0024", "0027"],  # 반도체, 전기전자, 기계, 자동차, 화학, 철강

        # 금융 및 보험업 (KSIC 64-66)
        "금융 및 보험업": ["0032"],  # 금융

        # 정보통신업 (KSIC 58-63)
        "정보통신업": ["0005", "0038"],  # 소프트웨어, 통신서비스

        # 도매 및 소매업 (KSIC 46-47)
        "도매 및 소매업": ["0035"],  # 유통

        # 운수업 (KSIC 49-53)
        "운수업": ["0040"],  # 운송
    }

    # KSIC 코드 → 대분류 매핑 (정확한 범위)
    KSIC_TO_CATEGORY = {
        # 제조업
        **{str(i): "제조업" for i in range(10, 34)},  # 10-33

        # 금융 및 보험업
        "64": "금융 및 보험업",
        "65": "금융 및 보험업",
        "66": "금융 및 보험업",

        # 정보통신업
        **{str(i): "정보통신업" for i in range(58, 64)},  # 58-63

        # 도매 및 소매업
        "46": "도매 및 소매업",
        "47": "도매 및 소매업",

        # 운수업
        **{str(i): "운수업" for i in range(49, 54)},  # 49-53
    }

    @classmethod
    def validate_mapping(cls, ksic_code: str, kis_code: str) -> bool:
        """KSIC → KIS 매핑이 유효한지 검증"""
        # KSIC 코드의 앞 2자리로 대분류 확인
        ksic_prefix = ksic_code[:2] if len(ksic_code) >= 2 else ksic_code[:1]
        category = cls.KSIC_TO_CATEGORY.get(ksic_prefix)

        if not category:
            # 알 수 없는 KSIC 코드는 경고만 출력
            logger.warning(f"알 수 없는 KSIC 코드: {ksic_code}")
            return True

        # 허용 가능한 KIS 코드 확인
        allowed_kis = cls.VALID_MAPPINGS.get(category, [])

        if kis_code not in allowed_kis:
            logger.error(
                f"잘못된 매핑 감지: KSIC {ksic_code} ({category}) → KIS {kis_code}. "
                f"허용 가능한 KIS 코드: {allowed_kis}"
            )
            return False

        return True
```

2. **매핑 생성 시 검증 적용**:
```python
# sync_corp_codes.py의 _create_ksic_mapping() 수정

from companies.services.ksic_kis_validator import KsicKisValidator

# ... (기존 코드)

if kis_counts:
    # 가장 많이 나타나는 KIS 코드 찾기
    best_kis_code = max(kis_counts.items(), key=lambda x: x[1])[0]

    # ✅ 검증 로직 추가
    if not KsicKisValidator.validate_mapping(cat.ksic_code, best_kis_code):
        self.stdout.write(
            self.style.ERROR(
                f"❌ KSIC {cat.ksic_code} → KIS {best_kis_code} 매핑이 유효하지 않습니다. 건너뜁니다."
            )
        )
        continue  # 잘못된 매핑은 생성하지 않음

    kis_obj = KisIndustry.objects.filter(kis_code=best_kis_code).first()
    # ... (나머지 코드)
```

#### 1.3 매핑 신뢰도 기반 필터링

**목표**: 신뢰도가 낮은 매핑을 자동으로 제외

**작업 내용**:

```python
# sync_corp_codes.py의 _create_ksic_mapping() 수정

if kis_counts:
    total_count = sum(kis_counts.values())

    # ✅ 신뢰도 계산
    best_kis_code, best_count = max(kis_counts.items(), key=lambda x: x[1])
    confidence = best_count / total_count if total_count > 0 else 0

    # ✅ 신뢰도 임계값 (50% 이상만 허용)
    MIN_CONFIDENCE = 0.5
    MIN_SAMPLE_SIZE = 3  # 최소 3개 이상의 기업이 있어야 함

    if confidence < MIN_CONFIDENCE:
        self.stdout.write(
            self.style.WARNING(
                f"⚠️ KSIC {cat.ksic_code} → KIS {best_kis_code} 매핑의 신뢰도가 낮습니다 "
                f"({confidence:.1%}). 건너뜁니다."
            )
        )
        continue

    if best_count < MIN_SAMPLE_SIZE:
        self.stdout.write(
            self.style.WARNING(
                f"⚠️ KSIC {cat.ksic_code} → KIS {best_kis_code} 매핑의 샘플 수가 부족합니다 "
                f"({best_count}개). 건너뜁니다."
            )
        )
        continue

    # 검증 통과
    if not KsicKisValidator.validate_mapping(cat.ksic_code, best_kis_code):
        continue

    # 통계 정보 출력
    self.stdout.write(
        f"  ✓ KSIC {cat.ksic_code} → KIS {best_kis_code} "
        f"(신뢰도: {confidence:.1%}, 샘플: {best_count}/{total_count})"
    )

    # 매핑 생성
    kis_obj = KisIndustry.objects.filter(kis_code=best_kis_code).first()
    # ... (나머지 코드)
```

### 2단계: 수동 매핑 테이블 추가

**목표**: 자동 매핑이 실패하는 경우를 대비한 수동 매핑 테이블 생성

**작업 내용**:

1. **수동 매핑 테이블 생성** (`companies/services/ksic_kis_manual_mapping.py`):
```python
class KsicKisManualMapping:
    """KSIC → KIS 수동 매핑 테이블"""

    # 자동 매핑이 실패하거나 부정확한 경우를 위한 수동 매핑
    MANUAL_MAPPINGS = {
        # 금융 및 보험업
        "641": "0032",  # 은행 → 금융
        "642": "0032",  # 저축기관 → 금융
        "643": "0032",  # 신용카드 및 할부금융업 → 금융
        "649": "0032",  # 기타 금융업 → 금융
        "651": "0032",  # 보험업 → 금융
        "661": "0032",  # 금융투자업 → 금융

        # 반도체
        "261": "0009",  # 전자부품 제조업 → 반도체
        "264": "0009",  # 반도체 제조업 → 반도체

        # 정보통신업
        "620": "0005",  # 컴퓨터 프로그래밍 → 소프트웨어
        "631": "0005",  # 정보서비스업 → 소프트웨어
        "611": "0038",  # 전기통신업 → 통신서비스

        # 화학
        "201": "0024",  # 화학물질 제조업 → 화학
        "202": "0024",  # 화학제품 제조업 → 화학

        # 자동차
        "304": "0021",  # 자동차 제조업 → 자동차

        # 전기전자
        "281": "0014",  # 전기장비 제조업 → 전기전자
        "265": "0014",  # 의료기기 제조업 → 전기전자
    }

    @classmethod
    def get_kis_code(cls, ksic_code: str) -> str | None:
        """KSIC 코드로 KIS 코드 조회 (수동 매핑)"""
        # 정확한 매칭
        if ksic_code in cls.MANUAL_MAPPINGS:
            return cls.MANUAL_MAPPINGS[ksic_code]

        # 앞 2자리 매칭 (예: "64992" → "649")
        if len(ksic_code) >= 3:
            prefix = ksic_code[:3]
            if prefix in cls.MANUAL_MAPPINGS:
                return cls.MANUAL_MAPPINGS[prefix]

        return None
```

2. **수동 매핑 우선 적용**:
```python
# sync_corp_codes.py의 _create_ksic_mapping() 수정

from companies.services.ksic_kis_manual_mapping import KsicKisManualMapping

for cat in KsicCategory.objects.all():
    # ✅ 수동 매핑 우선 확인
    manual_kis_code = KsicKisManualMapping.get_kis_code(cat.ksic_code)

    if manual_kis_code:
        # 수동 매핑 사용
        kis_obj = KisIndustry.objects.filter(kis_code=manual_kis_code).first()

        if kis_obj:
            cat.representative_kis_id = kis_obj.kis_code
            cat.name = kis_obj.name
            cat.save()
            mapping_created += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ KSIC {cat.ksic_code} → KIS {manual_kis_code} (수동 매핑)"
                )
            )
            continue  # 다음 KSIC 카테고리로

    # 수동 매핑이 없으면 자동 매핑 시도
    # ... (기존 통계 기반 로직)
```

### 3단계: 매핑 검증 및 수정 관리 명령어

**목표**: 잘못된 매핑을 쉽게 찾고 수정할 수 있는 도구 제공

**작업 내용**:

1. **매핑 검증 명령어** (`companies/management/commands/validate_industry_mapping.py`):
```python
class Command(BaseCommand):
    help = "기업-산업 매핑을 검증하고 잘못된 매핑을 리포트합니다."

    def handle(self, *args, **options):
        from companies.models import Company
        from companies.services.ksic_kis_validator import KsicKisValidator

        self.stdout.write("기업-산업 매핑 검증 시작...")

        # Industry별로 그룹화
        industries = Industry.objects.filter(is_deleted=False)

        errors = []

        for industry in industries:
            companies = Company.objects.filter(industry=industry, is_deleted=False)

            for company in companies:
                # Company의 원본 KSIC 코드 확인 (별도 필드에 보관 필요)
                # 또는 DART API에서 다시 조회

                # 매핑 검증
                if not KsicKisValidator.validate_mapping(
                    company.original_ksic_code,  # 필요시 추가
                    industry.induty_code
                ):
                    errors.append({
                        "company": company.company_name,
                        "stock_code": company.stock_code,
                        "ksic": company.original_ksic_code,
                        "kis": industry.induty_code,
                        "industry": industry.name,
                    })

        # 결과 출력
        if errors:
            self.stdout.write(self.style.ERROR(f"\n❌ {len(errors)}개의 잘못된 매핑 발견:"))
            for err in errors[:20]:  # 최대 20개만 출력
                self.stdout.write(
                    f"  - {err['company']} ({err['stock_code']}): "
                    f"KSIC {err['ksic']} → KIS {err['kis']} ({err['industry']})"
                )

            # CSV 파일로 저장
            import csv
            with open("mapping_errors.csv", "w") as f:
                writer = csv.DictWriter(f, fieldnames=errors[0].keys())
                writer.writeheader()
                writer.writerows(errors)

            self.stdout.write(
                self.style.WARNING(f"\n전체 오류 목록을 mapping_errors.csv에 저장했습니다.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ 모든 매핑이 정상입니다."))
```

2. **매핑 수정 명령어** (`companies/management/commands/fix_industry_mapping.py`):
```python
class Command(BaseCommand):
    help = "잘못된 기업-산업 매핑을 수정합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제로 저장하지 않고 결과만 출력",
        )
        parser.add_argument(
            "--auto",
            action="store_true",
            help="자동으로 수정 (수동 매핑 테이블 사용)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        auto = options["auto"]

        from companies.models import Company
        from companies.services.ksic_kis_validator import KsicKisValidator
        from companies.services.ksic_kis_manual_mapping import KsicKisManualMapping
        from industries.models import Industry, KisIndustry

        self.stdout.write("잘못된 매핑 수정 시작...")

        fixed_count = 0

        # 모든 기업 순회
        for company in Company.objects.filter(
            induty_code__isnull=False, is_deleted=False
        ):
            # KSIC 코드 확인 (원본, 별도 필드 필요)
            original_ksic = company.original_ksic_code  # 추가 필요
            current_kis = company.induty_code

            # 매핑 검증
            if KsicKisValidator.validate_mapping(original_ksic, current_kis):
                continue  # 올바른 매핑

            # 잘못된 매핑 발견
            self.stdout.write(
                self.style.WARNING(
                    f"❌ {company.company_name}: KSIC {original_ksic} → KIS {current_kis}"
                )
            )

            if auto:
                # 수동 매핑 테이블에서 올바른 KIS 코드 찾기
                correct_kis = KsicKisManualMapping.get_kis_code(original_ksic)

                if correct_kis:
                    # Industry 찾기
                    industry = Industry.objects.filter(
                        induty_code=correct_kis, is_deleted=False
                    ).first()

                    if not industry:
                        # Industry 생성
                        kis_industry = KisIndustry.objects.get(kis_code=correct_kis)
                        if not dry_run:
                            industry = Industry.objects.create(
                                induty_code=correct_kis,
                                name=kis_industry.name,
                            )

                    # Company 업데이트
                    if not dry_run:
                        company.induty_code = correct_kis
                        company.industry = industry
                        company.save()

                    fixed_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ 수정: KSIC {original_ksic} → KIS {correct_kis}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ! 수동 매핑 테이블에 없음: KSIC {original_ksic}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(f"\n총 {fixed_count}개 기업의 매핑을 수정했습니다.")
        )
```

### 4단계: Company 모델에 원본 KSIC 코드 보관 필드 추가

**목표**: 원본 KSIC 코드를 보관하여 매핑 검증 및 롤백 가능하게 함

**작업 내용**:

1. **마이그레이션 생성**:
```python
# companies/migrations/XXXX_add_original_ksic_code.py

from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('companies', 'PREVIOUS_MIGRATION'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='original_ksic_code',
            field=models.CharField(
                max_length=20,
                null=True,
                blank=True,
                db_index=True,
                verbose_name="원본 KSIC 코드",
                help_text="DART API에서 가져온 원본 업종코드 (변환 전)",
            ),
        ),
    ]
```

2. **sync_corp_codes.py 수정**:
```python
# 기업 생성/업데이트 시 original_ksic_code 저장

company, created = Company.objects.get_or_create(
    stock_code=stock_code,
    defaults={
        "corp_code": corp_code,
        "company_name": corp_name,
        "induty_code": raw_ksic_code,  # KIS 코드로 변환될 예정
        "original_ksic_code": raw_ksic_code,  # ✅ 원본 보관
        "market": market,
        "industry": None,
        "description": "",
    },
)

# 업데이트 시에도 original_ksic_code 저장
if not skip_industry_mapping and raw_ksic_code:
    if not dry_run:
        company.original_ksic_code = raw_ksic_code  # ✅ 원본 보관
        company.induty_code = raw_ksic_code  # 일단 원본 저장 (나중에 변환)
    needs_update = True
```

## 실행 계획

### Phase 1: 긴급 수정 (1-2일)

1. **KsicKisValidator 클래스 생성** (반나절)
   - `companies/services/ksic_kis_validator.py` 작성
   - KSIC - KIS 허용 매핑 테이블 정의
   - 검증 로직 구현

2. **KsicKisManualMapping 클래스 생성** (반나절)
   - `companies/services/ksic_kis_manual_mapping.py` 작성
   - 주요 산업의 KSIC → KIS 수동 매핑 테이블 작성
   - 금융, 반도체, 정보통신, 화학, 자동차 등

3. **sync_corp_codes.py 수정** (1일)
   - 파싱 결과 샘플링 검증 추가
   - KSIC → KIS 매핑 시 검증 로직 적용
   - 신뢰도 기반 필터링 추가
   - 수동 매핑 우선 적용

4. **테스트 및 검증**
   - 테스트 데이터로 sync_corp_codes 실행
   - 매핑 결과 검증
   - 문제 발견 시 수정

### Phase 2: 매핑 검증 및 수정 (1-2일)

1. **Company 모델에 original_ksic_code 필드 추가** (반나절)
   - 마이그레이션 생성 및 적용
   - sync_corp_codes.py에서 original_ksic_code 저장하도록 수정

2. **validate_industry_mapping.py 명령어 작성** (반나절)
   - 매핑 검증 로직 구현
   - CSV 리포트 생성

3. **fix_industry_mapping.py 명령어 작성** (반나절)
   - 자동 수정 로직 구현
   - 수동 매핑 테이블 활용

4. **전체 데이터 재동기화 및 수정**
   - 기존 데이터 백업
   - `python manage.py sync_corp_codes --update-existing` 실행
   - `python manage.py validate_industry_mapping` 실행
   - `python manage.py fix_industry_mapping --auto` 실행
   - 결과 검증

### Phase 3: 문서화 및 모니터링 (반나절)

1. **문서 업데이트**
   - `docs/guides/INDUSTRY-MAPPING-ANALYSIS.md` 업데이트
   - CLAUDE.md에 매핑 검증 명령어 추가
   - README 업데이트

2. **모니터링 설정**
   - 매핑 오류 감지 알림 설정 (선택 사항)
   - 정기적인 매핑 검증 스케줄링 (Celery Beat)

## 테스트 시나리오

### 1. 샘플 데이터 검증
```bash
# 대표 기업의 매핑이 올바른지 확인
python manage.py shell
>>> from companies.models import Company
>>>
>>> # 삼성전자 (전기전자)
>>> samsung = Company.objects.get(stock_code="005930")
>>> print(f"{samsung.company_name}: {samsung.industry.name} ({samsung.induty_code})")
>>> # 기대: 삼성전자: 전기전자 (0014)
>>>
>>> # 신한지주 (금융)
>>> shinhan = Company.objects.get(stock_code="055550")
>>> print(f"{shinhan.company_name}: {shinhan.industry.name} ({shinhan.induty_code})")
>>> # 기대: 신한지주: 금융 (0032)
>>>
>>> # SK하이닉스 (반도체)
>>> skhynix = Company.objects.get(stock_code="000660")
>>> print(f"{skhynix.company_name}: {skhynix.industry.name} ({skhynix.induty_code})")
>>> # 기대: SK하이닉스: 반도체 (0009)
```

### 2. 금융 산업 매핑 검증
```bash
python manage.py shell
>>> from companies.models import Company
>>> from industries.models import Industry
>>>
>>> # 금융 산업에 속한 기업들 확인
>>> financial = Industry.objects.filter(name__contains="금융").first()
>>> companies = Company.objects.filter(industry=financial)[:10]
>>>
>>> for c in companies:
>>>     print(f"{c.company_name} ({c.stock_code}), KSIC: {c.original_ksic_code}")
>>>
>>> # 기대: 모두 금융 관련 기업 (은행, 증권, 보험 등)
>>> # 잘못된 예: SK, LG 등 제조업 기업이 나오면 안 됨
```

### 3. 매핑 검증 명령어 테스트
```bash
# 전체 매핑 검증
python manage.py validate_industry_mapping

# 기대 결과: 잘못된 매핑이 없거나, 있다면 CSV 파일로 리포트 생성
```

### 4. 자동 수정 테스트
```bash
# Dry run으로 먼저 확인
python manage.py fix_industry_mapping --auto --dry-run

# 실제 수정
python manage.py fix_industry_mapping --auto

# 기대 결과: 잘못된 매핑이 모두 수정됨
```

## 롤백 계획

### 데이터베이스 백업

```bash
# Phase 2 실행 전 백업
docker-compose exec db pg_dump -U postgres -d postgres -t company -t industry -t ksic_category > backup_before_fix.sql

# 롤백이 필요한 경우
docker-compose exec db psql -U postgres -d postgres < backup_before_fix.sql
```

### 코드 롤백

```bash
# 변경 사항 되돌리기
git revert <commit-hash>
```

## 성공 기준

1. **정확성**: 대표 기업 20개 샘플의 매핑이 100% 정확
2. **검증**: validate_industry_mapping 명령어 실행 시 오류 0개
3. **신뢰도**: 모든 KSIC → KIS 매핑의 신뢰도 50% 이상
4. **커버리지**: 전체 기업의 95% 이상이 Industry와 연결됨

## 참고 자료

- KSIC (한국표준산업분류): https://kssc.kostat.go.kr/
- KIS 업종 분류: 한국투자증권 업종 마스터 파일
- DART API 문서: https://opendart.fss.or.kr/

## 작성자 및 검토

- **작성자**: Claude Code
- **작성일**: 2026-01-24
- **검토자**: (검토 후 기입)
- **검토일**: (검토 후 기입)
