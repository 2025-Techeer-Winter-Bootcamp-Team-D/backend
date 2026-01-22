"""
기업 전망 분석 서비스

OpenSearch에 저장된 특정 기업의 뉴스, 보고서를 분석하여
퀀트 투자자가 의사결정을 할 수 있는 전망을 제공합니다.
"""

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from google import genai
from google.genai.types import GenerateContentConfig

from companies.models import Company, Report
from news.services.opensearch import OpenSearchService
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class CompanyOutlookService:
    """
    기업 전망 분석 서비스

    - OpenSearch에서 뉴스/보고서 검색
    - Gemini LLM으로 분석 생성
    - Redis 캐싱 (TTL: 1시간)
    """

    CACHE_KEY_PREFIX = "outlook"
    CACHE_VERSION = "v1"
    CACHE_TTL = 3600  # 1시간

    def __init__(self):
        """Gemini 클라이언트 초기화"""
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            error_msg = "GEMINI_API_KEY is missing or empty."
            logger.error(error_msg)
            raise ValueError(error_msg)

        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"
        logger.debug(f"CompanyOutlookService 초기화: {self.model_name}")

    def _get_cache_key(self, stock_code: str) -> str:
        """캐시 키 생성"""
        return f"{self.CACHE_KEY_PREFIX}:{stock_code}:{self.CACHE_VERSION}"

    def analyze_outlook(
        self,
        company: Company,
        days_back: int = 30,
        max_news: int = 10,
        max_reports: int = 5,
    ) -> dict:
        """
        기업 전망 분석

        Args:
            company: Company 모델 인스턴스
            days_back: 뉴스/보고서 검색 기간 (일)
            max_news: 최대 뉴스 수
            max_reports: 최대 보고서 수

        Returns:
            분석 결과 dict
        """
        stock_code = company.stock_code

        # 1. 캐시 확인
        cache_key = self._get_cache_key(stock_code)
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"캐시 히트: {cache_key}")
            return cached_result

        # 2. 데이터 검색
        search_data = self._search_company_data(
            company, days_back, max_news, max_reports
        )

        # 3. LLM 분석 생성
        analysis_result = self._generate_analysis(company, search_data)

        # 4. 결과 구성
        result = {
            "stock_code": stock_code,
            "company_name": company.company_name,
            "analyzed_at": timezone.now().isoformat(),
            "analysis": analysis_result.get("analysis", "분석 데이터가 부족합니다."),
            "positive_factor": analysis_result.get("positive_factor", "긍정 요인 정보 없음"),
            "risk_factor": analysis_result.get("risk_factor", "리스크 요인 정보 없음"),
            "opinion": analysis_result.get("opinion", "투자 의견 정보 없음"),
            "data_sources": {
                "news_count": len(search_data.get("news", [])),
                "report_count": len(search_data.get("reports", [])),
            },
        }

        # 5. 캐싱
        cache.set(cache_key, result, self.CACHE_TTL)
        logger.info(f"캐시 저장: {cache_key}, TTL={self.CACHE_TTL}s")

        return result

    def _search_company_data(
        self,
        company: Company,
        days_back: int,
        max_news: int,
        max_reports: int,
    ) -> dict:
        """
        OpenSearch에서 기업 관련 뉴스/보고서 검색

        Args:
            company: Company 모델 인스턴스
            days_back: 검색 기간 (일)
            max_news: 최대 뉴스 수
            max_reports: 최대 보고서 수

        Returns:
            {"news": [...], "reports": [...]}
        """
        published_after = timezone.now() - timedelta(days=days_back)
        news_list = []
        reports_list = []

        # 뉴스 검색
        try:
            opensearch_service = OpenSearchService()
            clean_name = company.company_name.replace("(주)", "").replace("주식회사", "").strip()
            news_results = opensearch_service.search_news_by_keyword(
                keyword=clean_name,
                size=max_news,
                published_after=published_after,
            )
            news_list = news_results
            logger.info(f"뉴스 검색 완료: {company.company_name}, {len(news_list)}건")
        except Exception as e:
            logger.warning(f"뉴스 검색 실패: {e}")

        # 보고서 검색 (벡터 검색)
        try:
            # 기업명으로 임베딩 생성
            embedding_service = EmbeddingService()
            query_vector = embedding_service.create_embedding(
                f"{company.company_name} 투자 전망 실적 분석"
            )

            if query_vector:
                report_service = ReportOpenSearchService()
                reports_results = report_service.search_similar_reports(
                    query_vector=query_vector,
                    size=max_reports,
                    company_stock_code=company.stock_code,
                )
                reports_list = reports_results
                logger.info(
                    f"보고서 검색 완료: {company.stock_code}, {len(reports_list)}건"
                )
        except Exception as e:
            logger.warning(f"보고서 검색 실패: {e}")

        # 보고서가 없으면 DB에서 직접 가져오기
        if not reports_list:
            try:
                db_reports = Report.objects.filter(
                    company=company,
                    processing_status="completed",
                    submitted_at__gte=published_after.date(),
                ).order_by("-submitted_at")[:max_reports]

                reports_list = [
                    {
                        "report_id": r.id,
                        "report_name": r.report_name,
                        "summary": (
                            r.extracted_info.get("summary", "")
                            if r.extracted_info
                            else ""
                        ),
                        "submitted_at": r.submitted_at.isoformat(),
                    }
                    for r in db_reports
                ]
                logger.info(f"DB에서 보고서 조회: {len(reports_list)}건")
            except Exception as e:
                logger.warning(f"DB 보고서 조회 실패: {e}")

        return {"news": news_list, "reports": reports_list}

    def _generate_analysis(self, company: Company, search_data: dict) -> dict:
        """
        Gemini LLM으로 분석 생성

        Args:
            company: Company 모델 인스턴스
            search_data: 검색된 뉴스/보고서 데이터

        Returns:
            {"analysis": str, "upside_potential": str, "signal": str}
        """
        news_list = search_data.get("news", [])
        reports_list = search_data.get("reports", [])

        # 데이터가 전혀 없는 경우
        if not news_list and not reports_list:
            logger.warning(f"분석 데이터 부족: {company.stock_code}")
            return {
                "analysis": "최근 뉴스 및 보고서 데이터가 부족하여 분석이 어렵습니다.",
                "positive_factor": "-",
                "risk_factor": "-",
                "opinion": "관망 요망"
            }

        # 뉴스 제목 목록
        news_titles = "\n".join(
            [f"- {n.get('title', '')}" for n in news_list if n.get("title")]
        )
        if not news_titles:
            news_titles = "(최근 뉴스 없음)"

        # 보고서 요약 목록
        report_summaries = "\n".join(
            [
                f"- [{r.get('report_name', '')}] {r.get('summary', '')[:200]}"
                for r in reports_list
                if r.get("report_name")
            ]
        )
        if not report_summaries:
            report_summaries = "(최근 보고서 없음)"

        # 시가총액 포맷팅
        market_amount = company.market_amount
        if market_amount >= 1_0000_0000_0000:  # 조 단위
            market_str = f"{market_amount / 1_0000_0000_0000:.1f}조"
        elif market_amount >= 1_0000_0000:  # 억 단위
            market_str = f"{market_amount / 1_0000_0000:.0f}억"
        else:
            market_str = f"{market_amount:,}"

        prompt = f"""당신은 퀀트 투자 분석 전문가입니다. 아래 정보를 바탕으로 투자 전망을 분석하세요.

## 기업 정보
- 기업명: {company.company_name}
- 종목코드: {company.stock_code}
- 시가총액: {market_str}원

## 최근 뉴스 ({len(news_list)}건)
{news_titles}

## 최근 공시 보고서 ({len(reports_list)}건)
{report_summaries}

## 분석 요청
위 정보를 종합하여 투자 전망을 분석하고, 다음 JSON 형식으로만 응답하세요:
{{
    "analysis": "3줄 이내의 간결한 투자 전망 분석. 실제 자료들을 바탕으로 핵심 포인트만 요약.",
    "positive_factor": "주가 상승의 핵심 동력 1줄 요약",
    "risk_factor": "투자 시 가장 주의해야 할 리스크 1줄 요약",
    "option": "위 내용을 종합한 최종 투자 판단 근거 1줄 요약
}}

주의사항:
- JSON 형식으로만 응답하세요.
- analysis는 반드시 3줄 이내로 작성하고 분석한 내용만 작성하세요.
- positive_factor, risk_factor, option은 반드시 지정된 값만 사용하세요.
- positive_factor는 핵심 긍정 요인 한 줄로 작성하세요.
- risk_factor는 핵심 리스크 요인 한 줄로 작성하세요.
- option은 최종 투자 의견 한 줄로 작성하세요.
- 분석을 생성할 때 추가 정보 부재에 대한 언급은 하지 마세요.

""" 

        try:
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                },
            ]

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=GenerateContentConfig(safety_settings=safety_settings),
            )
            text = response.text.strip()

            # JSON 파싱
            if "{" in text and "}" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                json_text = text[start:end]
                try:
                    result = json.loads(json_text)

                    return {
                        "analysis": result.get("analysis", "분석 데이터가 부족합니다."),
                        "positive_factor": result.get("positive_factor", "긍정 요인 정보 없음"),
                        "risk_factor": result.get("risk_factor", "리스크 요인 정보 없음"),
                        "opinion": result.get("option", "투자 의견 정보 없음"),
                    }
                except json.JSONDecodeError:
                    logger.warning(f"JSON 파싱 실패: {json_text[:100]}")

            # JSON 파싱 실패 시 텍스트 그대로 반환
            return {
                "analysis": text[:300] if text else "분석 생성 실패",
                "positive_factor": "정보 없음",
                "risk_factor": "정보 없음",
                "opinion": "분석 실패",
            }

        except Exception as e:
            error_message = str(e)
            if "429" in error_message or "quota" in error_message.lower():
                logger.warning("Gemini API 쿼터 초과")
                raise QuotaExceededError("API 요청 한도를 초과했습니다.")
            else:
                logger.error(f"LLM 분석 실패: {error_message}")
                raise LLMServiceError("분석 서비스 일시 불가")


class QuotaExceededError(Exception):
    """API 쿼터 초과 에러"""

    pass


class LLMServiceError(Exception):
    """LLM 서비스 에러"""

    pass
