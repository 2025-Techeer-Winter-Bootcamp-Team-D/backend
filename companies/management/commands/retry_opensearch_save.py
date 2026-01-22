"""
보고서 OpenSearch 저장 재시도 Management Command

이미 처리된 보고서의 OpenSearch 저장만 재시도합니다.
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
from companies.tasks.report_processing import save_report_to_opensearch_task
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "이미 처리된 보고서의 OpenSearch 저장만 재시도합니다. "
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
            ).filter(
                embedding__isnull=False
            )  # 임베딩이 있어야 함
        else:
            # 처리 완료되었고 임베딩이 있는 모든 보고서
            queryset = queryset.filter(
                processing_status="completed", embedding__isnull=False
            )

        if stock_code:
            queryset = queryset.filter(company__stock_code=stock_code)

        # 필수 데이터가 있는 보고서만 필터링
        queryset = queryset.filter(
            embedding__isnull=False,
            extracted_info__isnull=False,
            refined_content__isnull=False,
        ).exclude(embedding="", refined_content="")

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

        # 재시도 실행
        success_count = 0
        fail_count = 0

        for report in queryset:
            try:
                # save_report_to_opensearch_task에 필요한 데이터 구성
                extracted_info = report.extracted_info or {}
                summary = extracted_info.get("summary", {}).get("one_line", "")

                data = {
                    "report_id": report.id,
                    "rcept_no": report.rcept_no,
                    "company_stock_code": report.company.stock_code,
                    "company_name": report.company.company_name,
                    "report_name": report.report_name,
                    "report_type": report.report_type,
                    "refined_content": report.refined_content or "",
                    "extracted_info": extracted_info,
                    "embedding": report.embedding,
                    "submitted_at": (
                        str(report.submitted_at) if report.submitted_at else None
                    ),
                }

                # 동기적으로 실행 (테스트용)
                # 또는 비동기로 실행하려면: save_report_to_opensearch_task.delay(data)
                result = save_report_to_opensearch_task(data)

                if result:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ 성공: ID {report.id} - {report.company.company_name} "
                            f"({report.report_name})"
                        )
                    )
                else:
                    fail_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ 실패: ID {report.id} - {report.company.company_name} "
                            f"({report.report_name})"
                        )
                    )

            except Exception as e:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f"✗ 오류: ID {report.id} - {e}"))
                logger.error(
                    f"OpenSearch 저장 재시도 오류: report_id={report.id} - {e}",
                    exc_info=True,
                )

        # 결과 요약
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"재시도 완료: 성공 {success_count}개, 실패 {fail_count}개"
            )
        )
