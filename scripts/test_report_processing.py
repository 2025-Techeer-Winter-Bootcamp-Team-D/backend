#!/usr/bin/env python
"""
보고서 처리 파이프라인 테스트 스크립트

각 단계별로 테스트할 수 있습니다:
1. 본문 추출 (OpenDartReader)
2. 본문 정제 (Gemini)
3. 정보 추출 (Gemini - 요약 + 매출구성)
4. 임베딩 생성 (Gemini)
5. OpenSearch 저장
6. 전체 파이프라인
"""

import argparse
import json
import logging
import os
import sys

# Django 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from companies.models import Company, Report, RevenueComposition
from companies.services.report_extractor import ReportExtractorService
from companies.services.report_info_extractor import ReportInfoExtractorService
from companies.services.report_opensearch import ReportOpenSearchService
from news.services.embedding import EmbeddingService
from news.services.refiner import RefineService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_extract(rcept_no: str):
    """1단계: 본문 추출 테스트"""
    print("\n" + "=" * 60)
    print("1단계: 본문 추출 테스트 (OpenDartReader)")
    print("=" * 60)

    extractor = ReportExtractorService()
    content = extractor.extract_content(rcept_no)

    if content:
        print(f"✅ 추출 성공: {len(content)}자")
        print(f"\n--- 본문 샘플 (처음 1000자) ---")
        print(content[:1000])
        print("--- 끝 ---\n")
        return content
    else:
        print("❌ 추출 실패")
        return None


def test_refine(raw_content: str):
    """2단계: 본문 정제 테스트"""
    print("\n" + "=" * 60)
    print("2단계: 본문 정제 테스트 (Gemini)")
    print("=" * 60)

    refiner = RefineService()
    refined = refiner.get_refined_body(raw_content)

    if refined and len(refined) > 100:
        print(f"✅ 정제 성공: {len(raw_content)}자 → {len(refined)}자")
        print(f"   압축률: {len(refined) / len(raw_content) * 100:.1f}%")
        print(f"\n--- 정제된 본문 샘플 (처음 1000자) ---")
        print(refined[:1000])
        print("--- 끝 ---\n")
        return refined
    else:
        print("❌ 정제 실패")
        return None


def test_extract_info(refined_content: str, report_name: str, company_name: str):
    """3단계: 정보 추출 테스트"""
    print("\n" + "=" * 60)
    print("3단계: 정보 추출 테스트 (Gemini - 요약 + 매출구성)")
    print("=" * 60)

    extractor = ReportInfoExtractorService()
    info = extractor.extract_info(refined_content, report_name, company_name)

    if info and "error" not in info:
        print("✅ 정보 추출 성공")
        print(f"\n--- 추출된 정보 ---")
        print(json.dumps(info, ensure_ascii=False, indent=2))
        print("--- 끝 ---\n")
        return info
    else:
        print(f"❌ 정보 추출 실패: {info.get('error', 'Unknown error')}")
        return None


def test_embedding(refined_content: str):
    """4단계: 임베딩 생성 테스트"""
    print("\n" + "=" * 60)
    print("4단계: 임베딩 생성 테스트 (Gemini)")
    print("=" * 60)

    embedding_service = EmbeddingService()
    embedding = embedding_service.create_embedding(refined_content)

    if embedding and len(embedding) == 768:
        print(f"✅ 임베딩 생성 성공: {len(embedding)}차원")
        print(f"   샘플값: [{embedding[0]:.6f}, {embedding[1]:.6f}, ..., {embedding[-1]:.6f}]")
        return embedding
    else:
        print(f"❌ 임베딩 생성 실패: {len(embedding) if embedding else 0}차원")
        return None


def test_opensearch(
    report_id: int,
    stock_code: str,
    company_name: str,
    report_name: str,
    report_type: str,
    content: str,
    summary: str,
    embedding: list,
):
    """5단계: OpenSearch 저장 테스트"""
    print("\n" + "=" * 60)
    print("5단계: OpenSearch 저장 테스트")
    print("=" * 60)

    opensearch = ReportOpenSearchService()

    # 저장
    success = opensearch.save_report_vector(
        report_id=report_id,
        company_stock_code=stock_code,
        company_name=company_name,
        report_name=report_name,
        report_type=report_type,
        content=content[:5000],
        summary=summary,
        content_vector=embedding,
    )

    if success:
        print("✅ OpenSearch 저장 성공")

        # 검색 테스트
        results = opensearch.search_similar_reports(embedding, size=3)
        print(f"\n--- 유사 보고서 검색 결과 ({len(results)}건) ---")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.get('score', 0):.4f}] {r.get('company_name')} - {r.get('report_name')}")
        print("--- 끝 ---\n")

        # 총 문서 수
        count = opensearch.get_report_count()
        print(f"📊 OpenSearch 총 보고서 수: {count}건")
        return True
    else:
        print("❌ OpenSearch 저장 실패")
        return False


def test_full_pipeline(report_id: int = None, rcept_no: str = None):
    """전체 파이프라인 테스트"""
    print("\n" + "=" * 60)
    print("전체 파이프라인 테스트")
    print("=" * 60)

    # 보고서 조회
    if report_id:
        report = Report.objects.select_related("company").get(id=report_id)
    elif rcept_no:
        report = Report.objects.select_related("company").get(rcept_no=rcept_no)
    else:
        # 최신 pending 보고서 가져오기
        report = (
            Report.objects.select_related("company")
            .filter(processing_status="pending")
            .order_by("-submitted_at")
            .first()
        )

    if not report:
        print("❌ 테스트할 보고서가 없습니다.")
        return

    print(f"\n📋 테스트 대상 보고서:")
    print(f"   ID: {report.id}")
    print(f"   접수번호: {report.rcept_no}")
    print(f"   보고서명: {report.report_name}")
    print(f"   기업: {report.company.company_name} ({report.company.stock_code})")
    print(f"   제출일: {report.submitted_at}")
    print(f"   처리상태: {report.processing_status}")

    # 1단계: 본문 추출
    raw_content = test_extract(report.rcept_no)
    if not raw_content:
        return

    # 2단계: 본문 정제
    refined_content = test_refine(raw_content)
    if not refined_content:
        return

    # 3단계: 정보 추출
    extracted_info = test_extract_info(
        refined_content, report.report_name, report.company.company_name
    )
    if not extracted_info:
        return

    # 4단계: 임베딩 생성
    embedding = test_embedding(refined_content)
    if not embedding:
        return

    # 5단계: OpenSearch 저장
    summary = extracted_info.get("summary", {}).get("one_line", "")
    success = test_opensearch(
        report_id=report.id,
        stock_code=report.company.stock_code,
        company_name=report.company.company_name,
        report_name=report.report_name,
        report_type=report.report_type,
        content=refined_content,
        summary=summary,
        embedding=embedding,
    )

    if success:
        print("\n" + "=" * 60)
        print("🎉 전체 파이프라인 테스트 완료!")
        print("=" * 60)

        # DB에 결과 저장 여부 확인
        save = input("\nDB에 결과를 저장하시겠습니까? (y/N): ").strip().lower()
        if save == "y":
            report.raw_content = raw_content
            report.refined_content = refined_content
            report.extracted_info = extracted_info
            report.embedding = embedding
            report.processing_status = "completed"
            report.processed_at = django.utils.timezone.now()
            report.save()
            print("✅ DB 저장 완료")

            # 매출 구성 저장
            revenue_composition = extracted_info.get("revenue_composition", [])
            if revenue_composition:
                fiscal_year = report.submitted_at.year
                for segment in revenue_composition:
                    # ratio가 문자열 ("58.1%")이면 숫자로 변환
                    ratio_value = segment.get("ratio")
                    if isinstance(ratio_value, str):
                        ratio_value = ratio_value.replace("%", "").strip()
                        try:
                            ratio_value = float(ratio_value)
                        except ValueError:
                            ratio_value = None
                    
                    RevenueComposition.objects.update_or_create(
                        company_id=report.company.stock_code,
                        fiscal_year=fiscal_year,
                        segment_name=segment.get("segment", ""),
                        defaults={
                            "revenue": segment.get("revenue", 0),
                            "ratio": ratio_value,
                        },
                    )
                print(f"✅ 매출 구성 {len(revenue_composition)}건 저장 완료")


def list_pending_reports(stock_code: str = None, limit: int = 10):
    """미처리 보고서 목록 조회"""
    print("\n" + "=" * 60)
    print("미처리 보고서 목록")
    print("=" * 60)

    queryset = Report.objects.select_related("company").filter(
        processing_status="pending"
    )
    if stock_code:
        queryset = queryset.filter(company_id=stock_code)

    reports = queryset.order_by("-submitted_at")[:limit]

    if not reports:
        print("미처리 보고서가 없습니다.")
        return

    print(f"\n{'ID':<8} {'접수번호':<16} {'기업명':<12} {'보고서명':<30} {'제출일'}")
    print("-" * 90)
    for r in reports:
        print(
            f"{r.id:<8} {r.rcept_no:<16} {r.company.company_name[:10]:<12} "
            f"{r.report_name[:28]:<30} {r.submitted_at}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="보고서 처리 파이프라인 테스트")
    parser.add_argument(
        "--step",
        type=int,
        choices=[1, 2, 3, 4, 5, 6],
        help="테스트할 단계 (1:추출, 2:정제, 3:정보추출, 4:임베딩, 5:OpenSearch, 6:전체)",
    )
    parser.add_argument("--rcept-no", type=str, help="보고서 접수번호")
    parser.add_argument("--report-id", type=int, help="보고서 ID")
    parser.add_argument("--stock-code", type=str, help="기업 종목코드")
    parser.add_argument("--list", action="store_true", help="미처리 보고서 목록 조회")

    args = parser.parse_args()

    if args.list:
        list_pending_reports(args.stock_code)
    elif args.step == 6 or (not args.step and (args.report_id or args.rcept_no)):
        test_full_pipeline(report_id=args.report_id, rcept_no=args.rcept_no)
    elif args.step == 1 and args.rcept_no:
        test_extract(args.rcept_no)
    else:
        print("사용법:")
        print("  미처리 보고서 목록: python test_report_processing.py --list")
        print("  전체 파이프라인:    python test_report_processing.py --report-id 123")
        print("  본문 추출만:        python test_report_processing.py --step 1 --rcept-no 20260107000715")
