# 보고서 처리 워크플로우 개선 계획

## 🔎 개요

현재 보고서 처리 워크플로우는 전체 보고서 본문을 LLM에 전달하여 정보를 추출하고 있습니다. 이를 개선하여 **섹션별 파싱**, **테이블 마크다운 변환**, **에이전트 워크플로우 분리**를 통해 추출 정확도와 효율성을 향상시킵니다.

## 📋 현재 문제점

1. **전체 본문 전달**: 보고서 전체를 LLM에 전달하여 불필요한 토큰 소비 및 노이즈 증가
2. **표 구조 손실**: 복잡한 표가 일반 텍스트로 변환되면서 행/열 구조가 뒤섞임
3. **일관된 프롬프트**: 기업 유형(제조업/금융지주사/개별 금융사)에 관계없이 동일한 프롬프트 사용

## 🎯 개선 목표

1. **섹션별 파싱**: [II. 사업의 내용] 중 표가 포함된 하위 섹션만 추출
2. **테이블 마크다운 변환**: 표 구조를 보존한 Markdown 형식으로 변환하여 LLM의 수치 인식률 향상
3. **에이전트 워크플로우 분리**: Classifier와 Extractor를 분리하여 최적화된 프롬프트 적용

## 📐 아키텍처 설계

### 현재 워크플로우

```
extract_report_content_task
  ↓ (raw_content: 전체 텍스트)
refine_report_content_task
  ↓ (refined_content: 정제된 전체 텍스트)
extract_report_info_task
  ↓ (Gemini에 전체 본문 전달)
extracted_info
```

### 개선된 워크플로우

```
extract_report_content_task
  ↓ (raw_content: 전체 텍스트, xml_content: XML 원문)
refine_report_content_task
  ├─ RefineService: 전체 본문 정제
  └─ ReportSectionExtractorService: 섹션별 추출 + 테이블 마크다운 변환
      ↓ (refined_content, section_content, tables_markdown)
extract_report_info_task
  ├─ Agent A (ReportClassifierService): 기업 유형 분류
  └─ Agent B (ReportInfoExtractorService): 분류 결과 기반 최적화된 프롬프트로 정보 추출
      ↓ (extracted_info)
```

## 🔧 구현 세부사항

### 1. 섹션별 파싱 (Section-based Retrieval)

#### 1.1 `ReportSectionExtractorService` 생성

**위치**: `companies/services/report_section_extractor.py`

**기능**:
- DART XML에서 [II. 사업의 내용] 섹션 추출
- 하위 섹션 중 표가 포함된 섹션만 선별
- 추출 대상 하위 섹션:
  - 주요 제품 및 서비스
  - 매출 및 수주상황
  - 영업실적
  - 영업종류별 현황
  - 수익별 현황
  - 사업부문별 현황
  - 부문별 매출

**메서드**:
```python
def extract_sections_with_tables(
    self, xml_content: str, report_name: str
) -> Dict[str, str]:
    """
    Returns:
        {
            "main_content": "섹션별 추출된 본문",
            "tables": "Markdown 형식의 표 데이터"
        }
    """
```

**구현 방식**:
- BeautifulSoup으로 XML 파싱
- 섹션 제목 패턴 매칭 (다양한 형식 고려)
- 표(`<table>`) 태그 추출
- 표가 포함된 하위 섹션만 선별

### 2. 테이블 마크다운 변환 (Table-to-Markdown)

#### 2.1 테이블 변환 로직

**위치**: `ReportSectionExtractorService._table_to_markdown()`

**기능**:
- HTML/XML `<table>` 태그를 Markdown 테이블 형식으로 변환
- 헤더(`<thead>`)와 본문(`<tbody>`) 구분
- 셀 텍스트 정제 (줄바꿈 제거, 공백 정리)
- Markdown 파이프 문자(`|`) 이스케이프 처리

**변환 예시**:
```markdown
| 부문 | 매출액(원) | 비중(%) |
|------|-----------|---------|
| 반도체 | 100,000,000 | 50.0 |
| 디스플레이 | 50,000,000 | 25.0 |
```

**장점**:
- LLM이 표 구조를 정확히 인식
- 행/열 관계 보존
- 수치 데이터 추출 정확도 향상

### 3. 에이전트 워크플로우 분리

#### 3.1 Agent A: Classifier (`ReportClassifierService`)

**위치**: `companies/services/report_classifier.py`

**기능**:
- 기업 유형 분류 (Gemini 사용)
- 분류 대상:
  - `manufacturing`: 제조업
  - `financial_holding`: 금융지주사
  - `financial_individual`: 개별 금융사
  - `service`: 서비스업
  - `other`: 기타

**입력**:
- `company_name`: 기업명
- `report_name`: 보고서명
- `content_sample`: 보고서 내용 샘플 (최대 5000자)

**출력**:
```json
{
  "company_type": "manufacturing",
  "reason": "주요 제품 생산 기업"
}
```

#### 3.2 Agent B: Extractor (`ReportInfoExtractorService` 개선)

**위치**: `companies/services/report_info_extractor.py`

**개선사항**:
1. **섹션별 추출된 내용 우선 사용**
   - `section_content`가 있으면 우선 사용
   - 없으면 전체 `refined_content` 사용

2. **테이블 마크다운 포함**
   - `tables_markdown`이 있으면 컨텍스트에 추가
   - 표 데이터를 별도 섹션으로 구분

3. **기업 유형별 최적화된 프롬프트**
   - Classifier 결과에 따라 프롬프트 분기
   - 금융지주사/개별 금융사: "영업수익(Operating Revenue)" 키워드 강조
   - 제조업/서비스업: "매출액" 키워드 강조

**메서드 시그니처 변경**:
```python
def extract_info(
    self,
    refined_content: str,
    report_name: str,
    company_name: str,
    section_content: str = "",
    tables_markdown: str = "",
) -> dict:
```

## 📝 구현 단계

### Phase 1: 섹션별 파싱 및 테이블 변환

1. `ReportSectionExtractorService` 클래스 생성
   - XML 파싱 로직
   - 섹션 추출 로직
   - 테이블 Markdown 변환 로직

2. `ReportExtractorService` 확장
   - `extract_xml_content()` 메서드 추가 (XML 원문 반환)

3. `refine_report_content_task` 수정
   - 섹션별 추출 통합
   - `section_content`, `tables_markdown` 데이터 전달

### Phase 2: 에이전트 워크플로우 분리

1. `ReportClassifierService` 클래스 생성
   - 기업 유형 분류 로직
   - Gemini API 연동

2. `ReportInfoExtractorService` 개선
   - Classifier 통합
   - 기업 유형별 프롬프트 분기
   - 섹션별 추출된 내용 및 테이블 마크다운 활용

3. `extract_report_info_task` 수정
   - 섹션별 추출 데이터 전달
   - 새로운 파라미터 전달

### Phase 3: 테스트 및 검증

1. 단위 테스트 작성
   - 섹션 추출 테스트
   - 테이블 변환 테스트
   - 기업 유형 분류 테스트

2. 통합 테스트
   - 전체 워크플로우 테스트
   - 실제 보고서로 검증

3. 성능 측정
   - 토큰 사용량 비교
   - 추출 정확도 비교

## 📊 예상 효과

### 토큰 절감
- **현재**: 전체 보고서 본문 (~30,000자)
- **개선 후**: 섹션별 추출 (~5,000자) + 표 마크다운 (~2,000자)
- **절감률**: 약 70% 토큰 절감

### 추출 정확도 향상
- 표 구조 보존으로 수치 데이터 추출 정확도 향상
- 기업 유형별 최적화된 프롬프트로 매출 구성 추출 정확도 향상

### 처리 속도 향상
- 토큰 감소로 LLM 응답 시간 단축
- 불필요한 컨텍스트 제거로 처리 효율성 향상

## 🔄 마이그레이션 전략

1. **점진적 적용**: 기존 워크플로우 유지하면서 새 워크플로우 병행
2. **플래그 기반**: 환경 변수로 새 워크플로우 활성화/비활성화
3. **롤백 가능**: 문제 발생 시 기존 방식으로 즉시 복구

## 📌 주의사항

1. **XML 파싱 안정성**: DART XML 형식이 변경될 수 있으므로 다양한 형식 대응 필요
2. **섹션 추출 실패 처리**: 섹션 추출 실패 시 전체 본문 사용 (fallback)
3. **테이블 변환 실패 처리**: 테이블 변환 실패 시 일반 텍스트로 추출
4. **Classifier 오분류 처리**: 분류 실패 시 기본값(`other`) 사용

## 📚 참고사항

- DART XML 구조 분석 필요
- 실제 보고서 샘플로 테스트 필요
- 기업 유형별 프롬프트 최적화는 반복 개선 필요
