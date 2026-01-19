# industries/tasks/index_sync.py
import time
import logging
from celery import shared_task
from django.utils import timezone
from industries.models import Industry
from industries.services.kis_index_service import KISIndexService
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task
def sync_industry_charts_daily():
    """
    매일 4시 10분에 실행되는 산업 지수 차트 갱신 태스크
    최근 데이터를 가져와서 진행 중인 봉(3일, 주봉 등)을 업데이트합니다.
    """
    service = KISIndexService()
    industries = (
        Industry.objects.filter(is_deleted=False)
        .exclude(induty_code__isnull=True)
        .exclude(induty_code="")
    )

    now = timezone.now()
    end_date = now.strftime("%Y%m%d")
    start_date = (now - timedelta(days=10)).strftime("%Y%m%d")

    # '진행 중인 봉'의 오차를 없애기 위해 최근 15일치를 다시 계산하여 덮어씁니다.
    delete_from_date = now.date() - timedelta(days=15)

    updated_count = 0
    error_count = 0

    print(f"📅 {start_date} ~ {end_date} 구간 일일 갱신 시작")

    for industry in industries:
        try:
            clean_code = industry.induty_code.strip() if industry.induty_code else ""
            if not clean_code:
                logger.debug(f"건너뜀: {industry.name} - 업종코드가 없습니다.")
                continue

            print(f"📡 {industry.name}({industry.induty_code}) 데이터 요청 중...")
            raw_data = service.fetch_index_history(
                clean_code, start_date=start_date, end_date=end_date
            )

            if raw_data and len(raw_data) > 0:
                charts = service.get_industry_charts_1y(raw_data)
                service.save_charts_to_db(
                    industry, charts, delete_from_date=delete_from_date
                )
                updated_count += 1
                print(f"✅ {industry.name} 갱신 완료")
            else:
                # TPS 초과 등으로 빈 리스트가 온 경우
                error_count += 1
                print(f"⚠️ {industry.name}: 서버 응답은 왔으나 실제 데이터가 비어있음")

            # Rate limiting은 fetch_index_history 내부에서 처리되므로 추가 대기 불필요
            # 다만 에러 발생 시에는 짧은 대기로 다음 요청 준비

        except Exception as e:
            error_count += 1
            print(f"❌ {industry.name} 일일 갱신 실패: {str(e)}")
            # Rate limiting은 fetch_index_history 내부에서 처리되므로 추가 대기 불필요

    return f"일일 갱신 완료 - 성공: {updated_count}, 실패: {error_count}"


@shared_task
def backfill_industry_charts_task(industry_id=None):
    """관리자 API 호출 시 백그라운드에서 1년치 데이터를 적재하는 태스크"""
    logger.info(f"📊 산업 지수 백필 시작 (industry_id={industry_id})")
    service = KISIndexService()

    if industry_id:
        industries = Industry.objects.filter(pk=industry_id)
    else:
        industries = Industry.objects.filter(is_deleted=False).exclude(
            induty_code__isnull=True
        )

    total_count = industries.count()
    logger.info(f"📊 총 {total_count}개 산업 처리 예정")

    success_count = 0
    error_count = 0

    for idx, industry in enumerate(industries, 1):
        try:
            logger.info(
                f"📡 [{idx}/{total_count}] {industry.name}({industry.induty_code}) 처리 시작..."
            )
            # 1. 1년치 원재료 수집
            raw_data = service.fetch_1y_history_raw(industry.induty_code)
            logger.info(
                f"✅ [{idx}/{total_count}] {industry.name} 원본 데이터 수집 완료: {len(raw_data)}건"
            )

            # 2. 가공 (메서드 명칭 확인: get_industry_charts_1y)
            charts = service.get_industry_charts_1y(raw_data)
            logger.info(
                f"✅ [{idx}/{total_count}] {industry.name} 차트 데이터 가공 완료"
            )

            # 3. 4개 테이블 통합 저장 (백필은 전체 삭제 후 재삽입하지 않으므로 날짜 인자 제외 가능)
            service.save_charts_to_db(industry, charts)
            logger.info(f"✅ [{idx}/{total_count}] {industry.name} DB 저장 완료")
            success_count += 1
        except Exception as e:
            error_count += 1
            logger.error(
                f"❌ [{idx}/{total_count}] {industry.name} 백필 실패: {str(e)}",
                exc_info=True,
            )

    result_msg = f"{total_count}개 산업 데이터 적재 완료 - 성공: {success_count}, 실패: {error_count}"
    logger.info(f"📊 {result_msg}")
    return result_msg
