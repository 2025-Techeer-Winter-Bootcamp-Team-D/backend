#!/usr/bin/env python
"""
DART API 재무제표 응답 확인 스크립트
"""
import os
import sys
import django
import json

# Django 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from companies.services.dart_api import DartAPIClient, DartAPIError
from companies.models import Company


def test_dart_financial_statements():
    """DART API 재무제표 응답 확인"""
    try:
        client = DartAPIClient()

        # 삼성전자로 테스트
        company = Company.objects.filter(corp_code__isnull=False).first()
        if not company:
            print("corp_code가 있는 기업이 없습니다.")
            return

        print("=" * 80)
        print(
            f"DART API 재무제표 응답 구조 확인: {company.company_name} ({company.stock_code})"
        )
        print(f"corp_code: {company.corp_code}")
        print("=" * 80)

        # 2024년 사업보고서 조회
        year = "2024"
        report_code = "11011"

        print(f"\n[테스트] 사업연도: {year}, 보고서 코드: {report_code}")
        print("-" * 80)

        try:
            data = client.get_financial_statements(company.corp_code, year, report_code)

            # 전체 응답 출력
            print("\n[전체 응답 구조]")
            print(f"  status: {data.get('status')}")
            print(f"  message: {data.get('message')}")
            print(f"  list 개수: {len(data.get('list', []))}")

            # 계정과목 리스트 확인
            account_list = data.get("list", [])
            if account_list:
                print("\n[계정과목 샘플 (처음 10개)]")
                for i, account in enumerate(account_list[:10]):
                    print(f"\n  [{i+1}] 계정과목:")
                    print(f"    account_id: {account.get('account_id', 'N/A')}")
                    print(f"    account_nm: {account.get('account_nm', 'N/A')}")
                    print(f"    thstrm_amount: {account.get('thstrm_amount', 'N/A')}")
                    print(f"    frmtrm_amount: {account.get('frmtrm_amount', 'N/A')}")

                # 영업이익, 당기순이익 관련 계정과목 찾기
                print("\n[영업이익 관련 계정과목 검색]")
                operating_keywords = ["영업", "operating", "Operating"]
                for account in account_list:
                    account_id = account.get("account_id", "").lower()
                    account_nm = account.get("account_nm", "")
                    if any(
                        keyword.lower() in account_id.lower() or keyword in account_nm
                        for keyword in operating_keywords
                    ):
                        print(f"  account_id: {account.get('account_id')}")
                        print(f"  account_nm: {account.get('account_nm')}")
                        print(f"  thstrm_amount: {account.get('thstrm_amount')}")

                print("\n[당기순이익 관련 계정과목 검색]")
                profit_keywords = ["순이익", "profit", "Profit", "손익"]
                for account in account_list:
                    account_id = account.get("account_id", "").lower()
                    account_nm = account.get("account_nm", "")
                    if any(
                        keyword.lower() in account_id.lower() or keyword in account_nm
                        for keyword in profit_keywords
                    ):
                        print(f"  account_id: {account.get('account_id')}")
                        print(f"  account_nm: {account.get('account_nm')}")
                        print(f"  thstrm_amount: {account.get('thstrm_amount')}")

                # 모든 account_id 목록
                print("\n[모든 account_id 목록]")
                account_ids = set()
                for account in account_list:
                    account_id = account.get("account_id")
                    if account_id:
                        account_ids.add(account_id)
                for account_id in sorted(account_ids):
                    # 해당 account_id의 account_nm 찾기
                    for account in account_list:
                        if account.get("account_id") == account_id:
                            print(f"  {account_id}: {account.get('account_nm')}")
                            break
            else:
                print("  계정과목 리스트가 비어있습니다.")

            # 전체 응답 JSON 저장 (디버깅용)
            print("\n[전체 응답 JSON 저장: /tmp/dart_financial_response.json]")
            with open("/tmp/dart_financial_response.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("  저장 완료")

        except DartAPIError as e:
            print(f"  오류: {e}")

        print("\n" + "=" * 80)
        print("테스트 완료")
        print("=" * 80)

    except ValueError as e:
        print(f"DART_API_KEY가 설정되지 않았습니다: {e}")
        print("\n.env 파일에 DART_API_KEY를 설정해주세요.")
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_dart_financial_statements()
