# companies/models.py

from django.db import models


class Company(models.Model):
    stock_code = models.CharField(primary_key=True, max_length=10)  # 종목코드 (6자리)
    corp_code = models.CharField(
        max_length=8, unique=True, null=True
    )  # DART 고유번호 (8자리) - 신규
    induty_code = models.CharField(
        max_length=20, null=True, blank=True, db_index=True
    )  # 업종코드 (KSIC 코드, 예: "264", "26", "C26")
    company_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    logo_url = models.URLField(max_length=500, blank=True, null=True)  # 신규
    market_amount = models.BigIntegerField(default=0)  # 시가총액
    # DART 기업개황 추가 필드
    ceo_name = models.CharField(max_length=100, blank=True, null=True)  # 대표자명
    establishment_date = models.DateField(null=True)  # 설립일
    homepage_url = models.URLField(max_length=500, blank=True, null=True)  # 홈페이지
    address = models.TextField(blank=True, null=True)  # 본사 주소

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "company"


class FinancialStatement(models.Model):
    """기업 재무제표 데이터"""

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="financial_statements",
        to_field="stock_code",
        db_column="company_id",
    )
    fiscal_year = models.IntegerField()  # 사업연도 (예: 2024)
    report_code = models.CharField(
        max_length=5
    )  # 보고서 코드 (11011: 사업보고서, 11012: 반기보고서 등)

    # 주요 재무 지표 (단위: 원)
    revenue = models.BigIntegerField(null=True)  # 매출액
    operating_profit = models.BigIntegerField(null=True)  # 영업이익
    net_income = models.BigIntegerField(null=True)  # 당기순이익
    total_assets = models.BigIntegerField(null=True)  # 총자산
    total_liabilities = models.BigIntegerField(null=True)  # 총부채
    total_equity = models.BigIntegerField(null=True)  # 총자본

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "financial_statement"
        unique_together = ["company", "fiscal_year", "report_code"]
        ordering = ["-fiscal_year", "-report_code"]


class RevenueComposition(models.Model):
    """매출 구성 데이터"""

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="revenue_compositions",
        to_field="stock_code",
        db_column="company_id",
    )
    fiscal_year = models.IntegerField()  # 사업연도
    segment_name = models.CharField(max_length=255)  # 사업부문명
    revenue = models.BigIntegerField()  # 매출액
    ratio = models.DecimalField(
        max_digits=5, decimal_places=2, null=True
    )  # 매출 비중 (%)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "revenue_composition"
        ordering = ["-fiscal_year", "-revenue"]


class Report(models.Model):
    """기업 공시 보고서"""

    REPORT_TYPE_CHOICES = [
        ("A", "정기공시"),
        ("B", "주요사항보고"),
        ("C", "발행공시"),
        ("D", "지분공시"),
        ("E", "기타공시"),
        ("F", "외부감사관련"),
        ("G", "펀드공시"),
        ("H", "자산유동화"),
        ("I", "거래소공시"),
        ("J", "공정위공시"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="reports",
        to_field="stock_code",
        db_column="company_id",
    )
    rcept_no = models.CharField(max_length=20, unique=True)  # 접수번호
    report_name = models.CharField(max_length=500)  # 보고서명
    report_type = models.CharField(
        max_length=1, choices=REPORT_TYPE_CHOICES
    )  # 공시유형
    submitted_at = models.DateField()  # 접수일자
    report_url = models.URLField(max_length=500)  # 보고서 URL

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "report"
        ordering = ["-submitted_at"]

        

class CompanyRanking(models.Model):
    ranking_id = models.BigIntegerField(primary_key=True) # 순위 아이디
    stock_code = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='rankings', db_column='stock_code') # 종목코드
    rank = models.IntegerField() # 순위
    base_date = models.DateField() # 기준 날짜
    created_at = models.DateTimeField(auto_now_add=True) # 생성 일시
    updated_at = models.DateTimeField(auto_now=True) # 수정 일시
    is_deleted = models.BooleanField(default=False) # 삭제 여부

    class Meta:
        db_table = 'company_ranking'

        

        
