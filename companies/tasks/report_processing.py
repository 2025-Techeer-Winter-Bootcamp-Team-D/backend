"""
보고서 처리 Celery 태스크
보고서 본문 추출, 정제, 정보 추출, 임베딩 생성을 수행합니다.

워크플로우:
1. Extract Raw HTML/XML - OpenDartReader로 필요한 섹션(주로 II. 사업의 내용)만 타겟팅하여 추출
2. Structure Preservation - HTML 표를 Markdown Table로 변환
3. Classify Entity Type - 기업 유형을 [제조, 금융, 지주사, 기타]로 분류
4. Dynamic Info Extraction - 분류 결과에 따라 서로 다른 프롬프트 주입
5. Validation & Fallback - revenue_composition이 비어있다면 재무제표 API 호출 또는 재탐색
6. Selective Embedding - key_info와 요약본만 임베딩하여 검색 효율 증대
"""

import logging
from typing import Any

from celery import chain, shared_task
from django.utils import timezone

from companies.models import Report, RevenueComposition
from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.services.report_extractor import ReportExtractorService
from companies.services.report_info_extractor import ReportInfoExtractorService
from companies.services.report_section_extractor import ReportSectionExtractorService
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.embedding import EmbeddingService
from news.services.refiner import RefineService

logger = logging.getLogger(__name__)


def _try_fetch_revenue_from_financial_api(
    corp_code: str, submitted_at: str, report_name: str
) -> list[dict[str, Any]] | None:
    """
    Step 5: Validation & Fallback
    revenue_composition이 비어있을 때 재무제표 API를 호출하여 매출 구성 추출 시도

    Args:
        corp_code: 기업 고유번호
        submitted_at: 보고서 제출일
        report_name: 보고서명

    Returns:
        매출 구성 리스트 (실패 시 None)
    """
    try:
        # 사업연도 추출
        fiscal_year = None
        if submitted_at:
            try:
                from dateutil import parser as date_parser

                parsed_date = date_parser.parse(submitted_at)
                fiscal_year = parsed_date.year
            except (ValueError, TypeError, AttributeError):
                if len(submitted_at) >= 4 and submitted_at[:4].isdigit():
                    fiscal_year = int(submitted_at[:4])

        if not fiscal_year:
            logger.warning("사업연도 추출 실패, 재무제표 API 호출 불가")
            return None

        # 보고서 코드 결정
        if "사업보고서" in report_name:
            report_code = "11011"
        elif "반기보고서" in report_name:
            report_code = "11012"
        else:
            report_code = "11011"  # 기본값

        # DART API 호출
        dart_client = DartAPIClient()
        financial_data = dart_client.get_financial_statements(
            corp_code, str(fiscal_year), report_code
        )

        # 재무제표에서 매출 구성 추출
        # DART API 응답 구조: {"list": [{"account_nm": "매출액", "fs_div": "CFS", ...}, ...]}
        account_list = financial_data.get("list", [])

        # 부문별 매출 데이터 찾기
        # 주의: DART API의 재무제표는 일반적으로 연결재무제표 기준이며,
        # 부문별 매출은 별도 API나 보고서 본문에서 추출해야 할 수 있음
        # 여기서는 간단한 fallback으로 주요 계정과목만 추출

        revenue_composition = []
        total_revenue = 0

        # 매출액 관련 계정과목 찾기
        for account in account_list:
            account_nm = account.get("account_nm", "")
            if "매출" in account_nm or "수익" in account_nm:
                amount_str = account.get("thstrm_amount", "0")
                try:
                    amount = int(amount_str.replace(",", "")) if amount_str else 0
                    if amount > 0:
                        total_revenue += amount
                        revenue_composition.append(
                            {
                                "segment": account_nm,
                                "revenue": amount,
                                "ratio": None,  # 비율은 나중에 계산
                            }
                        )
                except (ValueError, TypeError):
                    continue

        # 비율 계산
        if total_revenue > 0:
            for item in revenue_composition:
                if item["revenue"] > 0:
                    item["ratio"] = round((item["revenue"] / total_revenue) * 100, 2)

        if revenue_composition:
            logger.info(
                f"재무제표 API에서 매출 구성 추출 성공: {len(revenue_composition)}개 항목"
            )
            return revenue_composition

        return None

    except DartAPIError as e:
        logger.warning(f"재무제표 API 호출 실패: {e}")
        return None
    except Exception as e:
        logger.error(f"재무제표 API Fallback 오류: {e}", exc_info=True)
        return None


@shared_task(bind=True, max_retries=3)
def extract_report_content_task(self, report_id: int) -> dict[str, Any] | None:
    """
    Step 1: Extract Raw HTML/XML
    OpenDartReader를 통해 필요한 섹션(주로 II. 사업의 내용)만 타겟팅하여 추출
    """
    try:
        report = Report.objects.select_related("company").get(id=report_id)
        report.processing_status = "processing"
        report.save(update_fields=["processing_status"])

        extractor = ReportExtractorService()
        # XML 원문 추출 (섹션별 파싱용)
        xml_content = extractor.extract_xml_content(report.rcept_no)

        if not xml_content:
            logger.warning(
                f"보고서 XML 추출 실패: {report_id} (rcept_no: {report.rcept_no})"
            )
            report.processing_status = "failed"
            report.save(update_fields=["processing_status"])
            return None

        # Step 2: Structure Preservation - 섹션별 추출 및 표를 Markdown으로 변환
        section_extractor = ReportSectionExtractorService()
        sections = section_extractor.extract_sections_with_tables(
            xml_content, report.report_name
        )
        section_content = sections.get("main_content", "")
        tables_markdown = sections.get("tables", "")

        # 전체 본문도 추출 (fallback용)
        raw_content = extractor.extract_content(report.rcept_no)

        # 섹션 추출 결과가 있으면 우선 사용, 없으면 전체 본문 사용
        if not section_content and not tables_markdown:
            logger.warning(f"섹션별 추출 실패, 전체 본문 사용: {report_id}")
            if raw_content:
                section_content = raw_content
            else:
                report.processing_status = "failed"
                report.save(update_fields=["processing_status"])
                return None

        report.raw_content = raw_content or section_content
        report.save(update_fields=["raw_content"])

        return {
            "report_id": report_id,
            "rcept_no": report.rcept_no,
            "raw_content": raw_content or section_content,  # fallback용
            "xml_content": xml_content,  # 섹션별 파싱용 XML 원문
            "section_content": section_content,  # Step 2 결과
            "tables_markdown": tables_markdown,  # Step 2 결과
            "company_stock_code": report.company.stock_code,
            "company_name": report.company.company_name,
            "company_corp_code": report.company.corp_code,  # Fallback용
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
    """
    Step 2: Structure Preservation (이미 Step 1에서 수행됨)
    보고서 본문 정제 (섹션별 추출은 이미 완료)

    주의: RefineService는 뉴스 기사용이므로 보고서 정제 시 과도하게 내용이 제거될 수 있음.
    정제 결과가 너무 짧으면 원본 내용(raw_content)을 사용하여 fallback 처리.
    """
    if not data:
        return None

    report_id = data.get("report_id")
    try:
        # Step 1에서 이미 섹션별 추출 완료
        section_content = data.get("section_content", "")
        tables_markdown = data.get("tables_markdown", "")
        raw_content = data.get("raw_content", "")

        # 섹션 내용이 있으면 우선 사용, 없으면 전체 본문 정제
        content_to_refine = section_content if section_content else raw_content

        if not content_to_refine:
            logger.warning(f"정제할 내용이 없음: {report_id}")
            Report.objects.filter(id=report_id).update(processing_status="failed")
            return None

        # 보고서 전용 정제 메서드 사용
        refiner = RefineService()
        refined_content = refiner.get_refined_report_body(content_to_refine)

        # 정제 결과가 없거나 짧아도 원본 내용 사용하여 계속 진행
        if not refined_content or len(refined_content.strip()) < 100:
            logger.warning(
                f"보고서 정제 결과가 짧음 ({len(refined_content.strip()) if refined_content else 0}자), "
                f"원본 내용 사용: {report_id}"
            )
            refined_content = content_to_refine

        # DB 업데이트
        Report.objects.filter(id=report_id).update(refined_content=refined_content)

        data["refined_content"] = refined_content
        # section_content와 tables_markdown은 이미 Step 1에서 설정됨
        return data
    except Exception as e:
        logger.error(f"보고서 정제 오류: {report_id} - {e}")
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3)
def extract_report_info_task(self, data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Step 3: Classify Entity Type + Step 4: Dynamic Info Extraction
    기업 유형 분류 및 분류 결과에 따른 정보 추출
    Step 5: Validation & Fallback - revenue_composition이 비어있으면 재무제표 API 호출 또는 재탐색
    """
    if not data:
        return None

    try:
        report_id = data["report_id"]
        refined_content = data["refined_content"]
        section_content = data.get("section_content", "")
        tables_markdown = data.get("tables_markdown", "")
        company_name = data["company_name"]
        company_stock_code = data["company_stock_code"]
        company_corp_code = data.get("company_corp_code")
        report_name = data["report_name"]
        submitted_at = data.get("submitted_at", "")

        # Step 3 & 4: 기업 유형 분류 및 정보 추출
        extractor = ReportInfoExtractorService()
        extracted_info = extractor.extract_info(
            refined_content=refined_content,
            report_name=report_name,
            company_name=company_name,
            section_content=section_content,
            tables_markdown=tables_markdown,
        )

        # Step 5: Validation & Fallback
        revenue_composition = extracted_info.get("revenue_composition", [])
        # revenue_composition이 비어있거나 유효하지 않은 경우 Fallback 시도
        if (
            not revenue_composition
            or (isinstance(revenue_composition, list) and len(revenue_composition) == 0)
            or (
                isinstance(revenue_composition, list)
                and len(revenue_composition) == 1
                and isinstance(revenue_composition[0], dict)
                and revenue_composition[0].get("segment", "").strip() == "비고"
            )
        ):
            # 사업보고서/반기보고서인 경우에만 Fallback 시도
            if (
                "사업보고서" in report_name or "반기보고서" in report_name
            ) and company_corp_code:
                logger.info(
                    f"매출 구성이 비어있음, 재무제표 API Fallback 시도: {report_id}"
                )
                fallback_revenue = _try_fetch_revenue_from_financial_api(
                    company_corp_code, submitted_at, report_name
                )
                if fallback_revenue:
                    extracted_info["revenue_composition"] = fallback_revenue
                    logger.info(
                        f"재무제표 API에서 매출 구성 추출 성공: {report_id} - "
                        f"{len(fallback_revenue)}개 부문"
                    )
                else:
                    logger.warning(
                        f"재무제표 API Fallback 실패, 매출 구성 없이 진행: {report_id}"
                    )

        # 주요 키워드 추출 및 검증/정규화
        raw_keyword = extracted_info.get("primary_keyword", "")
        primary_keyword = None

        if raw_keyword:
            try:
                # 문자열로 변환
                if not isinstance(raw_keyword, str):
                    primary_keyword = str(raw_keyword)
                else:
                    primary_keyword = raw_keyword

                # 공백 제거
                primary_keyword = primary_keyword.strip()

                # 최대 길이 제한 (200자)
                if len(primary_keyword) > 200:
                    primary_keyword = primary_keyword[:200]
                    logger.warning(
                        f"primary_keyword가 200자를 초과하여 잘랐습니다: {report_id}"
                    )

                # 빈 문자열이면 None으로 설정
                if not primary_keyword:
                    primary_keyword = None
            except Exception as e:
                logger.error(
                    f"primary_keyword 변환 실패: {report_id} - {e}", exc_info=True
                )
                primary_keyword = None

        # DB 업데이트 (extracted_info JSON 및 primary_keyword 저장)
        Report.objects.filter(id=report_id).update(
            extracted_info=extracted_info,
            primary_keyword=primary_keyword,
        )

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
            others_segment = None  # "기타" 항목 저장용
            total_ratio = 0.0  # 나머지 항목들의 ratio 합

            # 먼저 "기타" 항목을 제외한 나머지 항목 처리
            for segment in revenue_composition:
                # 필수 키 검증: segment 필드가 있고 비어있지 않은지 확인
                segment_name = (
                    segment.get("segment") if isinstance(segment, dict) else None
                )
                if not segment_name or not str(segment_name).strip():
                    logger.warning(
                        f"매출 구성 항목 건너뜀 (segment 누락/비어있음): report_id={report_id}, "
                        f"company={company_stock_code}, segment_data={segment}"
                    )
                    continue

                segment_name = str(segment_name).strip()

                # "기타" 항목은 나중에 처리
                if segment_name == "기타":
                    others_segment = segment
                    continue

                # revenue를 int/Decimal로 안전하게 변환
                try:
                    revenue_value = segment.get("revenue", 0)
                    if revenue_value is None:
                        revenue_value = 0
                    revenue_value = int(revenue_value)

                    # 매출(revenue)은 음수가 될 수 없음 - 마이너스 값은 건너뜀
                    if revenue_value < 0:
                        logger.warning(
                            f"매출 구성 항목 건너뜀 (revenue가 마이너스): report_id={report_id}, "
                            f"company={company_stock_code}, segment={segment_name}, revenue={revenue_value}"
                        )
                        continue
                except (ValueError, TypeError):
                    logger.warning(
                        f"매출 구성 항목 revenue 변환 실패, 건너뜀: report_id={report_id}, "
                        f"company={company_stock_code}, revenue={segment.get('revenue')}"
                    )
                    continue

                # ratio가 숫자 또는 None인지 검증
                ratio_value = segment.get("ratio")
                if ratio_value is not None:
                    try:
                        # 문자열 "58.1%" 형태 처리
                        if isinstance(ratio_value, str):
                            ratio_value = ratio_value.replace("%", "").strip()
                        ratio_value = float(ratio_value)
                        # 유효한 ratio만 합산
                        if ratio_value > 0:
                            total_ratio += ratio_value
                    except (ValueError, TypeError):
                        logger.warning(
                            f"매출 구성 항목 ratio 변환 실패, None 사용: report_id={report_id}, "
                            f"company={company_stock_code}, ratio={segment.get('ratio')}"
                        )
                        ratio_value = None

                RevenueComposition.objects.update_or_create(
                    company_id=company_stock_code,
                    fiscal_year=fiscal_year,
                    segment_name=segment_name,
                    defaults={
                        "revenue": revenue_value,
                        "ratio": ratio_value,
                    },
                )
                saved_count += 1

            # "기타" 항목 처리: ratio를 100 - (나머지 ratio 합)으로 계산
            # ratio가 0이면 저장하지 않음
            if others_segment:
                segment_name = "기타"
                others_ratio = max(0.0, 100.0 - total_ratio)  # 최소 0

                # ratio가 0이면 저장하지 않음
                if others_ratio <= 0:
                    logger.debug(
                        f"매출 구성 기타 항목 제외 (ratio가 0): report_id={report_id}, "
                        f"company={company_stock_code}, 계산값: 100 - {total_ratio:.2f} = {others_ratio:.2f}"
                    )
                else:
                    # revenue는 원본 데이터 사용 (마이너스여도 상관없음 - ratio만 계산)
                    try:
                        revenue_value = others_segment.get("revenue", 0)
                        if revenue_value is None:
                            revenue_value = 0
                        else:
                            revenue_value = int(revenue_value)
                            # 마이너스면 0으로 설정 (매출은 음수가 될 수 없음)
                            if revenue_value < 0:
                                revenue_value = 0
                    except (ValueError, TypeError):
                        revenue_value = 0

                    RevenueComposition.objects.update_or_create(
                        company_id=company_stock_code,
                        fiscal_year=fiscal_year,
                        segment_name=segment_name,
                        defaults={
                            "revenue": revenue_value,
                            "ratio": round(others_ratio, 2),  # 소수점 2자리로 반올림
                        },
                    )
                    saved_count += 1

                    logger.debug(
                        f"매출 구성 기타 항목 처리: report_id={report_id}, "
                        f"company={company_stock_code}, ratio={round(others_ratio, 2)}% (계산값: 100 - {total_ratio:.2f})"
                    )

            logger.info(
                f"매출 구성 저장 완료: {report_id} - {saved_count}개 부문 저장 "
                f"(총 {len(revenue_composition)}개 중)"
            )

        data["extracted_info"] = extracted_info
        return data
    except Exception as e:
        logger.error(f"정보 추출 오류: {data.get('report_id')} - {e}")
        # Celery retry 호출 (지수 백오프)
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3)
def create_report_embedding_task(self, data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Step 6: Selective Embedding
    보고서 전체가 아닌, 추출된 key_info와 정제된 요약본만 임베딩하여 검색 효율 증대
    """
    if not data:
        return None

    report_id = data.get("report_id")
    try:
        extracted_info = data.get("extracted_info", {})

        # key_info와 summary만 추출하여 임베딩
        key_info = extracted_info.get("key_info", {})
        summary = extracted_info.get("summary", {})
        one_line_summary = summary.get("one_line", "")

        # key_info를 문자열로 변환
        key_info_text = ""
        if isinstance(key_info, dict):
            key_info_items = []
            for key, value in key_info.items():
                key_info_items.append(f"{key}: {value}")
            key_info_text = "\n".join(key_info_items)

        # 임베딩할 텍스트 구성: key_info + summary
        embedding_text = f"{key_info_text}\n\n요약: {one_line_summary}".strip()

        # 텍스트가 너무 짧으면 전체 본문 사용 (fallback)
        if len(embedding_text) < 50:
            logger.warning(f"임베딩 텍스트가 너무 짧음, 전체 본문 사용: {report_id}")
            embedding_text = data.get("refined_content", "")[:10000]  # 최대 10,000자

        if not embedding_text:
            logger.warning(f"임베딩할 텍스트가 없음: {report_id}")
            return data

        embedding_service = EmbeddingService()
        embedding = embedding_service.create_embedding(embedding_text)

        if not embedding:
            logger.warning(f"임베딩 생성 실패: {report_id}")
            # 임베딩 실패는 재시도 의미 없음 (서비스 문제), 파이프라인 계속 진행
            return data

        # DB 업데이트
        Report.objects.filter(id=report_id).update(embedding=embedding)

        data["embedding"] = embedding
        return data
    except Exception as e:
        logger.error(f"임베딩 생성 오류: {report_id} - {e}")
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


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
