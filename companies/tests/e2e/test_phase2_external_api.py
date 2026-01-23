# companies/tests/e2e/test_phase2_external_api.py

"""
Phase 2: 외부 API 검증 테스트
- DART API
- Gemini API
"""

import time
import logging
import requests
from typing import Dict, Any
from config.settings import DART_API_KEY, GEMINI_API_KEY
import google.generativeai as genai

logger = logging.getLogger(__name__)


class Phase2ExternalAPITest:
    """Phase 2: 외부 API 검증 테스트"""

    @staticmethod
    def run(skip_gemini: bool = False) -> Dict[str, Any]:
        """Phase 2 전체 테스트 실행"""
        start_time = time.time()
        results = {
            "status": "success",
            "duration": 0,
            "checks": {},
            "tokens_used": 0
        }

        try:
            # DART API 검증
            results["checks"]["dart_api"] = Phase2ExternalAPITest._check_dart_api()

            # Gemini API 검증 (skip_gemini=True면 스킵)
            if not skip_gemini:
                gemini_result = Phase2ExternalAPITest._check_gemini_api()
                results["checks"]["gemini_api"] = gemini_result
                results["tokens_used"] = gemini_result.get("tokens", 0)
            else:
                results["checks"]["gemini_api"] = {
                    "status": "skipped",
                    "duration": 0,
                    "message": "Gemini API 테스트 스킵"
                }

        except Exception as e:
            logger.error(f"Phase 2 실행 중 오류 발생: {str(e)}")
            results["status"] = "error"
            results["error"] = str(e)

        results["duration"] = round(time.time() - start_time, 2)
        return results

    @staticmethod
    def _check_dart_api() -> Dict[str, Any]:
        """DART API 연결 확인"""
        start_time = time.time()
        try:
            if not DART_API_KEY:
                return {
                    "status": "error",
                    "duration": 0,
                    "error": "DART_API_KEY가 설정되지 않았습니다"
                }

            # DART OpenAPI - 기업 정보 조회 (삼성전자)
            url = "https://opendart.fss.or.kr/api/company.json"
            params = {
                "crtfc_key": DART_API_KEY,
                "corp_code": "00126380"  # 삼성전자 고유번호
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # 응답 형식 검증
            if data.get("status") == "000":  # 정상
                return {
                    "status": "ok",
                    "duration": round(time.time() - start_time, 2),
                    "company_name": data.get("corp_name")
                }
            else:
                return {
                    "status": "error",
                    "duration": round(time.time() - start_time, 2),
                    "error": f"DART API 오류: {data.get('message')}"
                }

        except requests.exceptions.Timeout:
            logger.error("DART API 연결 타임아웃")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": "Connection timeout"
            }
        except Exception as e:
            logger.error(f"DART API 연결 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e)
            }

    @staticmethod
    def _check_gemini_api() -> Dict[str, Any]:
        """Gemini API 연결 확인 (최소 토큰 사용)"""
        start_time = time.time()
        try:
            if not GEMINI_API_KEY:
                return {
                    "status": "error",
                    "duration": 0,
                    "error": "GEMINI_API_KEY가 설정되지 않았습니다",
                    "tokens": 0
                }

            # Gemini API 설정
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")

            # 최소 토큰 테스트 (입력: "Hi", 예상 출력: ~5 tokens)
            response = model.generate_content(
                "Hi",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=10,
                    temperature=0.0,
                )
            )

            # 토큰 사용량 계산
            # Gemini Flash: 입력 ~2 tokens + 출력 ~5 tokens = ~7 tokens
            input_tokens = 2  # "Hi" 입력 토큰 추정
            output_tokens = len(response.text.split())  # 출력 단어 수로 추정
            total_tokens = input_tokens + output_tokens

            return {
                "status": "ok",
                "duration": round(time.time() - start_time, 2),
                "tokens": total_tokens,
                "response": response.text[:50]  # 응답 일부만 반환
            }

        except Exception as e:
            logger.error(f"Gemini API 연결 실패: {str(e)}")
            return {
                "status": "error",
                "duration": round(time.time() - start_time, 2),
                "error": str(e),
                "tokens": 0
            }
