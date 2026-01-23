# companies/tests/e2e/test_phase4_report_pipeline.py

"""
Phase 4: 보고서 처리 파이프라인 검증 테스트
- 가장 짧은 보고서 선택
- 보고서 처리 파이프라인 실행
- 결과 검증
"""

import time
import logging
from typing import Dict, Any, Optional
from django.db.models import Length
from companies.models import Report
from companies.tasks.report_processing import process_single_report_pipeline
from celery.result import AsyncResult

logger = logging.getLogger(__name__)


class Phase4ReportPipelineTest:
    """Phase 4: 보고서 처리 파이프라인 검증 테스트"""

    @staticmethod
    def run(skip_gemini: bool = False, timeout: int = 60) -> Dict[str, Any]:
        """Phase 4 전체 테스트 실행"""
        start_time = time.time()
        results = {
            "status": "success",
            "duration": 0,
            "report_id": None,
            "checks": {},
            "tokens_used": 0
        }

        if skip_gemini:
            results["status"] = "skipped"
            results["message"] = "Gemini API 사용이 비활성화되어 Phase 4를 스킵합니다"
            return results

        try:
            # 1. 가장 짧은 보고서 선택
            report = Phase4ReportPipelineTest._select_shortest_report()
            if not report:
                results["status"] = "error"
                results["error"] = "처리할 보고서가 없습니다"
                return results

            results["report_id"] = report.rcept_no
            results["checks"]["report_selection"] = {
                "status": "ok",
                "rcept_no": report.rcept_no,
                "report_name": report.report_name,
                "content_length": len(report.raw_content or report.refined_content or "")
            }

            # 2. 보고서 처리 파이프라인 실행
            pipeline_result = Phase4ReportPipelineTest._run_pipeline(
                report, timeout=timeout
            )
            results["checks"]["pipeline"] = pipeline_result

            # Gemini 토큰 사용량 추정
            if pipeline_result.get("status") == "ok":
                # 입력 토큰: 보고서 길이 / 4 (평균 4자 = 1 토큰)
                # 출력 토큰: 평균 150 토큰
                content_length = len(report.raw_content or report.refined_content or "")
                input_tokens = content_length // 4
                output_tokens = 150
                results["tokens_used"] = input_tokens + output_tokens

        except Exception as e:
            logger.error(f"Phase 4 실행 중 오류 발생: {str(e)}")
            results["status"] = "error"
            results["error"] = str(e)

        results["duration"] = round(time.time() - start_time, 2)
        return results

    @staticmethod
    def _select_shortest_report() -> Optional[Report]:
        """가장 짧은 보고서 선택 (처리되지 않은 것 중)"""
        try:
            # raw_content 또는 refined_content가 있는 보고서 중 가장 짧은 것
            report = Report.objects.filter(
                processing_status__in=["pending", "failed"]
            ).exclude(
                raw_content__isnull=True,
                refined_content__isnull=True
            ).annotate(
                content_length=Length("raw_content") + Length("refined_content")
            ).order_by("content_length").first()

            # 처리되지 않은 보고서가 없으면 아무거나 선택
            if not report:
                report = Report.objects.exclude(
                    raw_content__isnull=True,
                    refined_content__isnull=True
                ).annotate(
                    content_length=Length("raw_content") + Length("refined_content")
                ).order_by("content_length").first()

            return report

        except Exception as e:
            logger.error(f"보고서 선택 실패: {str(e)}")
            return None

    @staticmethod
    def _run_pipeline(report: Report, timeout: int = 60) -> Dict[str, Any]:
        """보고서 처리 파이프라인 실행"""
        start_time = time.time()
        checks = {}

        try:
            # Celery 작업 트리거
            logger.info(f"보고서 처리 시작: {report.rcept_no}")
            task_result = process_single_report_pipeline.delay(report.rcept_no)

            # 작업 완료 대기 (timeout 설정)
            try:
                result = task_result.get(timeout=timeout)
                checks["task_execution"] = {
                    "status": "ok",
                    "result": result
                }
            except Exception as e:
                logger.error(f"파이프라인 실행 타임아웃 또는 오류: {str(e)}")
                checks["task_execution"] = {
                    "status": "error",
                    "error": str(e)
                }
                return {
                    "status": "error",
                    "duration": round(time.time() - start_time, 2),
                    "checks": checks,
                    "error": f"Pipeline execution failed: {str(e)}"
                }

            # 3. 결과 검증
            report.refresh_from_db()

            # 처리 상태 검증
            checks["processing_status"] = {
                "status": "ok" if report.processing_status == "completed" else "error",
                "processing_status": report.processing_status
            }

            # 추출된 정보 검증
            checks["extracted_info"] = {
                "status": "ok" if report.extracted_info else "error",
                "has_data": bool(report.extracted_info)
            }

            # 임베딩 검증
            checks["embedding"] = {
                "status": "ok" if report.embedding else "warning",
                "has_embedding": bool(report.embedding)
            }

            # OpenSearch 인덱싱 검증 (간접 확인)
            checks["opensearch"] = {
                "status": "ok" if report.primary_keyword else "warning",
                "has_keyword": bool(report.primary_keyword)
            }

            return {
                "status": "ok" if report.processing_status == "completed" else "error",
                "duration": round(time.time() - start_time, 2),
                "checks": checks
            }

        except Exception as e:
            logger.error(f"파이프라인 실행 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "checks": checks,
                "error": str(e)
            }
