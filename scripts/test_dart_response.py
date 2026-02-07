#!/usr/bin/env python
"""
DART API 실제 응답 확인 스크립트
"""
import os
import sys
import django

# Django 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from companies.services.dart_api import DartAPIClient, DartAPIError
import json


def test_dart_company_info():
    """DART API company.json 응답 확인"""
    try:
        client = DartAPIClient()

        # 삼성전자 corp_code (예시)
        # 실제로는 sync_corp_codes 명령어로 가져온 corp_code를 사용해야 함
        test_corp_codes = [
            "00126380",  # 삼성전자 (예상)
            # 다른 기업들도 테스트 가능
        ]

        print("=" * 80)
        print("DART API company.json 응답 구조 확인")
        print("=" * 80)

        for corp_code in test_corp_codes:
            try:
                print(f"\n[테스트] corp_code: {corp_code}")
                print("-" * 80)

                data = client.get_company_info(corp_code)

                # 전체 응답 출력
                print("\n[전체 응답]")
                print(json.dumps(data, indent=2, ensure_ascii=False))

                # 업종코드 관련 필드 확인
                print("\n[업종코드 관련 필드]")
                print(f"  induty_code: {data.get('induty_code', '없음')}")
                print(f"  cls_code: {data.get('cls_code', '없음')}")
                print(
                    f"  업종코드 존재 여부: {bool(data.get('induty_code') or data.get('cls_code'))}"
                )

                # 모든 필드명 출력
                print("\n[응답 필드 목록]")
                for key in sorted(data.keys()):
                    value = data[key]
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:50] + "..."
                    print(f"  {key}: {value}")

            except DartAPIError as e:
                print(f"  오류: {e}")
                continue
            except Exception as e:
                print(f"  예상치 못한 오류: {e}")
                continue

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
    test_dart_company_info()
