#!/usr/bin/env python
"""
OpenDartReader 보고서 본문 추출 테스트 스크립트

DART 보고서 원문(XML)을 추출하고, 정제 필요성을 판단합니다.
"""
import os
import sys
import re

# Django 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings

try:
    import OpenDartReader
except ImportError:
    print("OpenDartReader가 설치되지 않았습니다.")
    print("설치: pip install opendartreader")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("BeautifulSoup이 설치되지 않았습니다.")
    print("설치: pip install beautifulsoup4 lxml")
    sys.exit(1)


def test_report_extraction(rcept_no: str = None):
    """
    보고서 본문 추출 테스트

    Args:
        rcept_no: 테스트할 보고서 접수번호 (없으면 DB에서 가져옴)
    """
    print("=" * 80)
    print("OpenDartReader 보고서 본문 추출 테스트")
    print("=" * 80)

    # DART API 키 확인
    api_key = settings.DART_API_KEY
    if not api_key:
        print("[오류] DART_API_KEY가 설정되지 않았습니다.")
        return

    dart = OpenDartReader(api_key)

    # 테스트할 보고서 접수번호
    if not rcept_no:
        # DB에서 가장 최근 보고서 가져오기
        from companies.models import Report

        report = Report.objects.order_by("-submitted_at").first()
        if report:
            rcept_no = report.rcept_no
            print(f"[DB에서 가져온 보고서]")
            print(f"  보고서명: {report.report_name}")
            print(f"  접수번호: {rcept_no}")
            print(f"  제출일: {report.submitted_at}")
        else:
            # 샘플 접수번호 사용 (삼성전자 2024년 사업보고서)
            rcept_no = "20240314000542"
            print(f"[샘플 접수번호 사용]: {rcept_no}")

    print("-" * 80)

    try:
        # 1. XML 원문 가져오기
        print(f"\n[1단계] XML 원문 가져오기...")
        xml_text = dart.document(rcept_no)

        if not xml_text:
            print("[오류] XML 가져오기 실패")
            return

        print(f"  XML 원문 길이: {len(xml_text)}자")

        # 2. XML 원문 샘플 출력 (처음 2000자)
        print(f"\n[2단계] XML 원문 샘플 (처음 2000자):")
        print("-" * 40)
        print(xml_text[:2000])
        print("-" * 40)

        # 3. BeautifulSoup으로 텍스트 추출
        print(f"\n[3단계] XML → 텍스트 변환...")
        soup = BeautifulSoup(xml_text, "lxml-xml")
        text = soup.get_text(separator="\n", strip=True)

        # 연속된 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        print(f"  추출된 텍스트 길이: {len(text)}자")
        print(f"  추출된 텍스트 줄 수: {len(text.splitlines())}줄")

        # 4. 추출된 텍스트 샘플 출력
        print(f"\n[4단계] 추출된 텍스트 샘플 (처음 3000자):")
        print("=" * 40)
        print(text[:3000])
        print("=" * 40)

        # 5. 불필요한 요소 분석
        print(f"\n[5단계] 불필요한 요소 분석:")
        print("-" * 40)

        # 분석 항목
        analysis = {
            "빈 줄 수": len([l for l in text.splitlines() if not l.strip()]),
            "총 줄 수": len(text.splitlines()),
            "숫자만 있는 줄": len(
                [l for l in text.splitlines() if l.strip().isdigit()]
            ),
            "한 글자 줄": len([l for l in text.splitlines() if len(l.strip()) == 1]),
            "10자 미만 줄": len(
                [l for l in text.splitlines() if 0 < len(l.strip()) < 10]
            ),
            "URL 포함 줄": len([l for l in text.splitlines() if "http" in l.lower()]),
            "특수문자만 줄": len(
                [
                    l
                    for l in text.splitlines()
                    if l.strip() and not any(c.isalnum() for c in l)
                ]
            ),
        }

        for key, value in analysis.items():
            ratio = (
                (value / analysis["총 줄 수"] * 100) if analysis["총 줄 수"] > 0 else 0
            )
            print(f"  {key}: {value} ({ratio:.1f}%)")

        # 6. 자주 등장하는 패턴 분석
        print(f"\n[6단계] 자주 등장하는 짧은 줄 (상위 20개):")
        print("-" * 40)

        short_lines = [l.strip() for l in text.splitlines() if 0 < len(l.strip()) < 30]
        from collections import Counter

        common_short = Counter(short_lines).most_common(20)

        for line, count in common_short:
            print(f"  [{count:3d}회] {line}")

        # 7. 정제 필요성 판단
        print(f"\n[7단계] 정제 필요성 판단:")
        print("=" * 40)

        noise_ratio = (
            (
                analysis["숫자만 있는 줄"]
                + analysis["한 글자 줄"]
                + analysis["특수문자만 줄"]
            )
            / analysis["총 줄 수"]
            * 100
            if analysis["총 줄 수"] > 0
            else 0
        )

        print(f"  노이즈 비율: {noise_ratio:.1f}%")

        if noise_ratio > 30:
            print(f"  → 정제 필요: 노이즈 비율이 높음 (30% 초과)")
            print(f"  → Gemini 정제 권장")
        elif noise_ratio > 15:
            print(f"  → 정제 권장: 노이즈 비율이 다소 높음 (15-30%)")
            print(f"  → 간단한 규칙 기반 정제 또는 Gemini 정제")
        else:
            print(f"  → 정제 불필요: 노이즈 비율이 낮음 (15% 미만)")
            print(f"  → 규칙 기반 정제로 충분")

        # 8. 전체 텍스트 파일 저장
        output_path = "/tmp/dart_report_raw.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\n[저장 완료] 전체 텍스트: {output_path}")

        # XML 원문도 저장
        xml_output_path = "/tmp/dart_report_raw.xml"
        with open(xml_output_path, "w", encoding="utf-8") as f:
            f.write(xml_text)
        print(f"[저장 완료] XML 원문: {xml_output_path}")

        print("\n" + "=" * 80)
        print("테스트 완료")
        print("=" * 80)

    except Exception as e:
        print(f"\n[오류 발생] {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="OpenDartReader 보고서 본문 추출 테스트"
    )
    parser.add_argument(
        "--rcept-no",
        type=str,
        default=None,
        help="테스트할 보고서 접수번호 (예: 20240314000542)",
    )

    args = parser.parse_args()
    test_report_extraction(rcept_no=args.rcept_no)
