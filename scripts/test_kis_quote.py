#!/usr/bin/env python
"""
KIS API 시세 응답 구조 확인 스크립트
실제 응답 구조를 확인하여 시가총액 매핑이 올바른지 검증
"""
import os
import sys
import django
import json

# Django 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Redis 연결 오류 무시 (테스트용)
# KIS API 클라이언트가 캐시 연결 오류를 처리하도록 수정되었으므로
# 여기서는 추가 설정 불필요 (캐시 오류 시 자동으로 fallback)

django.setup()

from companies.services.kis_quote import KISQuoteClient
from companies.models import Company


def test_kis_quote_response():
    """KIS API 시세 응답 구조 확인"""
    try:
        client = KISQuoteClient()

        # 삼성전자로 테스트
        stock_code = "005930"
        company = Company.objects.filter(stock_code=stock_code).first()
        if not company:
            print(f"기업이 없습니다: {stock_code}")
            return

        print("=" * 80)
        print(f"KIS API 시세 응답 구조 확인: {company.company_name} ({stock_code})")
        print("=" * 80)

        # 시세 조회
        quote = client.get_stock_quote(stock_code)
        if not quote:
            print("시세 조회 실패")
            return

        print("\n[전체 응답 구조]")
        print(f"응답 타입: {type(quote)}")
        print(f"응답 키 개수: {len(quote)}")
        print(f"응답 키 목록: {list(quote.keys())}")

        print("\n[전체 응답 내용]")
        print(json.dumps(quote, indent=2, ensure_ascii=False))

        # 시가총액 관련 필드 확인
        print("\n[시가총액 관련 필드]")
        market_cap_fields = [
            "hts_avls",
            "avls",  # 대체 필드 가능성
            "market_cap",
            "market_amount",
            "시가총액",
        ]

        for field in market_cap_fields:
            if field in quote:
                value = quote[field]
                print(f"  {field}: {value} (타입: {type(value).__name__})")

        # hts_avls 필드 상세 확인
        if "hts_avls" in quote:
            hts_avls = quote["hts_avls"]
            print("\n[hts_avls 상세 분석]")
            print(f"  원본 값: {hts_avls}")
            print(f"  타입: {type(hts_avls).__name__}")
            print(f"  문자열 변환: {str(hts_avls)}")

            # 콤마 제거 후 변환
            try:
                hts_avls_clean = str(hts_avls).replace(",", "").strip()
                print(f"  콤마 제거 후: {hts_avls_clean}")

                if hts_avls_clean:
                    value_int = int(hts_avls_clean)
                    print(f"  정수 변환: {value_int:,}")

                    # 억 단위 → 원 단위 변환
                    market_amount = value_int * 100_000_000
                    print(f"  원 단위 변환: {market_amount:,}원")
                    print(f"  억 단위: {value_int:,}억원")
            except (ValueError, TypeError) as e:
                print(f"  변환 실패: {e}")

        # 현재 코드로 시가총액 조회
        print("\n[현재 코드로 시가총액 조회]")
        market_amount = client.get_market_amount(stock_code)
        if market_amount:
            print(f"  시가총액: {market_amount:,}원")
            print(f"  억 단위: {market_amount / 100_000_000:,.0f}억원")
        else:
            print("  시가총액 조회 실패")

        # DB에 저장된 시가총액과 비교
        print("\n[DB 저장값과 비교]")
        if company.market_amount:
            print(f"  DB 저장값: {company.market_amount:,}원")
            print(f"  DB 억 단위: {company.market_amount / 100_000_000:,.0f}억원")

            if market_amount:
                diff = abs(market_amount - company.market_amount)
                diff_percent = (
                    (diff / company.market_amount * 100)
                    if company.market_amount > 0
                    else 0
                )
                print(f"  차이: {diff:,}원 ({diff_percent:.2f}%)")

                if diff_percent < 1:
                    print("  ✅ 일치 (오차 1% 미만)")
                elif diff_percent < 5:
                    print("  ⚠️  차이 있음 (오차 5% 미만)")
                else:
                    print("  ❌ 큰 차이 (오차 5% 이상)")
        else:
            print("  DB 저장값 없음")

        # 전체 응답 JSON 저장 (디버깅용)
        print("\n[전체 응답 JSON 저장: /tmp/kis_quote_response.json]")
        with open("/tmp/kis_quote_response.json", "w", encoding="utf-8") as f:
            json.dump(quote, f, indent=2, ensure_ascii=False)
        print("  저장 완료")

        print("\n" + "=" * 80)
        print("테스트 완료")
        print("=" * 80)

    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_kis_quote_response()
