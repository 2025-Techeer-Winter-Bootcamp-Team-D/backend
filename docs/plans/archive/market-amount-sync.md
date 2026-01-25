# 기업 시가총액(market_amount) 수집/반영 계획

> **구현 완료**: 2026-01-16

## 목적
`Company.market_amount`(시가총액)을 신뢰 가능한 외부 데이터에서 수집하여
**기업 기본정보 조회 API** 응답에 최신 값이 포함되도록 한다.

현재 `CompanyDetailSerializer`에 `market_amount`가 이미 포함되어 있어,
**데이터 소스 및 갱신 로직 구현**이 핵심이다.

---

## 1) 데이터 소스 조사 결과

### A. DART 기업개황 API
- `companies/services/company_info.py`에서 DART 기업개황을 사용 중
- DART 응답에는 **시가총액 필드가 없음**
- DART만으로는 `market_amount` 갱신 불가

### B. KIS (한국투자증권) REST API - 현재가 시세
- KIS REST “국내주식 현재가 시세” 응답에 **시가총액(예: hts_avls)** 제공
- 이미 코드베이스에 KIS WebSocket 수집(`kis-publisher`)이 존재
- **REST 쿼트 API를 추가 호출**하는 방식이 가장 현실적

### C. KRX 상장주식수 + 현재가 계산
- 상장주식수 데이터가 필요
- 현 코드베이스에는 종목 코드 CSV 로딩만 있고 **주식수 데이터 없음**
- 별도 수집/정규화가 필요해 비용이 큼

**결론**: KIS REST API에서 제공하는 시가총액 값을 사용한다.

---

## 2) 구현 전략

### 핵심 아이디어
- `Company.market_amount`는 **KIS REST 시세 응답의 시가총액 값을 저장**
- 단건 갱신 + 배치 갱신(주기적) 모두 지원

### 2.1. KIS REST 시세 클라이언트 추가
- 위치 후보: `companies/services/kis_quote.py` 또는 `core/services/kis_quote.py`
- 책임:
  - `get_market_amount(stock_code)` → 시가총액(BigInt) 반환
  - 실패 시 `None` 반환 또는 예외 처리
- 필요 환경변수:
  - `KIS_APP_KEY`, `KIS_APP_SECRET` (이미 kis-publisher에서 사용 중)
  - 토큰 발급/캐시 로직은 REST 기준으로 별도 구현 필요

### 2.2. 단건 갱신 (동기/비동기)
- `CompanyInfoService.sync_company_info`에 옵션 추가
  - 예: `sync_market_amount: bool = True`
  - DART 동기화 후 KIS REST 호출로 시총 갱신
- `sync_company_from_dart` API에서 `sync_market_amount=true` 옵션 지원

### 2.3. 배치 갱신 (주기적)
- Celery Task 추가
  - `companies.tasks.kis_market_amount.sync_all_market_amount()`
  - 모든 `Company` 순회, 시가총액 갱신
- Celery Beat 스케줄 추가
  - 장 마감 후 1회 (예: 평일 16:10)
  - 실패 종목은 로깅 후 다음 사이클에서 재시도

### 2.4. 데이터 품질/운영
- 값이 없거나 실패 시 기존 값 유지
- (선택) `Company.market_amount_updated_at` 필드 추가로 갱신 시점 기록
- API 문서에 **시가총액 기준/시점** 명시

---

## 3) API 응답 반영 계획

현재 `CompanyDetailSerializer`에 `market_amount`가 포함되어 있어 **별도 변경 없음**.
문서에 아래를 명시:
- 시가총액 출처: KIS 현재가 시세
- 갱신 주기: 배치 기준 (예: 영업일 16:10)

---

## 4) 작업 순서 (구현 계획)

1. **KIS REST 시세 클라이언트 추가**
   - 토큰 발급/캐시 로직 포함
   - `get_market_amount(stock_code)` 구현
2. **단건 갱신 로직 추가**
   - `CompanyInfoService.sync_company_info` 확장
   - `sync_company_from_dart`에서 옵션 처리
3. **배치 갱신 Celery Task 추가**
   - 전체 기업 순회
   - 실패 종목 로깅
4. **Celery Beat 스케줄 등록**
   - 장 마감 후 주기적 실행
5. **문서 업데이트**
   - API 문서에 출처/갱신 주기 명시
   - 운영 문서에 환경변수/토큰 정책 추가

---

## 5) 리스크 및 대응

- **KIS 토큰 만료**: 토큰 캐싱 및 자동 재발급 필요
- **API Rate Limit**: 배치 시 요청 간 딜레이 필요
- **시가총액 불일치**: KIS 기준으로 통일하고 문서에 명시

---

## 6) 체크리스트
- [x] KIS REST 토큰 발급/캐시 구현
- [x] 시가총액 필드 매핑 확인 (`hts_avls` 등)
- [x] 단건 갱신 옵션 연동
- [x] 배치 갱신 task + beat 등록
- [x] 문서 업데이트

---

## 7) 구현 상세 (완료)

### 7.1. 파일 구조

| 파일 | 설명 |
|------|------|
| `companies/services/kis_quote.py` | KIS REST API 클라이언트 (토큰 발급/캐시, 시세 조회) |
| `companies/services/company_info.py` | 기업 정보 동기화 서비스 (시가총액 갱신 포함) |
| `companies/tasks/kis_market_amount.py` | 시가총액 배치 갱신 Celery Task |
| `config/settings.py` | Celery Beat 스케줄 등록 |

### 7.2. 주요 함수/클래스

```python
# companies/services/kis_quote.py
class KISQuoteClient:
    def get_stock_quote(stock_code: str) -> dict  # 현재가 시세 전체
    def get_market_amount(stock_code: str) -> int  # 시가총액만 (원 단위)

def get_market_amount(stock_code: str) -> int  # 편의 함수

# companies/services/company_info.py
class CompanyInfoService:
    def sync_company_info(company)  # DART + 시가총액 동기화
    def sync_market_amount_only(company)  # 시가총액만 갱신

# companies/tasks/kis_market_amount.py
sync_market_amount(stock_code)  # 단건 갱신 task
sync_all_market_amount()  # 전체 배치 갱신 (동기, Rate Limit 대응)
sync_all_market_amount_async()  # 전체 배치 갱신 (비동기)
```

### 7.3. 환경변수

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `KIS_APP_KEY` | KIS API 앱 키 | (필수) |
| `KIS_APP_SECRET` | KIS API 앱 시크릿 | (필수) |
| `KIS_REST_BASE_URL` | KIS REST API 기본 URL | `https://openapivts.koreainvestment.com:29443` (모의투자) |
| `DART_SYNC_ENABLED` | 시가총액 배치 갱신 활성화 | `false` |

> **실전투자 URL**: `https://openapi.koreainvestment.com:9443`

### 7.4. Celery Beat 스케줄

| 스케줄 ID | 실행 주기 | Task |
|-----------|-----------|------|
| `sync-market-amount-daily` | 평일 16:10 | `sync_all_market_amount` |

### 7.5. API 응답 시가총액 정보

- **출처**: KIS REST API 현재가 시세 (`hts_avls` 필드)
- **단위**: 원 (억 단위에서 변환)
- **갱신 주기**: 평일 장 마감 후 (16:10)
- **갱신 실패 시**: 기존 값 유지

### 7.6. 토큰 정책

- **발급**: `/oauth2/tokenP` 엔드포인트
- **유효기간**: 24시간
- **캐싱**: Django cache (23시간 TTL)
- **자동 재발급**: 캐시 만료 시 자동 재발급
