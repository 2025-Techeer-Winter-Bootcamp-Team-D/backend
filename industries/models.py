# industries/models.py
from django.db import models


class Industry(models.Model):
    # ERD상 산업 아이디 (PK)
    industry_id = models.BigAutoField(primary_key=True)
    # 산업 이름
    name = models.CharField(max_length=255)
    # 업종코드 (KSIC 코드, 예: "264", "26", "C26")
    induty_code = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True
    )
    # 산업 설명
    description = models.TextField(null=True, blank=True)
    # 생성/수정/삭제 필드 (공통)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "industry"  # 실제 DB 테이블명 고정


class IndustryRanking(models.Model):
    ranking_id = models.BigIntegerField(primary_key=True)  # 순위 아이디
    industry = models.ForeignKey(
        Industry,
        on_delete=models.CASCADE,
        related_name="rankings",
        db_column="industry_id",
    )  # 산업 아이디
    rank = models.IntegerField()  # 순위
    amount = models.BigIntegerField()  # 시가총액 합계
    base_date = models.DateField()  # 기준 날짜
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 일시
    updated_at = models.DateTimeField(auto_now=True)  # 수정 일시
    is_deleted = models.BooleanField(default=False)  # 삭제 여부

    class Meta:
        db_table = "industry_ranking"


# ==================== 산업 지수 차트 모델들 ====================


class IndustryChartBase(models.Model):
    """산업 지수 차트 기본 모델 (추상 모델)"""

    industry = models.ForeignKey(Industry, on_delete=models.CASCADE)
    base_date = models.DateField(db_index=True)  # 기준 날짜

    # OHLC 데이터
    open = models.FloatField()  # 시가
    high = models.FloatField()  # 고가
    low = models.FloatField()  # 저가
    close = models.FloatField()  # 종가

    # 변동 데이터
    change_value = models.FloatField(null=True, blank=True)  # 전일 대비 변동값
    change_rate = models.FloatField(null=True, blank=True)  # 전일 대비 변동률 (%)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["industry", "-base_date"]


class IndustryChart1d(IndustryChartBase):
    """산업 지수 일봉 (1개월 기준)"""

    class Meta:
        db_table = "industry_chart_1d"
        unique_together = [["industry", "base_date"]]
        ordering = ["industry", "-base_date"]
        indexes = [
            models.Index(fields=["industry", "-base_date"]),
        ]


class IndustryChart3d(IndustryChartBase):
    """산업 지수 3일봉 (3개월 기준)"""

    class Meta:
        db_table = "industry_chart_3d"
        unique_together = [["industry", "base_date"]]
        ordering = ["industry", "-base_date"]
        indexes = [
            models.Index(fields=["industry", "-base_date"]),
        ]


class IndustryChart1w(IndustryChartBase):
    """산업 지수 주봉 (6개월 기준)"""

    class Meta:
        db_table = "industry_chart_1w"
        unique_together = [["industry", "base_date"]]
        ordering = ["industry", "-base_date"]
        indexes = [
            models.Index(fields=["industry", "-base_date"]),
        ]


class IndustryChart2w(IndustryChartBase):
    """산업 지수 2주봉 (1년 기준)"""

    class Meta:
        db_table = "industry_chart_2w"
        unique_together = [["industry", "base_date"]]
        ordering = ["industry", "-base_date"]
        indexes = [
            models.Index(fields=["industry", "-base_date"]),
        ]


# ==================== KSIC - KIS 매핑 모델들 ====================
# 1. KIS 업종 지수 마스터 (idxcode.mst에서 추출)
class KisIndustry(models.Model):
    kis_code = models.CharField(max_length=4, primary_key=True)  # '0014' 등
    name = models.CharField(max_length=100)  # '전기전자' 등

    class Meta:
        db_table = "kis_industry"


# 2. DART 표준산업분류 마스터 (사용자님이 5->3자리로 가공한 코드)
class KsicCategory(models.Model):
    ksic_code = models.CharField(max_length=5, primary_key=True)  # '261' 등
    name = models.CharField(max_length=100, null=True, blank=True)

    # 이 DART 업종을 대표하는 KIS 지수와 직접 연결
    representative_kis = models.ForeignKey(
        "KisIndustry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ksic_categories",
    )

    class Meta:
        db_table = "ksic_category"


# # 3. [DEPRECATED] 마스터 파일 기반 종목-업종 매핑 모델
# # ⚠️ 이 모델은 더 이상 사용되지 않습니다.
# # sync_corp_codes.py에서 메모리 딕셔너리(ticker_to_kis)로 대체되었습니다.
# # 마이그레이션 이슈를 피하기 위해 모델 정의는 유지하지만, 새로운 코드에서는 사용하지 마세요.
# # TODO: 향후 마이그레이션을 통해 완전히 제거 예정
# class IndustryMapping(models.Model):
#     # MST 파일에서 추출한 6자리 종목코드 (Company 테이블과 독립적으로 먼저 저장 가능)
#     ticker = models.CharField(max_length=6, db_index=True)

#     # KIS 업종 코드와의 연결 (FK)
#     kis = models.ForeignKey(
#         KisIndustry, on_delete=models.CASCADE, related_name="mappings"
#     )

#     # 향후 Company 모델이 채워졌을 때 조인을 쉽게 하기 위한 선택적 필드
#     # company = models.ForeignKey('company.Company', on_delete=models.SET_NULL, null=True, to_field='ticker')

#     weight = models.FloatField(default=1.0)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         db_table = "industry_mapping"
#         # 동일 티커가 동일 KIS 업종에 중복 매핑되는 것 방지
#         unique_together = ("ticker", "kis")
