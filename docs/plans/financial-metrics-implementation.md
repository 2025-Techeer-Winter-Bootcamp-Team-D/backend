# 기업 재무 지표 추가 구현 계획

**작성일**: 2026-01-18
**상태**: 계획
**목적**: 기업 재무제표 모델에 주요 투자 지표(PER, PBR, ROE, 부채비율, 배당수익률) 추가 및 자동 계산 로직 구현

---

## 1. 개요

투자자들이 기업을 분석할 때 필수적으로 사용하는 주요 재무 지표를 `FinancialStatement` 모델에 추가하고, 이를 자동으로 계산하여 API를 통해 제공합니다.

### 추가할 재무 지표

| 지표 | 설명 | 계산식 | 단위 |
|------|------|--------|------|
| **PER** | 주가수익비율 (Price Earnings Ratio) | 시가총액 ÷ 당기순이익 | 배 |
| **PBR** | 주가순자산비율 (Price Book-value Ratio) | 시가총액 ÷ 총자본 | 배 |
| **ROE** | 자기자본이익률 (Return On Equity) | (당기순이익 ÷ 총자본) × 100 | % |
| **부채비율** | 부채비율 (Debt Ratio) | (총부채 ÷ 총자본) × 100 | % |
| **배당수익률** | 배당수익률 (Dividend Yield) | (연간 배당금 ÷ 현재 주가) × 100 | % |

---

## 2. 현재 상태 분석

### 기존 데이터 구조

#### Company 모델
```python
class Company(models.Model):
    stock_code = models.CharField(primary_key=True, max_length=6)
    company_name = models.CharField(max_length=255)
    market_amount = models.BigIntegerField(default=0)  # 시가총액 ✅
    # ... 기타 필드
```

#### FinancialStatement 모델
```python
class FinancialStatement(models.Model):
    company = models.ForeignKey(Company, ...)
    fiscal_year = models.IntegerField()  # 사업연도
    report_code = models.CharField(max_length=5)  # 보고서 코드

    # 기존 재무 데이터
    revenue = models.BigIntegerField(null=True)  # 매출액 ✅
    operating_profit = models.BigIntegerField(null=True)  # 영업이익 ✅
    net_income = models.BigIntegerField(null=True)  # 당기순이익 ✅
    total_assets = models.BigIntegerField(null=True)  # 총자산 ✅
    total_liabilities = models.BigIntegerField(null=True)  # 총부채 ✅
    total_equity = models.BigIntegerField(null=True)  # 총자본 ✅
```

### 계산 가능 여부 분석

| 지표 | 필요 데이터 | 보유 데이터 | 추가 필요 데이터 |
|------|-------------|-------------|------------------|
| ROE | 당기순이익, 총자본 | ✅ FinancialStatement | - |
| 부채비율 | 총부채, 총자본 | ✅ FinancialStatement | - |
| PER | 시가총액, 당기순이익 | ✅ Company.market_amount<br>✅ FinancialStatement.net_income | - |
| PBR | 시가총액, 총자본 | ✅ Company.market_amount<br>✅ FinancialStatement.total_equity | - |
| 배당수익률 | 배당금, 주가 | ❌ 없음 | ✅ 배당금 (DART API)<br>✅ 현재 주가 (StockPrice 또는 KIS API) |

---

## 3. 데이터베이스 설계

### 3.1. FinancialStatement 모델 필드 추가

```python
class FinancialStatement(models.Model):
    # ... 기존 필드 ...

    # 추가: 계산된 재무 지표
    per = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        verbose_name="PER (주가수익비율)",
        help_text="시가총액 ÷ 당기순이익"
    )
    pbr = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        verbose_name="PBR (주가순자산비율)",
        help_text="시가총액 ÷ 총자본"
    )
    roe = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        verbose_name="ROE (자기자본이익률)",
        help_text="(당기순이익 ÷ 총자본) × 100"
    )
    debt_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        verbose_name="부채비율",
        help_text="(총부채 ÷ 총자본) × 100"
    )
    dividend_yield = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        verbose_name="배당수익률",
        help_text="(연간 배당금 ÷ 현재 주가) × 100"
    )

    # 메타 정보
    metrics_calculated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="지표 계산 시간",
        help_text="마지막으로 재무 지표를 계산한 시간"
    )
```

### 3.2. Dividend 모델 추가 (배당 정보)

```python
class Dividend(models.Model):
    """배당 정보"""

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="dividends",
        db_column="company_id",
    )
    fiscal_year = models.IntegerField()  # 배당 기준 연도
    dividend_per_share = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="주당 배당금",
        help_text="단위: 원"
    )
    dividend_type = models.CharField(
        max_length=20,
        choices=[
            ("cash", "현금배당"),
            ("stock", "주식배당"),
        ],
        default="cash",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dividend"
        unique_together = ["company", "fiscal_year", "dividend_type"]
        ordering = ["-fiscal_year"]
```

---

## 4. 계산 로직 설계

### 4.1. FinancialMetricsService 생성

**파일**: `companies/services/financial_metrics.py`

```python
"""
재무 지표 계산 서비스
PER, PBR, ROE, 부채비율, 배당수익률을 계산합니다.
"""
from decimal import Decimal, InvalidOperation
import logging
from typing import Optional

from companies.models import Company, FinancialStatement, Dividend
from core.models import StockPrice  # 주가 데이터

logger = logging.getLogger(__name__)


class FinancialMetricsService:
    """재무 지표 계산 서비스"""

    @staticmethod
    def calculate_roe(net_income: int, total_equity: int) -> Optional[Decimal]:
        """
        ROE (자기자본이익률) 계산

        Args:
            net_income: 당기순이익
            total_equity: 총자본

        Returns:
            ROE (%), None if 계산 불가
        """
        if not total_equity or total_equity <= 0:
            return None

        try:
            roe = (Decimal(net_income) / Decimal(total_equity)) * 100
            return round(roe, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_debt_ratio(
        total_liabilities: int,
        total_equity: int
    ) -> Optional[Decimal]:
        """
        부채비율 계산

        Args:
            total_liabilities: 총부채
            total_equity: 총자본

        Returns:
            부채비율 (%), None if 계산 불가
        """
        if not total_equity or total_equity <= 0:
            return None

        try:
            debt_ratio = (Decimal(total_liabilities) / Decimal(total_equity)) * 100
            return round(debt_ratio, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_per(
        market_cap: int,
        net_income: int
    ) -> Optional[Decimal]:
        """
        PER (주가수익비율) 계산

        Args:
            market_cap: 시가총액
            net_income: 당기순이익

        Returns:
            PER (배), None if 계산 불가
        """
        if not net_income or net_income <= 0:
            return None

        try:
            per = Decimal(market_cap) / Decimal(net_income)
            return round(per, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_pbr(
        market_cap: int,
        total_equity: int
    ) -> Optional[Decimal]:
        """
        PBR (주가순자산비율) 계산

        Args:
            market_cap: 시가총액
            total_equity: 총자본

        Returns:
            PBR (배), None if 계산 불가
        """
        if not total_equity or total_equity <= 0:
            return None

        try:
            pbr = Decimal(market_cap) / Decimal(total_equity)
            return round(pbr, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_dividend_yield(
        dividend_per_share: Decimal,
        current_price: int
    ) -> Optional[Decimal]:
        """
        배당수익률 계산

        Args:
            dividend_per_share: 주당 배당금
            current_price: 현재 주가

        Returns:
            배당수익률 (%), None if 계산 불가
        """
        if not current_price or current_price <= 0:
            return None

        try:
            dividend_yield = (dividend_per_share / Decimal(current_price)) * 100
            return round(dividend_yield, 2)
        except (InvalidOperation, ZeroDivisionError):
            return None

    def calculate_all_metrics(
        self,
        financial_statement: FinancialStatement
    ) -> dict:
        """
        재무제표에 대한 모든 지표 계산

        Args:
            financial_statement: FinancialStatement 인스턴스

        Returns:
            계산된 지표 딕셔너리
        """
        company = financial_statement.company

        # 1. ROE 계산 (재무제표 데이터만 사용)
        roe = self.calculate_roe(
            financial_statement.net_income or 0,
            financial_statement.total_equity or 0
        )

        # 2. 부채비율 계산 (재무제표 데이터만 사용)
        debt_ratio = self.calculate_debt_ratio(
            financial_statement.total_liabilities or 0,
            financial_statement.total_equity or 0
        )

        # 3. PER 계산 (시가총액 + 재무제표)
        per = self.calculate_per(
            company.market_amount,
            financial_statement.net_income or 0
        )

        # 4. PBR 계산 (시가총액 + 재무제표)
        pbr = self.calculate_pbr(
            company.market_amount,
            financial_statement.total_equity or 0
        )

        # 5. 배당수익률 계산 (배당금 + 현재가)
        dividend_yield = None
        try:
            # 해당 연도 배당금 조회
            dividend = Dividend.objects.filter(
                company=company,
                fiscal_year=financial_statement.fiscal_year,
                dividend_type="cash"
            ).first()

            if dividend:
                # 현재가 조회 (최신 StockPrice)
                latest_price = StockPrice.objects.filter(
                    company=company
                ).order_by("-timestamp").first()

                if latest_price:
                    dividend_yield = self.calculate_dividend_yield(
                        dividend.dividend_per_share,
                        latest_price.close_price
                    )
        except Exception as e:
            logger.warning(f"배당수익률 계산 실패: {company.stock_code} - {e}")

        return {
            "roe": roe,
            "debt_ratio": debt_ratio,
            "per": per,
            "pbr": pbr,
            "dividend_yield": dividend_yield,
        }

    def update_financial_metrics(
        self,
        financial_statement: FinancialStatement
    ) -> FinancialStatement:
        """
        재무제표의 지표를 계산하여 업데이트

        Args:
            financial_statement: FinancialStatement 인스턴스

        Returns:
            업데이트된 FinancialStatement 인스턴스
        """
        from django.utils import timezone

        metrics = self.calculate_all_metrics(financial_statement)

        financial_statement.roe = metrics["roe"]
        financial_statement.debt_ratio = metrics["debt_ratio"]
        financial_statement.per = metrics["per"]
        financial_statement.pbr = metrics["pbr"]
        financial_statement.dividend_yield = metrics["dividend_yield"]
        financial_statement.metrics_calculated_at = timezone.now()

        financial_statement.save(update_fields=[
            "roe", "debt_ratio", "per", "pbr", "dividend_yield",
            "metrics_calculated_at"
        ])

        logger.info(
            f"재무 지표 계산 완료: {financial_statement.company.stock_code} "
            f"({financial_statement.fiscal_year}년)"
        )

        return financial_statement
```

### 4.2. DART API 배당 정보 조회 추가

**파일**: `companies/services/dart_api.py`

```python
class DartAPIClient:
    # ... 기존 메서드 ...

    def get_dividend_info(
        self,
        corp_code: str,
        bsns_year: str,  # 사업연도 (예: "2024")
        reprt_code: str = "11011",  # 11011: 사업보고서
    ) -> Dict[str, Any]:
        """
        배당에 관한 사항 조회

        Args:
            corp_code: 고유번호
            bsns_year: 사업연도
            reprt_code: 보고서 코드

        Returns:
            배당 정보 딕셔너리
        """
        params = {
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
        }
        return self._request("alotMatter.json", params, allow_empty=True)
```

### 4.3. 배당 정보 동기화 서비스

**파일**: `companies/services/dividend.py`

```python
"""
배당 정보 동기화 서비스
"""
from decimal import Decimal
import logging
from typing import List

from companies.models import Company, Dividend
from companies.services.dart_api import DartAPIClient, DartAPIError

logger = logging.getLogger(__name__)


class DividendService:
    """배당 정보 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    def sync_dividend_info(
        self,
        company: Company,
        year: int
    ) -> List[Dividend]:
        """
        DART API에서 배당 정보를 조회하여 저장

        Args:
            company: Company 인스턴스
            year: 사업연도

        Returns:
            생성/업데이트된 Dividend 인스턴스 리스트
        """
        if not company.corp_code:
            raise ValueError(f"Company {company.stock_code}에 corp_code가 없습니다.")

        try:
            # DART API 호출
            data = self.dart_client.get_dividend_info(
                corp_code=company.corp_code,
                bsns_year=str(year),
                reprt_code="11011"  # 사업보고서
            )

            dividend_list = data.get("list", [])
            if not dividend_list:
                logger.info(f"배당 정보 없음: {company.stock_code} ({year}년)")
                return []

            dividends = []
            for item in dividend_list:
                try:
                    # 주당 배당금 파싱 (예: "1,500원" -> 1500)
                    dividend_per_share_str = item.get("se", "0")
                    dividend_per_share = Decimal(
                        dividend_per_share_str.replace(",", "").replace("원", "")
                    )

                    # 배당 유형 (현금배당/주식배당)
                    dividend_type = "cash"  # DART API 응답 구조에 따라 조정

                    dividend, created = Dividend.objects.update_or_create(
                        company=company,
                        fiscal_year=year,
                        dividend_type=dividend_type,
                        defaults={
                            "dividend_per_share": dividend_per_share,
                        }
                    )
                    dividends.append(dividend)

                except (KeyError, ValueError, InvalidOperation) as e:
                    logger.warning(f"배당 데이터 파싱 오류: {e}")
                    continue

            logger.info(
                f"배당 정보 동기화 완료: {company.stock_code} ({year}년, {len(dividends)}건)"
            )
            return dividends

        except DartAPIError as e:
            logger.error(f"DART API 오류 (배당 정보): {e}")
            raise
```

---

## 5. Celery 태스크 설계

### 5.1. 재무 지표 계산 태스크

**파일**: `companies/tasks/financial_metrics.py`

```python
"""
재무 지표 계산 Celery 태스크
"""
from celery import shared_task
import logging

from companies.models import Company, FinancialStatement
from companies.services.financial_metrics import FinancialMetricsService
from companies.services.dividend import DividendService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def calculate_financial_metrics_task(self, stock_code: str, fiscal_year: int):
    """
    특정 기업의 특정 연도 재무 지표 계산

    Args:
        stock_code: 종목코드
        fiscal_year: 사업연도
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        # 사업보고서 재무제표 조회
        financial_statement = FinancialStatement.objects.filter(
            company=company,
            fiscal_year=fiscal_year,
            report_code="11011"  # 사업보고서
        ).first()

        if not financial_statement:
            logger.warning(
                f"재무제표 없음: {stock_code} ({fiscal_year}년)"
            )
            return

        # 재무 지표 계산
        service = FinancialMetricsService()
        service.update_financial_metrics(financial_statement)

        logger.info(
            f"재무 지표 계산 완료: {stock_code} ({fiscal_year}년)"
        )

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except Exception as e:
        logger.error(f"재무 지표 계산 오류: {stock_code} - {e}")
        raise self.retry(countdown=60, exc=e)


@shared_task(bind=True, max_retries=3)
def sync_dividend_and_calculate_task(self, stock_code: str, fiscal_year: int):
    """
    배당 정보 동기화 후 재무 지표 계산

    Args:
        stock_code: 종목코드
        fiscal_year: 사업연도
    """
    try:
        company = Company.objects.get(pk=stock_code, is_deleted=False)

        # 1. 배당 정보 동기화
        dividend_service = DividendService()
        dividend_service.sync_dividend_info(company, fiscal_year)

        # 2. 재무 지표 계산
        calculate_financial_metrics_task.delay(stock_code, fiscal_year)

    except Company.DoesNotExist:
        logger.error(f"Company not found: {stock_code}")
    except Exception as e:
        logger.error(f"배당 동기화 및 지표 계산 오류: {stock_code} - {e}")
        raise self.retry(countdown=60, exc=e)


@shared_task
def calculate_all_companies_metrics():
    """
    모든 기업의 최신 연도 재무 지표 계산 (주기적 실행용)
    """
    from datetime import datetime

    current_year = datetime.now().year
    companies = Company.objects.filter(is_deleted=False, corp_code__isnull=False)

    total = companies.count()
    logger.info(f"전체 기업 재무 지표 계산 시작: {total}개 기업")

    for company in companies:
        try:
            # 최근 3년 재무 지표 계산
            for year in range(current_year - 3, current_year):
                sync_dividend_and_calculate_task.delay(
                    company.stock_code,
                    year
                )
        except Exception as e:
            logger.error(
                f"재무 지표 계산 작업 등록 실패: {company.stock_code} - {e}"
            )

    logger.info(f"전체 기업 재무 지표 계산 작업 등록 완료: {total}개")
```

### 5.2. Celery Beat 스케줄 추가

**파일**: `config/celery.py`

```python
# Celery Beat 스케줄에 추가
app.conf.beat_schedule = {
    # ... 기존 스케줄 ...

    # 재무 지표 계산 (주 1회, 일요일 오전 2시)
    'calculate-financial-metrics-weekly': {
        'task': 'companies.tasks.financial_metrics.calculate_all_companies_metrics',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),
    },
}
```

---

## 6. API 응답 수정

### 6.1. Serializer 수정

**파일**: `companies/serializers.py`

```python
class FinancialStatementSerializer(serializers.ModelSerializer):
    """재무제표 시리얼라이저"""

    class Meta:
        model = FinancialStatement
        fields = [
            "fiscal_year",
            "report_code",
            "revenue",
            "operating_profit",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
            # 추가: 재무 지표
            "roe",
            "debt_ratio",
            "per",
            "pbr",
            "dividend_yield",
            "metrics_calculated_at",
        ]
```

### 6.2. API 응답 예시

**GET** `/api/companies/{stock_code}/financials/`

```json
{
  "status": 200,
  "message": "재무 지표 조회 성공",
  "data": [
    {
      "fiscal_year": 2024,
      "report_code": "11011",
      "revenue": 30000000000000,
      "operating_profit": 5000000000000,
      "net_income": 3500000000000,
      "total_assets": 50000000000000,
      "total_liabilities": 20000000000000,
      "total_equity": 30000000000000,
      "roe": 11.67,
      "debt_ratio": 66.67,
      "per": 12.34,
      "pbr": 1.45,
      "dividend_yield": 2.15,
      "metrics_calculated_at": "2026-01-18T10:30:00Z"
    }
  ]
}
```

---

## 7. 구현 단계

### Phase 1: 모델 및 마이그레이션 (1일)

- [ ] `FinancialStatement` 모델에 재무 지표 필드 추가
- [ ] `Dividend` 모델 생성
- [ ] 마이그레이션 생성 및 적용
- [ ] 테스트: 모델 생성 및 저장 확인

### Phase 2: 계산 로직 구현 (2일)

- [ ] `FinancialMetricsService` 구현
  - [ ] `calculate_roe()` 메서드
  - [ ] `calculate_debt_ratio()` 메서드
  - [ ] `calculate_per()` 메서드
  - [ ] `calculate_pbr()` 메서드
  - [ ] `calculate_dividend_yield()` 메서드
  - [ ] `calculate_all_metrics()` 메서드
  - [ ] `update_financial_metrics()` 메서드
- [ ] 유닛 테스트 작성
- [ ] 엣지 케이스 처리 (0 나누기, None 값 등)

### Phase 3: 배당 정보 수집 (2일)

- [ ] DART API 배당 조회 메서드 추가
- [ ] `DividendService` 구현
  - [ ] `sync_dividend_info()` 메서드
- [ ] 배당 정보 파싱 및 저장 로직
- [ ] 테스트: DART API 호출 및 데이터 저장 확인

### Phase 4: Celery 태스크 구현 (1일)

- [ ] `calculate_financial_metrics_task` 태스크 작성
- [ ] `sync_dividend_and_calculate_task` 태스크 작성
- [ ] `calculate_all_companies_metrics` 배치 태스크 작성
- [ ] Celery Beat 스케줄 설정
- [ ] 테스트: 태스크 실행 및 결과 확인

### Phase 5: API 수정 (1일)

- [ ] Serializer에 재무 지표 필드 추가
- [ ] API 응답에 재무 지표 포함
- [ ] Swagger 문서 업데이트
- [ ] 테스트: API 응답 확인

### Phase 6: 기존 데이터 처리 (1일)

- [ ] 기존 재무제표에 대해 재무 지표 일괄 계산 스크립트 작성
- [ ] 실행 및 검증
- [ ] 로그 확인 및 오류 수정

### Phase 7: 테스트 및 문서화 (1일)

- [ ] 통합 테스트 작성
- [ ] API 문서 업데이트 (`docs/API-REFERENCE.md`)
- [ ] 사용자 가이드 작성
- [ ] 코드 리뷰 및 최적화

---

## 8. 주의사항 및 고려사항

### 8.1. 데이터 정합성

- **시가총액 동기화**: Company.market_amount가 최신 값인지 확인 필요
- **재무제표 버전**: 사업보고서(11011) 우선, 없을 경우 반기보고서(11012) 사용
- **배당금 기준**: 현금배당 기준, 주식배당은 별도 처리

### 8.2. 성능 최적화

- **배치 처리**: 대량 계산 시 bulk_update 사용
- **캐싱**: 자주 조회되는 재무 지표는 Redis 캐싱 고려
- **비동기 처리**: Celery 태스크로 계산 부하 분산

### 8.3. 오류 처리

- **0으로 나누기**: 분모가 0이거나 음수일 때 None 반환
- **데이터 없음**: 재무제표나 배당 정보가 없을 때 적절한 메시지 반환
- **API 실패**: DART API 호출 실패 시 재시도 로직

### 8.4. 예외 상황

- **적자 기업**: 당기순이익이 음수일 때 PER은 음수 또는 None
- **자본잠식**: 총자본이 음수일 때 PBR, ROE 계산 불가
- **무배당**: 배당금이 0일 때 배당수익률은 0%

### 8.5. 주가 데이터 소스

현재 시스템에서 주가 데이터는 다음 소스에서 가져올 수 있습니다:

1. **StockPrice 모델** (실시간 스트리밍 데이터)
   - `core.models.StockPrice`에서 최신 종가 조회
   - 가장 정확한 현재가 데이터

2. **Company.market_amount** (시가총액)
   - KIS API로 주기적으로 업데이트
   - 배당수익률 계산 시 `시가총액 / 발행주식수`로 주가 역산 가능

**권장**: StockPrice 모델의 최신 종가 사용 (우선순위 1)

---

## 9. 테스트 시나리오

### 9.1. 단위 테스트

```python
# tests/test_financial_metrics.py

def test_calculate_roe():
    """ROE 계산 테스트"""
    service = FinancialMetricsService()

    # 정상 케이스
    roe = service.calculate_roe(net_income=1000000, total_equity=10000000)
    assert roe == Decimal("10.00")

    # 0으로 나누기
    roe = service.calculate_roe(net_income=1000000, total_equity=0)
    assert roe is None

    # 음수 자본
    roe = service.calculate_roe(net_income=1000000, total_equity=-1000000)
    assert roe is None


def test_calculate_per():
    """PER 계산 테스트"""
    service = FinancialMetricsService()

    # 정상 케이스
    per = service.calculate_per(market_cap=100000000, net_income=10000000)
    assert per == Decimal("10.00")

    # 적자 기업
    per = service.calculate_per(market_cap=100000000, net_income=-5000000)
    assert per is None
```

### 9.2. 통합 테스트

```python
def test_update_financial_metrics_integration():
    """재무 지표 통합 테스트"""
    # 1. 기업 및 재무제표 생성
    company = Company.objects.create(
        stock_code="005930",
        company_name="삼성전자",
        market_amount=400000000000000,
    )

    financial = FinancialStatement.objects.create(
        company=company,
        fiscal_year=2024,
        report_code="11011",
        net_income=35000000000000,
        total_assets=500000000000000,
        total_liabilities=200000000000000,
        total_equity=300000000000000,
    )

    # 2. 재무 지표 계산
    service = FinancialMetricsService()
    service.update_financial_metrics(financial)

    # 3. 검증
    financial.refresh_from_db()
    assert financial.roe is not None
    assert financial.debt_ratio is not None
    assert financial.per is not None
    assert financial.pbr is not None
    assert financial.metrics_calculated_at is not None
```

---

## 10. 마이그레이션 전략

### 10.1. 신규 필드 추가 마이그레이션

```bash
# 마이그레이션 생성
python manage.py makemigrations companies

# 마이그레이션 적용
python manage.py migrate companies
```

### 10.2. 기존 데이터 처리 스크립트

```python
# management/commands/calculate_existing_metrics.py

from django.core.management.base import BaseCommand
from companies.models import FinancialStatement
from companies.services.financial_metrics import FinancialMetricsService

class Command(BaseCommand):
    help = "기존 재무제표에 대해 재무 지표 일괄 계산"

    def handle(self, *args, **options):
        service = FinancialMetricsService()

        statements = FinancialStatement.objects.filter(
            metrics_calculated_at__isnull=True
        )

        total = statements.count()
        self.stdout.write(f"처리할 재무제표: {total}건")

        for i, statement in enumerate(statements, 1):
            try:
                service.update_financial_metrics(statement)
                self.stdout.write(f"[{i}/{total}] 완료: {statement.company.stock_code}")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"[{i}/{total}] 실패: {statement.company.stock_code} - {e}"
                    )
                )
```

실행:
```bash
python manage.py calculate_existing_metrics
```

---

## 11. 모니터링 및 운영

### 11.1. 로그 모니터링

재무 지표 계산 관련 로그를 모니터링하여 오류 파악:

```python
# 주요 로그 메시지
logger.info(f"재무 지표 계산 완료: {stock_code} ({fiscal_year}년)")
logger.warning(f"배당수익률 계산 실패: {stock_code} - {e}")
logger.error(f"재무 지표 계산 오류: {stock_code} - {e}")
```

### 11.2. 데이터 품질 검증

주기적으로 계산된 지표의 범위 검증:

- PER: 일반적으로 -100 ~ 100 범위
- PBR: 일반적으로 0 ~ 10 범위
- ROE: 일반적으로 -50% ~ 50% 범위
- 부채비율: 일반적으로 0% ~ 500% 범위
- 배당수익률: 일반적으로 0% ~ 10% 범위

이상치 발견 시 데이터 재확인 필요

### 11.3. Celery 태스크 모니터링

Flower를 통해 재무 지표 계산 태스크 상태 모니터링:

```bash
# Flower 접속
http://localhost:5555
```

---

## 12. FAQ

### Q1. 적자 기업의 PER은 어떻게 처리하나요?

A1. 당기순이익이 0 이하일 경우 PER을 `None`으로 반환하여 "계산 불가" 상태를 나타냅니다. API 응답에서는 `null`로 표시됩니다.

### Q2. 재무 지표는 얼마나 자주 업데이트되나요?

A2.
- **재무제표 동기화 시**: 새 재무제표가 저장되면 자동으로 계산
- **주기적 재계산**: Celery Beat으로 주 1회 (일요일 오전 2시) 전체 기업 재계산
- **시가총액 변경 시**: 시가총액이 업데이트되면 PER, PBR 재계산 필요

### Q3. 배당 정보가 없는 기업은 어떻게 처리하나요?

A3. 배당수익률을 `None`으로 설정하며, API 응답에서는 `null`로 표시됩니다. 무배당 기업으로 간주합니다.

### Q4. 사업보고서와 반기보고서 중 어느 것을 우선하나요?

A4. 사업보고서(11011)를 우선 사용합니다. 사업보고서가 없을 경우 반기보고서(11012)를 사용할 수 있습니다.

---

## 13. 참고 자료

- [DART OpenAPI 가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018)
- [재무 비율 계산 방법](https://www.investopedia.com/financial-ratios-4689817)
- Django DecimalField 사용법
- Celery Best Practices

---

**문서 버전**: 1.0
**마지막 업데이트**: 2026-01-18
