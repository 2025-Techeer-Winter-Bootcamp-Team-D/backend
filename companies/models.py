# companies/models.py

from django.db import models
from industries.models import Industry


class Company(models.Model):
    # 시장 구분 선택지 (DART API corp_cls 매핑)
    MARKET_CHOICES = [
        ("KOSPI", "유가증권"),  # corp_cls: Y
        ("KOSDAQ", "코스닥"),  # corp_cls: K
    ]

    stock_code = models.CharField(primary_key=True, max_length=6)  # 종목코드 (6자리)
    corp_code = models.CharField(
        max_length=8, unique=True, null=True
    )  # DART 고유번호 (8자리) - 신규
    industry = models.ForeignKey(
        Industry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companies",
        db_column="industry_id",
    )  # Industry와의 관계
    induty_code = models.CharField(
        max_length=20, null=True, blank=True, db_index=True
    )  # 업종코드 (KSIC 코드, 예: "264", "26", "C26")
    original_ksic_code = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="원본 KSIC 코드",
        help_text="DART API에서 가져온 원본 업종코드 (KIS 변환 전)",
    )  # 원본 KSIC 코드 보관 (매핑 검증 및 롤백용)
    market = models.CharField(
        max_length=10,
        choices=MARKET_CHOICES,
        null=True,
        blank=True,
        db_index=True,
    )  # 시장 구분 (DART API corp_cls로부터 매핑)
    company_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    logo_url = models.URLField(max_length=500, blank=True, null=True)  # 신규
    market_amount = models.BigIntegerField(default=0)  # 시가총액
    # DART 기업개황 추가 필드
    ceo_name = models.CharField(max_length=100, blank=True, null=True)  # 대표자명
    establishment_date = models.DateField(null=True)  # 설립일
    homepage_url = models.URLField(max_length=500, blank=True, null=True)  # 홈페이지
    address = models.TextField(blank=True, null=True)  # 본사 주소

    # 동기화 추적 필드
    last_info_synced_at = models.DateTimeField(
        null=True, blank=True, verbose_name="마지막 정보 동기화 시간"
    )  # DART 기업 정보 동기화 시간 (시가총액 갱신은 제외)

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

    # 계산된 재무 지표
    per = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="PER (주가수익비율)",
        help_text="시가총액 ÷ 당기순이익",
    )
    pbr = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="PBR (주가순자산비율)",
        help_text="시가총액 ÷ 총자본",
    )
    roe = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="ROE (자기자본이익률)",
        help_text="(당기순이익 ÷ 총자본) × 100",
    )
    debt_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="부채비율",
        help_text="(총부채 ÷ 총자본) × 100",
    )
    dividend_yield = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="배당수익률",
        help_text="(연간 배당금 ÷ 현재 주가) × 100",
    )
    eps = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="EPS (주당순이익)",
        help_text="당기순이익 ÷ 발행주식수",
    )
    operating_profit_margin = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="영업이익률",
        help_text="(영업이익 ÷ 매출액) × 100",
    )
    yoy_revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="매출액 YoY",
        help_text="전년 대비 매출액 성장률 (%)",
    )
    yoy_operating_profit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="영업이익 YoY",
        help_text="전년 대비 영업이익 성장률 (%)",
    )
    yoy_net_income = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="당기순이익 YoY",
        help_text="전년 대비 당기순이익 성장률 (%)",
    )

    # 메타 정보
    metrics_calculated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="지표 계산 시간",
        help_text="마지막으로 재무 지표를 계산한 시간",
    )

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

    PROCESSING_STATUS_CHOICES = [
        ("pending", "대기"),
        ("processing", "처리중"),
        ("completed", "완료"),
        ("failed", "실패"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="reports",
        db_column="company_id",
    )
    rcept_no = models.CharField(max_length=20, unique=True)  # 접수번호
    report_name = models.CharField(max_length=500)  # 보고서명
    report_type = models.CharField(
        max_length=1, choices=REPORT_TYPE_CHOICES
    )  # 공시유형
    submitted_at = models.DateField()  # 접수일자
    report_url = models.URLField(max_length=500)  # 보고서 URL

    # 보고서 처리 관련 필드 (신규)
    raw_content = models.TextField(null=True, blank=True, verbose_name="원본 본문")
    refined_content = models.TextField(
        null=True, blank=True, verbose_name="정제된 본문"
    )
    extracted_info = models.JSONField(
        null=True, blank=True, verbose_name="구조화된 추출 정보"
    )
    primary_keyword = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="주요 키워드",
    )
    embedding = models.JSONField(null=True, blank=True, verbose_name="벡터 임베딩")
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="처리 완료 시간"
    )
    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default="pending",
        verbose_name="처리 상태",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "report"
        ordering = ["-submitted_at"]


class Dividend(models.Model):
    """배당 정보"""

    DIVIDEND_TYPE_CHOICES = [
        ("cash", "현금배당"),
        ("stock", "주식배당"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="dividends",
        db_column="company_id",
    )
    fiscal_year = models.IntegerField(verbose_name="배당 기준 연도")  # 배당 기준 연도
    dividend_per_share = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="주당 배당금",
        help_text="단위: 원",
    )
    dividend_type = models.CharField(
        max_length=20,
        choices=DIVIDEND_TYPE_CHOICES,
        default="cash",
        verbose_name="배당 유형",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dividend"
        unique_together = ["company", "fiscal_year", "dividend_type"]
        ordering = ["-fiscal_year"]


class CompanyRanking(models.Model):
    ranking_id = models.BigIntegerField(primary_key=True)  # 순위 아이디
    stock_code = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="rankings",
        db_column="stock_code",
    )  # 종목코드
    rank = models.IntegerField()  # 순위
    base_date = models.DateField()  # 기준 날짜
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 일시
    updated_at = models.DateTimeField(auto_now=True)  # 수정 일시
    is_deleted = models.BooleanField(default=False)  # 삭제 여부

    class Meta:
        db_table = "company_ranking"


#sankey 모델(판관비,원가,순수익,기타 저장)
class SankeyData(models.Model):
    """
    기업별 산키 다이어그램 데이터 시각화를 위한 가공 데이터 모델
    """
    # 동일 앱 내 Company 모델 참조 (1:N 관계)
    company = models.ForeignKey(
        'Company', 
        on_delete=models.CASCADE, 
        related_name='sankey_data'
    )
    fiscal_year = models.IntegerField()
    
    # 시각화용 데이터 (리스트 구조)
    nodes = models.JSONField(default=list)  # 예: [{"name": "매출액"}, ...]
    links = models.JSONField(default=list)  # 예: [{"source": "반도체", "target": "매출액", "value": 100}, ...]
    
    # 재무 상태 요약
    is_loss = models.BooleanField(default=False) # 적자 여부
    
    # 실제 DB 수치 원본 보관 (오른쪽 노드 및 분석용)
    raw_values = models.JSONField(default=dict) 
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # 한 기업당 연도별로 하나의 데이터만 존재하도록 설정
        unique_together = ('company', 'fiscal_year')

    def __str__(self):
        return f"{self.company.company_name} ({self.fiscal_year}) - Sankey Data"


