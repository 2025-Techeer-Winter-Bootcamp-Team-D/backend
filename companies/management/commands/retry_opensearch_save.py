"""
보고서 Embedding 재생성 및 OpenSearch 저장 Management Command

DB의 refined_content와 extracted_info를 이용해서 embedding부터 다시 생성하고 OpenSearch에 저장합니다.
크롤링이나 정보 추출은 다시 하지 않습니다.

사용법:
    # 특정 보고서 ID 재시도
    python manage.py retry_opensearch_save --report-id 276

    # 여러 보고서 ID 재시도
    python manage.py retry_opensearch_save --report-id 276 277 278

    # 처리 완료되었지만 OpenSearch 저장 실패한 보고서 모두 재시도
    python manage.py retry_opensearch_save --failed-only

    # 특정 기업의 보고서만 재시도
    python manage.py retry_opensearch_save --stock-code 005930 --failed-only
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from companies.models import Report
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.embedding import EmbeddingService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "DB의 refined_content와 extracted_info를 이용해서 embedding부터 다시 생성하고 OpenSearch에 저장합니다. "
        "크롤링이나 정보 추출은 다시 하지 않습니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--report-id",
            type=int,
            nargs="+",
            help="재시도할 보고서 ID (여러 개 지정 가능)",
        )
        parser.add_argument(
            "--failed-only",
            action="store_true",
            help="처리 완료되었지만 OpenSearch 저장 실패한 보고서만 재시도",
        )
        parser.add_argument(
            "--stock-code",
            type=str,
            help="특정 기업의 보고서만 재시도 (종목코드)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제로 재시도하지 않고 대상 보고서만 출력",
        )

    def handle(self, *args, **options):
        report_ids = options.get("report_id")
        failed_only = options.get("failed_only", False)
        stock_code = options.get("stock_code")
        dry_run = options.get("dry_run", False)

        # 쿼리셋 구성
        queryset = Report.objects.select_related("company").all()

        if report_ids:
            # 특정 보고서 ID로 필터링
            queryset = queryset.filter(id__in=report_ids)
        elif failed_only:
            # 처리 완료되었지만 OpenSearch 저장 실패한 보고서
            # (processing_status가 "completed"이지만 OpenSearch에 저장되지 않은 경우)
            # 또는 processing_status가 "failed"인 경우
            queryset = queryset.filter(
                Q(processing_status="completed") | Q(processing_status="failed")
            )
        else:
            # 처리 완료된 모든 보고서
            queryset = queryset.filter(processing_status="completed")

        if stock_code:
            queryset = queryset.filter(company__stock_code=stock_code)

        # 필수 데이터가 있는 보고서만 필터링 (embedding은 없어도 됨)
        queryset = queryset.filter(
            extracted_info__isnull=False,
            refined_content__isnull=False,
        ).exclude(refined_content="")

        count = queryset.count()
        self.stdout.write(f"대상 보고서 수: {count}개")

        if count == 0:
            self.stdout.write(self.style.WARNING("재시도할 보고서가 없습니다."))
            return

        if dry_run:
            self.stdout.write("\n[DRY-RUN] 재시도 대상 보고서:")
            for report in queryset[:10]:  # 최대 10개만 출력
                self.stdout.write(
                    f"  - ID: {report.id}, "
                    f"기업: {report.company.company_name} ({report.company.stock_code}), "
                    f"보고서: {report.report_name}, "
                    f"상태: {report.processing_status}"
                )
            if count > 10:
                self.stdout.write(f"  ... 외 {count - 10}개")
            return

        # Embedding 서비스 및 OpenSearch 서비스 초기화
        embedding_service = EmbeddingService()
        opensearch_service = ReportOpenSearchService()

        # 재시도 실행
        success_count = 0
        fail_count = 0

        for report in queryset:
            try:
                # refined_content 유효성 검증
                if (
                    not report.refined_content
                    or len(report.refined_content.strip()) < 10
                ):
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠ 건너뜀: ID {report.id} - refined_content가 너무 짧거나 없음"
                        )
                    )
                    continue

                extracted_info = report.extracted_info or {}
                summary = extracted_info.get("summary", {}).get("one_line", "")

                # Embedding 생성 (기존 embedding이 없거나 재생성하는 경우)
                # 보고서는 key_info + summary를 우선 사용, 없으면 refined_content 사용
                key_info = extracted_info.get("key_info", {})
                key_info_text = ""
                if isinstance(key_info, dict):
                    key_info_items = []
                    for key, value in key_info.items():
                        key_info_items.append(f"{key}: {value}")
                    key_info_text = "\n".join(key_info_items)

                # 임베딩할 텍스트 구성: key_info + summary
                embedding_text = f"{key_info_text}\n\n요약: {summary}".strip()

                # 텍스트가 너무 짧으면 전체 본문 사용 (fallback)
                if len(embedding_text) < 50:
                    logger.debug(
                        f"임베딩 텍스트가 너무 짧음, 전체 본문 사용: {report.id}"
                    )
                    embedding_text = report.refined_content[:10000]  # 최대 10,000자

                if not embedding_text:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠ 건너뜀: ID {report.id} - 임베딩할 텍스트가 없음"
                        )
                    )
                    continue

                # Embedding 생성
                self.stdout.write(
                    f"임베딩 생성 중: ID {report.id} - {report.company.company_name} "
                    f"({report.report_name[:50]})..."
                )
                embedding = embedding_service.create_embedding(embedding_text)

                if not embedding:
                    fail_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ 임베딩 생성 실패: ID {report.id} - {report.company.company_name} "
                            f"({report.report_name[:50]})"
                        )
                    )
                    logger.error(
                        f"임베딩 생성 실패: report_id={report.id}, report_name={report.report_name[:50]}"
                    )
                    continue

                # OpenSearch에 저장
                success = opensearch_service.save_report_vector(
                    report_id=report.id,
                    company_stock_code=report.company.stock_code,
                    company_name=report.company.company_name,
                    report_name=report.report_name,
                    report_type=report.report_type,
                    content=report.refined_content[:10000],  # 본문 일부만
                    summary=summary,
                    content_vector=embedding,
                    submitted_at=report.submitted_at,
                )

                if success:
                    # DB에 embedding 저장 (선택적)
                    Report.objects.filter(id=report.id).update(embedding=embedding)
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ 성공: ID {report.id} - {report.company.company_name} "
                            f"({report.report_name[:50]})"
                        )
                    )
                else:
                    fail_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ OpenSearch 저장 실패: ID {report.id} - {report.company.company_name} "
                            f"({report.report_name[:50]})"
                        )
                    )
                    logger.error(
                        f"OpenSearch 저장 실패: report_id={report.id}, report_name={report.report_name[:50]}"
                    )

            except Exception as e:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f"✗ 오류: ID {report.id} - {e}"))
                logger.error(
                    f"보고서 embedding 재시도 오류: report_id={report.id} - {e}",
                    exc_info=True,
                )

        # 결과 요약
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"재시도 완료: 성공 {success_count}개, 실패 {fail_count}개"
            )
        )
