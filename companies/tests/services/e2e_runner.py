# companies/tests/services/e2e_runner.py

"""
E2E 테스트 통합 실행 서비스
모든 Phase를 실행하고 결과를 취합합니다.
"""

import time
import logging
from typing import Dict, Any, List
from companies.tests.e2e.test_phase1_infrastructure import Phase1InfrastructureTest
from companies.tests.e2e.test_phase2_external_api import Phase2ExternalAPITest
from companies.tests.e2e.test_phase3_data_integrity import Phase3DataIntegrityTest
from companies.tests.e2e.test_phase4_report_pipeline import Phase4ReportPipelineTest

logger = logging.getLogger(__name__)


class E2ETestRunner:
    """E2E 테스트 통합 실행 서비스"""

    # Gemini 토큰 비용 (Gemini Flash 1.5 기준)
    GEMINI_FLASH_INPUT_COST_PER_1M = 0.075  # $0.075 per 1M tokens
    GEMINI_FLASH_OUTPUT_COST_PER_1M = 0.30  # $0.30 per 1M tokens

    @staticmethod
    def run(phases: List[int] = None, skip_gemini: bool = False) -> Dict[str, Any]:
        """
        E2E 테스트 실행

        Args:
            phases: 실행할 Phase 리스트 (예: [1, 2, 3, 4]). None이면 전체 실행
            skip_gemini: Gemini API 사용 스킵 여부

        Returns:
            테스트 결과 딕셔너리
        """
        start_time = time.time()
        results = {
            "status": "success",
            "total_duration": 0,
            "gemini_tokens_used": 0,
            "estimated_cost": 0.0,
            "phases": {}
        }

        # 기본값: 전체 Phase 실행
        if phases is None:
            phases = [1, 2, 3, 4]

        try:
            # Phase 1: 인프라 검증
            if 1 in phases:
                logger.info("Phase 1 실행 시작: 인프라 검증")
                results["phases"]["phase1_infrastructure"] = Phase1InfrastructureTest.run()

            # Phase 2: 외부 API 검증
            if 2 in phases:
                logger.info("Phase 2 실행 시작: 외부 API 검증")
                phase2_result = Phase2ExternalAPITest.run(skip_gemini=skip_gemini)
                results["phases"]["phase2_external_api"] = phase2_result
                results["gemini_tokens_used"] += phase2_result.get("tokens_used", 0)

            # Phase 3: 데이터 정합성 검증
            if 3 in phases:
                logger.info("Phase 3 실행 시작: 데이터 정합성 검증")
                results["phases"]["phase3_data_integrity"] = Phase3DataIntegrityTest.run()

            # Phase 4: 보고서 처리 파이프라인 검증
            if 4 in phases:
                logger.info("Phase 4 실행 시작: 보고서 처리 파이프라인 검증")
                phase4_result = Phase4ReportPipelineTest.run(skip_gemini=skip_gemini)
                results["phases"]["phase4_report_pipeline"] = phase4_result
                results["gemini_tokens_used"] += phase4_result.get("tokens_used", 0)

            # 전체 실행 시간 계산
            results["total_duration"] = round(time.time() - start_time, 2)

            # Gemini 비용 추정 (입력/출력 토큰 분리 가정)
            # 입력 토큰: 전체의 80% 가정
            # 출력 토큰: 전체의 20% 가정
            total_tokens = results["gemini_tokens_used"]
            input_tokens = total_tokens * 0.8
            output_tokens = total_tokens * 0.2

            input_cost = (input_tokens / 1_000_000) * E2ETestRunner.GEMINI_FLASH_INPUT_COST_PER_1M
            output_cost = (output_tokens / 1_000_000) * E2ETestRunner.GEMINI_FLASH_OUTPUT_COST_PER_1M
            results["estimated_cost"] = round(input_cost + output_cost, 5)

            # 전체 상태 판정
            all_success = all(
                phase_result.get("status") in ["success", "ok", "skipped"]
                for phase_result in results["phases"].values()
            )
            results["status"] = "success" if all_success else "error"

        except Exception as e:
            logger.error(f"E2E 테스트 실행 중 오류 발생: {str(e)}")
            results["status"] = "error"
            results["error"] = str(e)
            results["total_duration"] = round(time.time() - start_time, 2)

        return results

    @staticmethod
    def format_results(results: Dict[str, Any]) -> str:
        """
        테스트 결과를 보기 좋게 포맷팅

        Args:
            results: 테스트 결과 딕셔너리

        Returns:
            포맷팅된 결과 문자열
        """
        output = []
        output.append("=" * 80)
        output.append("E2E 테스트 결과")
        output.append("=" * 80)
        output.append(f"전체 상태: {results.get('status', 'unknown').upper()}")
        output.append(f"전체 실행 시간: {results.get('total_duration', 0)}초")
        output.append(f"Gemini 토큰 사용량: {results.get('gemini_tokens_used', 0)} tokens")
        output.append(f"예상 비용: ${results.get('estimated_cost', 0)}")
        output.append("")

        # Phase별 결과
        phases = results.get("phases", {})
        for phase_name, phase_result in phases.items():
            output.append("-" * 80)
            output.append(f"{phase_name.upper()}")
            output.append("-" * 80)
            output.append(f"  상태: {phase_result.get('status', 'unknown')}")
            output.append(f"  실행 시간: {phase_result.get('duration', 0)}초")

            # 체크 결과
            checks = phase_result.get("checks", {})
            if checks:
                output.append("  검증 항목:")
                for check_name, check_result in checks.items():
                    check_status = check_result.get("status", "unknown")
                    output.append(f"    - {check_name}: {check_status}")

            output.append("")

        output.append("=" * 80)
        return "\n".join(output)
