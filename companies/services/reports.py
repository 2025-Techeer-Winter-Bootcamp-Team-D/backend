# companies/services/reports.py
"""
보고서 서비스
DART API를 통해 공시 보고서 목록을 조회하고 Report 모델에 저장하는 서비스
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from companies.models import Company, Report
from companies.services.dart_api import DartAPIClient, DartAPIError

logger = logging.getLogger(__name__)


def _trigger_report_processing(report: Report):
    """
    보고서 자동 처리 트리거 (사업보고서 및 반기보고서)

    Args:
        report: Report 인스턴스
    """
    from companies.tasks.report_processing import process_single_report_pipeline

    # 보고서 이름에 "사업보고서" 또는 "반기보고서"가 포함되어 있으면 자동 처리
    if "사업보고서" in report.report_name or "반기보고서" in report.report_name:
        report_type = (
            "사업보고서" if "사업보고서" in report.report_name else "반기보고서"
        )
        logger.info(
            f"{report_type} 자동 처리 트리거: {report.rcept_no} - {report.report_name}"
        )
        process_single_report_pipeline.delay(report.id)
    else:
        logger.debug(
            f"일반 보고서 (처리 안함): {report.rcept_no} - {report.report_name}"
        )


class ReportsService:
    """보고서 서비스"""

    def __init__(self):
        self.dart_client = DartAPIClient()

    def sync_reports(
        self,
        company: Company,
        days: int = 365,
        report_type: Optional[str] = None,
        incremental: bool = True,
        report_types: Optional[List[str]] = None,
    ) -> List[Report]:
        """
        DART API에서 보고서 목록을 조회하여 Report 모델에 저장

        Args:
            company: Company 인스턴스
            days: 조회할 기간 (일 단위, 기본값: 365일, incremental=True일 때는 fallback으로만 사용)
            report_type: 공시유형 필터 (단일 타입, report_types와 함께 사용 불가)
            incremental: 증분 동기화 여부 (기본값: True, 마지막 동기화 이후 보고서만)
            report_types: 공시유형 필터 리스트 (예: ["A", "B"], None이면 전체)

        Returns:
            생성/업데이트된 Report 인스턴스 리스트

        Raises:
            DartAPIError: DART API 호출 실패 시
            ValueError: corp_code가 없는 경우
        """
        if not company.corp_code:
            raise ValueError(
                f"Company {company.stock_code}에 corp_code가 설정되지 않았습니다."
            )

        try:
            # 증분 동기화: 마지막 동기화 날짜 확인
            if incremental:
                # 해당 기업의 가장 최근 보고서 날짜 확인
                latest_report = (
                    Report.objects.filter(company=company)
                    .order_by("-submitted_at")
                    .first()
                )
                if latest_report:
                    start_date = latest_report.submitted_at
                    logger.info(
                        f"증분 동기화: 마지막 동기화 날짜 이후 ({start_date}) 보고서만 조회"
                    )
                else:
                    # 보고서가 없으면 days 기간으로 fallback
                    start_date = datetime.now().date() - timedelta(days=days)
                    logger.info(
                        f"증분 동기화: 기존 보고서 없음, {days}일 기간으로 조회"
                    )
            else:
                # 전체 동기화: days 기간 사용
                start_date = datetime.now().date() - timedelta(days=days)

            end_date = datetime.now().date()
            bgn_de = start_date.strftime("%Y%m%d")
            end_de = end_date.strftime("%Y%m%d")

            # 주요 공시만 필터링 (기본값: 정기공시 + 주요사항보고)
            if report_types is None and report_type is None:
                report_types = ["A", "B"]  # 정기공시 + 주요사항보고
                logger.info("주요 공시만 동기화: 정기공시(A) + 주요사항보고(B)")
            elif report_type:
                report_types = [report_type]

            # 각 공시유형별로 조회 (DART API는 한 번에 하나의 타입만 필터링 가능)
            all_reports = []
            for rt in report_types:
                # 페이지네이션을 위한 변수
                page_no = 1
                page_count = 100

                # 모든 페이지 조회
                while True:
                    # DART API에서 공시 목록 조회
                    data = self.dart_client.get_disclosure_list(
                        company.corp_code,
                        bgn_de=bgn_de,
                        end_de=end_de,
                        pblntf_ty=rt,
                        page_no=page_no,
                        page_count=page_count,
                    )

                    report_list = data.get("list", [])
                    if not report_list:
                        break

                    # 보고서 저장
                    for item in report_list:
                        try:
                            # DART API 응답에 pblntf_ty 필드가 있는지 확인
                            report_type_from_api = item.get("pblntf_ty")
                            if not report_type_from_api:
                                # pblntf_ty가 없으면 요청한 타입(rt)을 사용
                                report_type_from_api = rt
                                logger.debug(
                                    f"API 응답에 pblntf_ty 없음, 요청 타입 사용: {rt}, 보고서명: {item.get('report_nm')}"
                                )

                            report, created = Report.objects.update_or_create(
                                rcept_no=item["rcept_no"],
                                defaults={
                                    "company": company,
                                    "report_name": item["report_nm"],
                                    "report_type": report_type_from_api,
                                    "submitted_at": datetime.strptime(
                                        item["rcept_dt"], "%Y%m%d"
                                    ).date(),
                                    "report_url": (
                                        f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}"
                                    ),
                                },
                            )
                            all_reports.append(report)

                            # 사업보고서 자동 처리 트리거
                            if created:
                                _trigger_report_processing(report)
                        except (KeyError, ValueError) as e:
                            logger.warning(
                                f"보고서 데이터 파싱 오류: {item.get('rcept_no', 'unknown')} - {e}"
                            )
                            continue

                    # 다음 페이지 확인
                    total_count = data.get("total_count", 0)
                    if page_no * page_count >= total_count:
                        break

                    page_no += 1

            logger.info(
                f"보고서 동기화 완료: {company.stock_code} ({len(all_reports)}건)"
            )

            return all_reports

        except DartAPIError as e:
            logger.error(f"DART API 오류 (보고서 목록 조회): {e}")
            raise
        except Exception as e:
            logger.error(f"보고서 동기화 중 오류 발생: {e}")
            raise

    def get_reports(
        self,
        company: Company,
        report_type: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> Dict[str, Any]:
        """
        기업의 보고서 목록 조회 (페이지네이션)

        Args:
            company: Company 인스턴스
            report_type: 공시유형 필터 (사용 안 함, 모든 보고서 조회)
            page: 페이지 번호 (1부터 시작)
            size: 페이지 크기 (최대 100)

        Returns:
            {
                'total_count': 전체 개수,
                'page': 현재 페이지,
                'page_size': 페이지 크기,
                'reports': Report 인스턴스 리스트
            }
        """
        # 페이지 크기 제한
        size = min(size, 100)

        # 쿼리셋 필터링 (타입 필터링 제거 - 모든 보고서 조회)
        reports = Report.objects.filter(company=company).order_by("-submitted_at")

        # 디버깅: 쿼리 확인
        total_count = reports.count()
        logger.info(
            f"보고서 조회: company={company.stock_code} (pk={company.pk}), "
            f"전체 보고서 개수={total_count}"
        )

        # 쿼리 SQL 확인
        logger.debug(f"쿼리 SQL: {reports.query}")

        # 페이지네이션
        start = (page - 1) * size
        end = start + size
        reports = reports[start:end]

        return {
            "total_count": total_count,
            "page": page,
            "page_size": size,
            "reports": list(reports),
        }
