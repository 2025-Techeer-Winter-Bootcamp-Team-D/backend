"""
보고서 처리 Celery 태스크
보고서 본문 추출, 정제, 정보 추출, 임베딩 생성을 수행합니다.
"""

import logging
from typing import Any

from celery import chain, shared_task
from django.utils import timezone

from companies.models import Report, RevenueComposition
from companies.services.report_extractor import ReportExtractorService
from companies.services.report_info_extractor import ReportInfoExtractorService
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.embedding import EmbeddingService
from news.services.refiner import RefineService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def extract_report_content_task(self, report_id: int) -> dict[str, Any] | None:
    """보고서 본문 추출 (OpenDartReader 사용)"""
    try:
        report = Report.objects.select_related("company").get(id=report_id)
        report.processing_status = "processing"
        report.save(update_fields=["processing_status"])

        extractor = ReportExtractorService()
        # rcept_no (접수번호)를 사용하여 DART에서 직접 본문 추출
        raw_content = extractor.extract_content(report.rcept_no)

        if not raw_content:
            logger.warning(
                f"보고서 본문 추출 실패: {report_id} (rcept_no: {report.rcept_no})"
            )
            report.processing_status = "failed"
            report.save(update_fields=["processing_status"])
            return None

        report.raw_content = raw_content
        report.save(update_fields=["raw_content"])

        return {
            "report_id": report_id,
            "rcept_no": report.rcept_no,
            "raw_content": raw_content,
            "company_stock_code": report.company.stock_code,
            "company_name": report.company.company_name,
            "report_name": report.report_name,
            "report_type": report.report_type,
            "submitted_at": str(report.submitted_at),
        }
    except Report.DoesNotExist:
        logger.error(f"Report not found: {report_id}")
        return None
    except Exception as e:
        logger.error(f"보고서 본문 추출 오류: {report_id} - {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def refine_report_content_task(self, data: dict[str, Any]) -> dict[str, Any] | None:
    """보고서 본문 정제"""
    if not data:
        return None

    report_id = data.get("report_id")
    try:
        raw_content = data["raw_content"]

        refiner = RefineService()
        refined_content = refiner.get_refined_body(raw_content)

        if not refined_content or len(refined_content.strip()) < 100:
            logger.warning(f"보고서 정제 결과가 너무 짧음: {report_id}")
            Report.objects.filter(id=report_id).update(processing_status="failed")
            # 정제 결과가 너무 짧은 경우는 재시도해도 의미 없으므로 None 반환
            return None

        # DB 업데이트
        Report.objects.filter(id=report_id).update(refined_content=refined_content)

        data["refined_content"] = refined_content
        return data
    except Exception as e:
        logger.error(f"보고서 정제 오류: {report_id} - {e}")
        # Celery retry 호출 (지수 백오프)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def extract_report_info_task(self, data: dict[str, Any]) -> dict[str, Any] | None:
    """통합 정보 추출 (요약 + 매출 구성)"""
    if not data:
        return None

    try:
        report_id = data["report_id"]
        refined_content = data["refined_content"]
        company_name = data["company_name"]
        company_stock_code = data["company_stock_code"]
        report_name = data["report_name"]
        submitted_at = data.get("submitted_at", "")

        # 1회 호출로 요약 + 매출 구성 통합 추출
        extractor = ReportInfoExtractorService()
        extracted_info = extractor.extract_info(
            refined_content, report_name, company_name
        )

        # DB 업데이트 (extracted_info JSON으로 저장)
        Report.objects.filter(id=report_id).update(extracted_info=extracted_info)

        # 매출 구성이 있으면 별도 테이블에도 저장
        revenue_composition = extracted_info.get("revenue_composition", [])
        if revenue_composition:
            # fiscal_year 추출: submitted_at을 여러 형식으로 파싱 시도
            fiscal_year = None
            if submitted_at:
                try:
                    # ISO/datetime 형식 파싱 시도
                    from datetime import datetime
                    from dateutil import parser as date_parser
                    parsed_date = date_parser.parse(submitted_at)
                    fiscal_year = parsed_date.year
                except (ValueError, TypeError, AttributeError):
                    try:
                        # 순수 숫자 4자리 연도 시도
                        if len(submitted_at) >= 4 and submitted_at[:4].isdigit():
                            fiscal_year = int(submitted_at[:4])
                    except (ValueError, TypeError):
                        pass
            
            if fiscal_year is None:
                fiscal_year = timezone.now().year
                logger.warning(
                    f"submitted_at 파싱 실패, 현재 연도 사용: report_id={report_id}, "
                    f"company={company_stock_code}, submitted_at={submitted_at}"
                )
            
            saved_count = 0
            for segment in revenue_composition:
                # 필수 키 검증: segment 필드가 있고 비어있지 않은지 확인
                segment_name = segment.get("segment") if isinstance(segment, dict) else None
                if not segment_name or not str(segment_name).strip():
                    logger.warning(
                        f"매출 구성 항목 건너뜀 (segment 누락/비어있음): report_id={report_id}, "
                        f"company={company_stock_code}, segment_data={segment}"
                    )
                    continue
                
                # revenue를 int/Decimal로 안전하게 변환
                try:
                    revenue_value = segment.get("revenue", 0)
                    if revenue_value is None:
                        revenue_value = 0
                    revenue_value = int(revenue_value)
                except (ValueError, TypeError):
                    logger.warning(
                        f"매출 구성 항목 revenue 변환 실패, 기본값 0 사용: report_id={report_id}, "
                        f"company={company_stock_code}, revenue={segment.get('revenue')}"
                    )
                    revenue_value = 0
                
                # ratio가 숫자 또는 None인지 검증
                ratio_value = segment.get("ratio")
                if ratio_value is not None:
                    try:
                        # 문자열 "58.1%" 형태 처리
                        if isinstance(ratio_value, str):
                            ratio_value = ratio_value.replace("%", "").strip()
                        ratio_value = float(ratio_value)
                    except (ValueError, TypeError):
                        logger.warning(
                            f"매출 구성 항목 ratio 변환 실패, None 사용: report_id={report_id}, "
                            f"company={company_stock_code}, ratio={segment.get('ratio')}"
                        )
                        ratio_value = None
                
                RevenueComposition.objects.update_or_create(
                    company_id=company_stock_code,
                    fiscal_year=fiscal_year,
                    segment_name=str(segment_name).strip(),
                    defaults={
                        "revenue": revenue_value,
                        "ratio": ratio_value,
                    },
                )
                saved_count += 1
            
            logger.info(
                f"매출 구성 저장 완료: {report_id} - {saved_count}개 부문 저장 "
                f"(총 {len(revenue_composition)}개 중)"
            )

        data["extracted_info"] = extracted_info
        return data
    except Exception as e:
        logger.error(f"정보 추출 오류: {data.get('report_id')} - {e}")
        raise


@shared_task(bind=True, max_retries=3)
def create_report_embedding_task(self, data: dict[str, Any]) -> dict[str, Any] | None:
    """보고서 임베딩 생성"""
    if not data:
        return None

    try:
        report_id = data["report_id"]
        refined_content = data["refined_content"]

        embedding_service = EmbeddingService()
        embedding = embedding_service.create_embedding(refined_content)

        if not embedding:
            logger.warning(f"임베딩 생성 실패: {report_id}")
            return data

        # DB 업데이트
        Report.objects.filter(id=report_id).update(embedding=embedding)

        data["embedding"] = embedding
        return data
    except Exception as e:
        logger.error(f"임베딩 생성 오류: {data.get('report_id')} - {e}")
        return data  # 임베딩 실패해도 다른 작업은 완료됨


@shared_task
def save_report_to_opensearch_task(data: dict[str, Any]) -> bool:
    """OpenSearch에 보고서 저장"""
    if not data or not data.get("embedding"):
        return False

    report_id = data.get("report_id")
    try:
        # extracted_info에서 요약 추출
        extracted_info = data.get("extracted_info", {})
        summary = extracted_info.get("summary", {}).get("one_line", "")

        opensearch = ReportOpenSearchService()
        success = opensearch.save_report_vector(
            report_id=report_id,
            company_stock_code=data["company_stock_code"],
            company_name=data["company_name"],
            report_name=data["report_name"],
            report_type=data["report_type"],
            content=data.get("refined_content", "")[:10000],  # 본문 일부만
            summary=summary,
            content_vector=data["embedding"],
            submitted_at=data.get("submitted_at"),
        )

        if success:
            Report.objects.filter(id=report_id).update(
                processing_status="completed",
                processed_at=timezone.now(),
            )
            logger.info(f"OpenSearch 저장 성공: {report_id}")
        else:
            # save_report_vector가 False를 반환한 경우 실패 상태로 업데이트
            Report.objects.filter(id=report_id).update(
                processing_status="failed",
                processed_at=timezone.now(),
            )
            logger.error(f"OpenSearch 저장 실패: report_id={report_id}")

        return success
    except Exception as e:
        logger.error(f"OpenSearch 저장 오류: report_id={report_id} - {e}")
        # 예외 발생 시 실패 상태로 업데이트
        if report_id:
            Report.objects.filter(id=report_id).update(
                processing_status="failed",
                processed_at=timezone.now(),
            )
        return False


@shared_task
def process_single_report_pipeline(report_id: int):
    """단일 보고서 처리 파이프라인"""
    workflow = chain(
        extract_report_content_task.s(report_id),
        refine_report_content_task.s(),
        extract_report_info_task.s(),  # 통합: 요약 + 매출구성 1회 호출
        create_report_embedding_task.s(),
        save_report_to_opensearch_task.s(),
    )

    return workflow.apply_async()


@shared_task
def process_company_reports(stock_code: str, limit: int = 20):
    """기업의 미처리 보고서 일괄 처리"""
    reports = Report.objects.filter(
        company_id=stock_code,
        processing_status="pending",
    ).order_by("-submitted_at")[:limit]

    count = reports.count()
    logger.info(f"보고서 처리 시작: {stock_code} - {count}건")

    for report in reports:
        process_single_report_pipeline.delay(report.id)

    return count
