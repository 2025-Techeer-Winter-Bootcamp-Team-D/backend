# 재무 데이터 매핑 가이드

## 개요

이 문서는 DART API와 KIS API의 실제 응답 구조를 기반으로 재무 데이터를 매핑하는 방법을 설명합니다.

## DART API 재무제표 응답 구조

### 응답 형식

```json
{
  "status": "000",
  "message": "정상",
  "list": [
    {
      "account_id": "ifrs-full_Revenue",
      "account_nm": "매출액",
      "thstrm_amount": "302231000000000",
      "frmtrm_amount": "279040800000000",
      "bfefrmtrm_amount": "236807000000000",
      "ord": "1",
      "currency": "KRW",
      "sj_div": "IS",
      "sj_nm": "손익계산서",
      "bsns_year": "2024",
      "reprt_code": "11011",
      "fs_div": "CFS"
    }
  ]
}
```

### 주요 필드

- `account_id`: 계정과목 코드 (IFRS 기준)
- `account_nm`: 계정과목명 (한글)
- `thstrm_amount`: 당기금액 (문자열)
- `frmtrm_amount`: 전기금액 (문자열)
- `sj_div`: 재무제표 구분 (BS: 재무상태표, IS: 손익계산서)
- `currency`: 통화 (일반적으로 "KRW")
- `fs_div`: 재무제표 구분 (CFS: 연결재무제표, OFS: 개별재무제표)

### 계정과목 코드 매핑

| 내부 필드 | IFRS 계정과목 코드 (우선순위) | DART 계정과목 코드 | 계정과목명 |
|---------|------------------|------------------|-----------|
| revenue | `ifrs-full_Revenue` | `dart_OperatingRevenues`, `dart_TotalRevenue` | 매출액, 영업수익 |
| operating_profit | `ifrs-full_ProfitLossFromOperatingActivities` (실제 응답에 없을 수 있음) | `dart_OperatingIncomeLoss` | 영업이익 |
| net_income | `ifrs-full_ProfitLossAttributableToOwnersOfParent` (우선) → `ifrs-full_ProfitLoss` (fallback) | `dart_ProfitLoss` | 당기순이익 (지배기업소유주지분 우선) |
| total_assets | `ifrs-full_Assets` | `dart_TotalAssets` | 총자산, 자산총계 |
| total_liabilities | `ifrs-full_Liabilities` | `dart_TotalLiabilities` | 총부채, 부채총계 |
| total_equity | `ifrs-full_Equity` | `dart_TotalEquity` | 자본총계, 총자본 |

**참고사항:**
- `ifrs-full_ProfitLoss`는 여러 번 나타날 수 있음 (총 당기순이익, 지배기업소유주지분, 비지배지분)
- 지배기업소유주지분(`ifrs-full_ProfitLossAttributableToOwnersOfParent`)을 우선 사용
- 우선순위 계정이 없으면 가장 큰 절댓값을 선택

### 매핑 우선순위

1. **account_id 매핑** (가장 정확)
   - IFRS 계정과목 코드로 먼저 매핑 시도
   - 우선순위 계정 코드 우선 사용 (예: `ifrs-full_ProfitLossAttributableToOwnersOfParent` > `ifrs-full_ProfitLoss`)
   - 재무제표 구분(sj_div) 검증 포함
   - 같은 account_id가 여러 번 나타날 경우 가장 큰 절댓값 선택

2. **account_nm 매핑** (account_id가 없는 경우)
   - 계정과목명 키워드 매칭
   - 제외 키워드 체크
   - 재무제표 구분(sj_div) 검증 포함
   - 우선순위 기반 매칭 (낮은 숫자가 높은 우선순위)

### 단위 처리

- DART API는 일반적으로 **원 단위**로 제공
- 일부 경우 천원 단위일 수 있으므로 단위 정보 확인 필요
- `currency` 필드는 통화 정보만 제공 (단위 정보는 별도 확인)

## KIS API 시세 응답 구조

### 응답 형식

```json
{
  "rt_cd": "0",
  "msg1": "정상처리",
  "output": {
    "hts_avls": "500,000",
    "stck_prpr": "70000",
    "prdy_vrss": "1000",
    ...
  }
}
```

### 시가총액 매핑

- `hts_avls`: HTS 시가총액 (억 단위, 문자열, 콤마 포함 가능)
- 변환: 억 단위 → 원 단위
- 예: "500,000" → 500,000억원 → 50,000,000,000,000원

## 데이터 유효성 검증

### 검증 항목

1. **회계 등식 검증**
   - `total_assets == total_liabilities + total_equity`
   - 오차 범위: 1% 허용 (회계 처리 차이, 반올림 오차 등)

2. **매출액-영업이익 관계 검증**
   - `revenue >= operating_profit`
   - 영업이익은 매출액보다 클 수 없음

3. **극단값 검증**
   - 비정상적으로 큰 값 체크 (1경원 이상)
   - 경고만 출력 (데이터 오류일 수 있지만 저장은 허용)

4. **재무제표 구분 검증**
   - 총자산, 총부채, 총자본은 BS(재무상태표)에만 있어야 함
   - 매출액, 영업이익, 당기순이익은 IS(손익계산서)에만 있어야 함

## 개선 사항

### 변경 전 문제점

1. 계정과목 코드 매핑이 불완전함
2. 재무제표 구분 검증 없음
3. 단위 정규화 로직 미흡
4. 유효성 검증이 약함

### 변경 후 개선 사항

1. **정확한 계정과목 코드 매핑**
   - IFRS 기준 계정과목 코드 우선 매핑
   - DART 계정과목 코드 지원
   - 계정과목명 기반 매핑 개선

2. **재무제표 구분 검증 추가**
   - sj_div 필드로 재무상태표/손익계산서 구분
   - 잘못된 매핑 방지

3. **단위 정규화 로직 개선**
   - 원 단위로 통일
   - 단위 정보 추출 및 변환

4. **유효성 검증 강화**
   - 회계 등식 검증
   - 극단값 검증
   - 필수 필드 존재 여부 검증

## 테스트 방법

### DART API 재무제표 테스트

```bash
python scripts/test_dart_financial.py
```

### KIS API 시세 테스트

```python
from companies.services.kis_quote import get_kis_quote_client

client = get_kis_quote_client()
quote = client.get_stock_quote("005930")  # 삼성전자
market_amount = client.get_market_amount("005930")
print(f"시가총액: {market_amount:,}원")
```

## 참고 자료

- [DART OpenAPI 공식 문서](https://opendart.fss.or.kr/guide/main.do)
- [KIS OpenAPI 공식 문서](https://apiportal.koreainvestment.com/)
- IFRS 계정과목 코드 표준
