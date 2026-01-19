"""
산업 전망 분석 서비스

OpenSearch에 저장된 특정 산업 관련 뉴스와 해당 산업 소속 기업들의 보고서를 분석하여
퀀트 투자자가 산업 트렌드를 파악할 수 있는 전망을 제공합니다.
"""

import json
import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.db.models import QuerySet, Sum, Avg, Count
from django.utils import timezone
from google import genai
from google.genai.types import GenerateContentConfig

from industries.models import Industry
from companies.models import Company, Report
from news.services.opensearch import OpenSearchService
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class IndustryOutlookService:
    """
    산업 전망 분석 서비스

    - OpenSearch에서 산업 뉴스 및 기업 보고서 검색
    - Gemini LLM으로 낙관/중립/비관 시나리오 분석 생성
    - Redis 캐싱 (TTL: 1시간)
    """

    CACHE_KEY_PREFIX = "industry_outlook"
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
        logger.debug(f"IndustryOutlookService 초기화: {self.model_name}")

    def _get_cache_key(self, industry_id: int) -> str:
        """캐시 키 생성"""
        return f"{self.CACHE_KEY_PREFIX}:{industry_id}:{self.CACHE_VERSION}"

    def analyze_outlook(
        self,
        industry: Industry,
        days_back: int = 30,
        max_news: int = 20,
        max_reports: int = 10,
        top_companies: int = 10,
    ) -> dict:
        """
        산업 전망 분석

        Args:
            industry: Industry 모델 인스턴스
            days_back: 뉴스/보고서 검색 기간 (일)
            max_news: 최대 뉴스 수
            max_reports: 최대 보고서 수
            top_companies: 보고서 수집 대상 상위 기업 수 (시가총액 기준)

        Returns:
            분석 결과 dict
        """
        industry_id = industry.industry_id

        # 1. 캐시 확인
        cache_key = self._get_cache_key(industry_id)
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"캐시 히트: {cache_key}")
            return cached_result

        # 2. 데이터 검색
        search_data = self._search_industry_data(
            industry, days_back, max_news, max_reports, top_companies
        )

        # 3. LLM 시나리오 분석 생성
        scenario_result = self._generate_scenario_analysis(industry, search_data)

        # 4. 산업 통계 계산
        companies = search_data.get("companies", [])
        statistics = self._calculate_industry_statistics(companies)

        # 5. 결과 구성
        result = {
            "industry_id": industry_id,
            "industry_name": industry.name,
            "ksic_code": industry.induty_code or "",
            "analyzed_at": timezone.now().isoformat(),
            "scenarios": scenario_result.get("scenarios", {}),
            "industry_statistics": statistics,
            "data_sources": {
                "news_count": len(search_data.get("news", [])),
                "report_count": len(search_data.get("reports", [])),
                "company_count": len(companies),
            },
        }

        # 6. 캐싱
        cache.set(cache_key, result, self.CACHE_TTL)
        logger.info(f"캐시 저장: {cache_key}, TTL={self.CACHE_TTL}s")

        return result

    def _search_industry_data(
        self,
        industry: Industry,
        days_back: int,
        max_news: int,
        max_reports: int,
        top_companies: int,
    ) -> dict:
        """
        산업 관련 데이터 검색

        Args:
            industry: Industry 모델 인스턴스
            days_back: 검색 기간 (일)
            max_news: 최대 뉴스 수
            max_reports: 최대 보고서 수
            top_companies: 보고서 수집 대상 상위 기업 수

        Returns:
            {"news": [...], "reports": [...], "companies": [...]}
        """
        published_after = timezone.now() - timedelta(days=days_back)
        news_list = []
        reports_list = []
        companies_list = []

        # 1. 해당 산업 소속 기업 목록 조회 (시가총액 상위 N개)
        try:
            top_companies_qs = (
                Company.objects.filter(industry=industry, is_deleted=False)
                .order_by("-market_amount")[:top_companies]
            )
            companies_list = list(top_companies_qs)
            logger.info(
                f"산업 {industry.name} 소속 상위 기업 조회: {len(companies_list)}개"
            )
        except Exception as e:
            logger.warning(f"산업 소속 기업 조회 실패: {e}")

        # 2. 산업 관련 뉴스 검색 (산업명 키워드)
        try:
            opensearch_service = OpenSearchService()
            news_results = opensearch_service.search_news_by_keyword(
                keyword=industry.name,
                size=max_news,
                published_after=published_after,
            )
            news_list = news_results
            logger.info(f"산업 뉴스 검색 완료: {industry.name}, {len(news_list)}건")
        except Exception as e:
            logger.warning(f"산업 뉴스 검색 실패: {e}")

        # 3. 상위 기업들의 보고서 검색
        if companies_list:
            try:
                # 기업 이름들을 조합하여 벡터 검색 쿼리 생성
                company_names = " ".join([c.company_name for c in companies_list[:5]])
                embedding_service = EmbeddingService()
                query_vector = embedding_service.create_embedding(
                    f"{industry.name} 산업 {company_names} 실적 전망 분석"
                )

                if query_vector:
                    report_service = ReportOpenSearchService()
                    # 각 기업별로 보고서 검색하여 통합
                    for company in companies_list:
                        company_reports = report_service.search_similar_reports(
                            query_vector=query_vector,
                            size=max(1, max_reports // len(companies_list)),
                            company_stock_code=company.stock_code,
                        )
                        reports_list.extend(company_reports)

                    # 최대 개수만큼만 유지
                    reports_list = reports_list[:max_reports]
                    logger.info(f"보고서 검색 완료: {len(reports_list)}건")
            except Exception as e:
                logger.warning(f"보고서 검색 실패: {e}")

        # 4. 보고서가 없으면 DB에서 직접 가져오기
        if not reports_list and companies_list:
            try:
                stock_codes = [c.stock_code for c in companies_list]
                db_reports = (
                    Report.objects.filter(
                        company__stock_code__in=stock_codes,
                        processing_status="completed",
                        submitted_at__gte=published_after.date(),
                    )
                    .order_by("-submitted_at")[:max_reports]
                )

                reports_list = [
                    {
                        "report_id": r.id,
                        "report_name": r.report_name,
                        "company_name": r.company.company_name,
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

        return {
            "news": news_list,
            "reports": reports_list,
            "companies": companies_list,
        }

    def _calculate_industry_statistics(
        self, companies: list[Company]
    ) -> dict:
        """
        산업 통계 계산

        Args:
            companies: 산업 소속 기업 리스트

        Returns:
            산업 통계 dict
        """
        if not companies:
            return {
                "company_count": 0,
                "total_market_cap": 0,
                "avg_market_cap": 0,
                "top_companies": [],
            }

        # 시가총액 합계 및 평균
        total_market_cap = sum(c.market_amount for c in companies)
        avg_market_cap = total_market_cap // len(companies) if companies else 0

        # 상위 기업 목록 (최대 5개)
        top_companies_list = [
            {
                "stock_code": c.stock_code,
                "company_name": c.company_name,
                "market_amount": c.market_amount,
            }
            for c in companies[:5]
        ]

        return {
            "company_count": len(companies),
            "total_market_cap": total_market_cap,
            "avg_market_cap": avg_market_cap,
            "top_companies": top_companies_list,
        }

    def _generate_scenario_analysis(
        self, industry: Industry, search_data: dict
    ) -> dict:
        """
        Gemini LLM으로 시나리오별 분석 생성

        Args:
            industry: Industry 모델 인스턴스
            search_data: 검색된 뉴스/보고서/기업 데이터

        Returns:
            {"scenarios": {"optimistic": {...}, "neutral": {...}, "pessimistic": {...}}}
        """
        news_list = search_data.get("news", [])
        reports_list = search_data.get("reports", [])
        companies_list = search_data.get("companies", [])

        # 데이터가 전혀 없는 경우
        if not news_list and not reports_list:
            logger.warning(f"분석 데이터 부족: {industry.industry_id}")
            return {
                "scenarios": {
                    "optimistic": {
                        "analysis": "최근 데이터가 부족하여 낙관 시나리오 분석이 어렵습니다.",
                        "key_factors": [],
                    },
                    "neutral": {
                        "analysis": "최근 데이터가 부족하여 중립 시나리오 분석이 어렵습니다.",
                        "key_factors": [],
                    },
                    "pessimistic": {
                        "analysis": "최근 데이터가 부족하여 비관 시나리오 분석이 어렵습니다.",
                        "key_factors": [],
                    },
                }
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
                f"- [{r.get('company_name', '')}] {r.get('report_name', '')}: {r.get('summary', '')[:150]}"
                for r in reports_list
                if r.get("report_name")
            ]
        )
        if not report_summaries:
            report_summaries = "(최근 보고서 없음)"

        # 산업 통계
        statistics = self._calculate_industry_statistics(companies_list)
        total_market_str = self._format_market_cap(statistics["total_market_cap"])
        avg_market_str = self._format_market_cap(statistics["avg_market_cap"])

        prompt = f"""당신은 퀀트 투자 산업 분석 전문가입니다. 아래 정보를 바탕으로 {industry.name} 산업의 전망을 낙관/중립/비관 시나리오로 분석하세요.

## 산업 정보
- 산업명: {industry.name}
- KSIC 코드: {industry.induty_code or 'N/A'}
- 소속 기업 수: {statistics['company_count']}개
- 총 시가총액: {total_market_str}원
- 평균 시가총액: {avg_market_str}원

## 최근 뉴스 ({len(news_list)}건)
{news_titles}

## 주요 기업 공시 보고서 ({len(reports_list)}건)
{report_summaries}

## 분석 요청
위 정보를 종합하여 다음 JSON 형식으로만 응답하세요:

{{
  "optimistic": {{
    "analysis": "낙관 시나리오 3줄 이내 분석 (긍정적 전망, 성장 동력, 호재 요인 중심)",
    "key_factors": ["긍정 요인1", "긍정 요인2", "긍정 요인3"]
  }},
  "neutral": {{
    "analysis": "중립 시나리오 3줄 이내 분석 (현 상황 유지, 불확실성, 관망 필요)",
    "key_factors": ["중립 요인1", "중립 요인2", "중립 요인3"]
  }},
  "pessimistic": {{
    "analysis": "비관 시나리오 3줄 이내 분석 (부정적 전망, 하락 리스크, 악재 요인 중심)",
    "key_factors": ["부정 요인1", "부정 요인2", "부정 요인3"]
  }}
}}

## 시나리오 정의
- **낙관 시나리오**: 긍정적 뉴스, 실적 개선, 정책 지원, 기술 혁신 등 최선의 경우
- **중립 시나리오**: 현재 추세 유지, 불확실성 존재, 단기 전망 불투명
- **비관 시나리오**: 부정적 뉴스, 실적 악화, 규제 강화, 구조적 리스크 등 최악의 경우

## 주의사항
- JSON 형식으로만 응답하세요.
- 각 시나리오의 analysis는 반드시 3줄 이내로 작성하세요.
- key_factors는 각 시나리오당 2-5개로 구성하세요.
- 추측이 아닌 제공된 데이터에 기반하여 분석하세요.
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
                    # 시나리오 구조 검증
                    scenarios = {}
                    for scenario_type in ["optimistic", "neutral", "pessimistic"]:
                        scenario_data = result.get(scenario_type, {})
                        scenarios[scenario_type] = {
                            "analysis": scenario_data.get(
                                "analysis", "분석 데이터가 부족합니다."
                            ),
                            "key_factors": scenario_data.get("key_factors", []),
                        }

                    return {"scenarios": scenarios}
                except json.JSONDecodeError:
                    logger.warning(f"JSON 파싱 실패: {json_text[:100]}")

            # JSON 파싱 실패 시 기본 응답 반환
            return {
                "scenarios": {
                    "optimistic": {
                        "analysis": "분석 생성 실패",
                        "key_factors": [],
                    },
                    "neutral": {
                        "analysis": "분석 생성 실패",
                        "key_factors": [],
                    },
                    "pessimistic": {
                        "analysis": "분석 생성 실패",
                        "key_factors": [],
                    },
                }
            }

        except Exception as e:
            error_message = str(e)
            if "429" in error_message or "quota" in error_message.lower():
                logger.warning("Gemini API 쿼터 초과")
                raise QuotaExceededError("API 요청 한도를 초과했습니다.")
            else:
                logger.error(f"LLM 분석 실패: {error_message}")
                raise LLMServiceError("분석 서비스 일시 불가")

    def _format_market_cap(self, amount: int) -> str:
        """시가총액 포맷팅"""
        if amount >= 1_0000_0000_0000:  # 조 단위
            return f"{amount / 1_0000_0000_0000:.1f}조"
        elif amount >= 1_0000_0000:  # 억 단위
            return f"{amount / 1_0000_0000:.0f}억"
        else:
            return f"{amount:,}"


class QuotaExceededError(Exception):
    """API 쿼터 초과 에러"""

    pass


class LLMServiceError(Exception):
    """LLM 서비스 에러"""

    pass
