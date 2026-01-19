# 기업-산업 업종 코드 매핑 구조 분석

## 개요

이 문서는 코드베이스에서 기업(Company)과 산업(Industry)이 업종 코드를 매개로 어떻게 매핑되는지 분석한 내용입니다.

## 데이터 모델 구조

### 1. Company 모델 (`companies/models.py`)

```python
class Company(models.Model):
    stock_code = models.CharField(primary_key=True, max_length=6)  # 종목코드
    corp_code = models.CharField(max_length=8, unique=True, null=True)  # DART 고유번호
    industry = models.ForeignKey(
        Industry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companies",
        db_column="industry_id",
    )  # Industry와의 직접 관계
    induty_code = models.CharField(
        max_length=20, null=True, blank=True, db_index=True
    )  # 업종코드 (KSIC 또는 KIS 코드)
    # ... 기타 필드
```

**핵심 필드:**
- `induty_code`: 업종코드 저장 (KSIC 3자리 또는 KIS 코드로 변환 가능)
- `industry`: Industry 모델에 대한 ForeignKey (직접 매핑)

### 2. Industry 모델 (`industries/models.py`)

```python
class Industry(models.Model):
    industry_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)  # 산업 이름
    induty_code = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True
    )  # 업종코드 (KSIC 또는 KIS 코드)
    description = models.TextField(null=True, blank=True)
    # ... 기타 필드
```

**핵심 필드:**
- `induty_code`: 업종코드 (KSIC 또는 KIS 코드)
- `companies`: Company 모델과의 역참조 관계 (`related_name="companies"`)

### 3. KIS 관련 모델 (`industries/models.py`)

#### KisIndustry
```python
class KisIndustry(models.Model):
    kis_code = models.CharField(max_length=4, primary_key=True)  # '0014' 등
    name = models.CharField(max_length=100)  # '전기전자' 등
```

**역할:** KIS 업종 지수 마스터 (KOSPI/KOSDAQ 업종 지수 코드)

#### KsicCategory
```python
class KsicCategory(models.Model):
    ksic_code = models.CharField(max_length=5, primary_key=True)  # '261' 등
    name = models.CharField(max_length=100, null=True, blank=True)
    representative_kis = models.ForeignKey(
        'KisIndustry', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="ksic_categories"
    )
```

**역할:** KSIC 코드와 KIS 코드 간의 매핑 테이블

#### IndustryMapping
```python
class IndustryMapping(models.Model):
    ticker = models.CharField(max_length=6, db_index=True)  # 종목코드
    kis = models.ForeignKey(KisIndustry, on_delete=models.CASCADE, related_name="mappings")
    weight = models.FloatField(default=1.0)
```

**역할:** 종목코드(ticker)와 KIS 업종 코드 간의 매핑 (KIS 마스터 파일 기반)

## 매핑 프로세스

### 1. DART API → Company 매핑 (KSIC 기반)

**경로:** `companies/services/company_info.py` → `IndustryMapper.get_industry_by_code()`

#### 단계별 프로세스:

1. **DART API에서 업종코드 조회**
   ```python
   # CompanyInfoService.sync_company_info()
   industry_code = data.get("induty_code")  # DART API 응답
   ```

2. **업종코드 정규화 (3자리)**
   ```python
   # 숫자 형식의 업종코드는 3자리로 정규화
   # 예: "64992" → "649", "26410" → "264", "264" → "264"
   if industry_code_str.isdigit() and len(industry_code_str) > 3:
       industry_code_normalized = industry_code_str[:3]
   ```

3. **IndustryMapper를 통한 Industry 찾기/생성**
   ```python
   industry = IndustryMapper.get_industry_by_code(industry_code_normalized)
   ```

4. **Company에 업종코드 및 Industry 할당**
   ```python
   company.induty_code = industry_code_normalized
   company.industry = industry  # IndustryMapper에서 반환된 Industry
   ```

### 2. IndustryMapper 매핑 로직 (`companies/services/industry_mapper.py`)

`IndustryMapper.get_industry_by_code()` 메서드는 다음 순서로 Industry를 찾습니다:

#### 우선순위 1: 업종코드로 직접 Industry 찾기
```python
industry = Industry.objects.filter(
    induty_code=industry_code, is_deleted=False
).first()
```

#### 우선순위 2: 상위 분류 코드로 찾기
```python
# 예: "264" → "26" → "2"
for code_length in range(len(industry_code) - 1, 0, -1):
    parent_code = industry_code[:code_length]
    industry = Industry.objects.filter(
        induty_code=parent_code, is_deleted=False
    ).first()
```

#### 우선순위 3: 매핑 테이블(INDUSTRY_CODE_MAP)에서 Industry 이름 찾기
```python
industry_name = cls.INDUSTRY_CODE_MAP.get(industry_code)
```

#### 우선순위 4: 대분류 코드로 매핑 시도
```python
# 숫자 코드의 첫 자리로 대분류 시도
# 예: "1" → "제조업", "6" → "운수업"
first_digit = industry_code[0]
major_category = major_category_map.get(first_digit)
```

#### 최종: Industry 찾기 또는 생성
```python
# 이름으로 Industry 찾기
industry = Industry.objects.filter(name=industry_name, is_deleted=False).first()

if industry:
    # 기존 Industry에 업종코드 업데이트
    if not industry.induty_code:
        industry.induty_code = industry_code
        industry.save()
else:
    # 새 Industry 생성
    industry = Industry.objects.create(
        name=industry_name,
        induty_code=industry_code,
        description=f"업종코드: {industry_code}",
    )
```

### 3. KIS 코드 기반 매핑 (KIS 마스터 파일)

**경로:** `industries/management/commands/sync_industry_mapping.py`

#### 단계별 프로세스:

1. **KIS 업종 마스터 적재**
   ```python
   # idxcode.mst.zip 파일에서 KIS 업종 코드 추출
   KisIndustry.objects.update_or_create(kis_code=kis_code, defaults={'name': name})
   ```

2. **종목-업종 매핑 적재**
   ```python
   # kospi_code.mst.zip, kosdaq_code.mst.zip 파일에서
   # 종목코드(ticker)와 KIS 업종 코드 매핑 추출
   IndustryMapping.objects.get_or_create(ticker=ticker, kis=kis_obj)
   ```

3. **KSIC → KIS 매핑 생성**
   ```python
   # Company 테이블의 KSIC 코드를 기반으로
   # IndustryMapping에서 가장 많이 나타나는 KIS 코드 찾기
   best_match = IndustryMapping.objects.filter(ticker__in=tickers)\
       .values('kis', 'kis__name')\
       .annotate(cnt=Count('kis'))\
       .order_by('-cnt').first()
   
   # KsicCategory에 매핑 저장
   cat.representative_kis_id = best_match['kis']
   ```

4. **Company 테이블의 induty_code를 KIS 코드로 변환 (선택적)**
   ```python
   # KSIC 코드를 KIS 코드로 일괄 업데이트
   Company.objects.filter(induty_code=cat.ksic_code)\
       .update(induty_code=cat.representative_kis_id)
   ```

5. **Industry 테이블 동기화**
   ```python
   # Industry 테이블에 KIS 코드 기반으로 업데이트
   Industry.objects.update_or_create(
       induty_code=cat.representative_kis_id,
       defaults={
           "name": cat.name,
           "description": f"{cat.name} 지수 (KSIC:{cat.ksic_code} 매핑 결과)"
       }
   )
   ```

## 매핑 흐름도

```
┌─────────────────┐
│   DART API      │
│  (KSIC 코드)    │
└────────┬────────┘
         │
         │ induty_code (예: "64992")
         ▼
┌─────────────────┐
│  정규화 (3자리) │
│  "64992" → "649"│
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│   IndustryMapper                │
│   get_industry_by_code()        │
│                                  │
│   1. induty_code로 직접 찾기    │
│   2. 상위 분류 코드로 찾기       │
│   3. 매핑 테이블에서 찾기        │
│   4. 대분류로 찾기              │
│   5. Industry 생성 (없으면)     │
└────────┬────────────────────────┘
         │
         │ Industry 인스턴스
         ▼
┌─────────────────┐
│    Company       │
│  - induty_code   │
│  - industry (FK) │
└─────────────────┘
```

### KIS 코드 기반 매핑 흐름도

```
┌──────────────────────┐
│  KIS 마스터 파일     │
│  (idxcode.mst.zip)   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   KisIndustry        │
│   (KIS 업종 코드)     │
└──────────┬───────────┘
           │
           │
┌──────────▼───────────┐
│  종목 마스터 파일     │
│  (kospi_code.mst.zip) │
│  (kosdaq_code.mst.zip)│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  IndustryMapping     │
│  (ticker ↔ KIS)      │
└──────────┬───────────┘
           │
           │ 통계 분석
           ▼
┌──────────────────────┐
│   KsicCategory       │
│   (KSIC ↔ KIS)       │
└──────────┬───────────┘
           │
           │ 변환 (선택적)
           ▼
┌──────────────────────┐
│    Company           │
│  induty_code (KIS)   │
└──────────────────────┘
```

## 업종 코드 체계

### 1. KSIC (한국표준산업분류) 코드

- **출처:** DART API
- **형식:** 숫자 (예: "264", "64992")
- **정규화:** 3자리로 정규화 (예: "64992" → "649")
- **용도:** DART API에서 받은 원본 업종코드

### 2. KIS 업종 코드

- **출처:** KIS 마스터 파일 (idxcode.mst.zip)
- **형식:** 4자리 숫자 (예: "0014", "1047")
- **용도:** KOSPI/KOSDAQ 업종 지수 코드

### 3. 코드 변환

- **KSIC → KIS:** `KsicCategory` 테이블을 통해 매핑
- **변환 기준:** `IndustryMapping`에서 해당 KSIC 코드를 가진 기업들의 KIS 코드 분포를 분석하여 가장 많이 나타나는 KIS 코드를 대표값으로 선택

## 주요 서비스 및 명령어

### 1. IndustryMapper (`companies/services/industry_mapper.py`)

**역할:** KSIC 코드를 Industry 모델로 매핑

**주요 메서드:**
- `get_industry_by_code(industry_code)`: 업종코드로 Industry 찾기 또는 생성

### 2. CompanyInfoService (`companies/services/company_info.py`)

**역할:** DART API를 통해 기업 정보 동기화 및 Industry 매핑

**주요 메서드:**
- `sync_company_info(company)`: 기업 정보 동기화 및 Industry 매핑

### 3. IndustryService (`industries/services/industry_service.py`)

**역할:** KSIC 코드를 KIS 코드로 변환

**주요 메서드:**
- `get_representative_kis_index(ksic_3digit)`: KSIC 3자리 코드를 KIS 업종 코드로 변환

### 4. 관리 명령어

#### `sync_industry_mapping`
```bash
python manage.py sync_industry_mapping
```
- KIS 마스터 파일에서 업종 코드 및 종목-업종 매핑 적재
- KSIC → KIS 매핑 생성
- Company 및 Industry 테이블 동기화

#### `sync_corp_codes`
```bash
python manage.py sync_corp_codes
```
- DART API에서 기업 정보 동기화
- KSIC 코드를 KIS 코드로 변환하여 저장 (KsicCategory 기반)

## 데이터 흐름 요약

1. **초기 데이터 수집:**
   - DART API → Company (KSIC 코드 저장)
   - KIS 마스터 파일 → IndustryMapping (종목 ↔ KIS 코드)

2. **매핑 생성:**
   - IndustryMapping 통계 분석 → KsicCategory (KSIC ↔ KIS 매핑)

3. **Industry 할당:**
   - IndustryMapper → Company.industry (KSIC 코드 기반)

4. **코드 변환 (선택적):**
   - KsicCategory → Company.induty_code (KSIC → KIS 변환)

## 주의사항

1. **업종코드 정규화:**
   - 숫자 형식의 KSIC 코드는 3자리로 정규화됨
   - 문자 형식(예: "C26")은 그대로 유지

2. **Industry 생성:**
   - 매핑이 없으면 IndustryMapper가 자동으로 Industry 생성
   - 생성된 Industry는 `INDUSTRY_CODE_MAP` 또는 대분류 매핑 기반

3. **KIS 코드 변환:**
   - `sync_industry_mapping` 명령어 실행 시 Company.induty_code가 KIS 코드로 변환될 수 있음
   - 원본 KSIC 코드를 유지하려면 변환 단계를 스킵해야 함

4. **매핑 우선순위:**
   - IndustryMapper는 여러 단계의 fallback 로직을 사용
   - 정확한 매핑이 없으면 상위 분류 코드로 매핑 시도

## 관련 파일

- `companies/models.py`: Company 모델 정의
- `industries/models.py`: Industry, KisIndustry, KsicCategory, IndustryMapping 모델 정의
- `companies/services/industry_mapper.py`: KSIC → Industry 매핑 서비스
- `companies/services/company_info.py`: DART API 기반 기업 정보 동기화
- `industries/services/industry_service.py`: KSIC → KIS 변환 서비스
- `industries/management/commands/sync_industry_mapping.py`: KIS 마스터 파일 기반 매핑 생성
- `companies/management/commands/sync_corp_codes.py`: DART API 기반 기업 정보 동기화
