#!/usr/bin/env python
"""
Jina.ai 본문 추출 테스트 스크립트

본문 추출한 전체 내용을 확인하기 위한 테스트 스크립트입니다.
"""
import os
import sys
import django
import argparse

# Django 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from news.services.jina_api import JinaReaderService
from news.models import News


def test_jina_extraction(url: str = None, check_duplicate: bool = True):
    """
    Jina.ai 본문 추출 테스트
    
    Args:
        url: 테스트할 뉴스 기사 URL (없으면 샘플 URL 사용)
        check_duplicate: DB 중복 체크 여부
    """
    try:
        # URL이 제공되지 않으면 샘플 URL 사용
        if not url:
            # 샘플 뉴스 URL (실제 테스트 시 변경 가능)
            url = "https://n.news.naver.com/mnews/article/001/0015000001"
            print(f"[알림] URL이 제공되지 않아 샘플 URL을 사용합니다: {url}")
            print(f"[알림] 다른 URL을 테스트하려면 --url 옵션을 사용하세요.\n")

        print("=" * 80)
        print(f"Jina.ai 본문 추출 테스트")
        print("=" * 80)
        print(f"\n[테스트 URL]")
        print(f"  {url}")
        print("-" * 80)

        # URL 유효성 검증
        if not url:
            print("[오류] URL이 제공되지 않았습니다.")
            return

        # DB 중복 체크 (옵션)
        if check_duplicate:
            if News.objects.filter(url=url).exists():
                print(f"\n[알림] 이미 저장된 기사입니다 (DB 중복).")
                existing_news = News.objects.filter(url=url).first()
                if existing_news:
                    print(f"  저장된 기사 ID: {existing_news.news_id}")
                    print(f"  저장된 기사 제목: {existing_news.title}")
                    print(f"  저장된 요약: {existing_news.summary[:200] if existing_news.summary else '(요약 없음)'}...")
                    print(f"\n[참고] 본문은 OpenSearch에 저장되어 있습니다. news_id={existing_news.news_id}")
                return

        # Jina.ai API로 본문 추출
        print(f"\n[본문 추출 시작]")
        print(f"  Jina.ai API 호출 중...")
        
        jina_service = JinaReaderService()
        raw_content = jina_service.extract_content(url)

        # 추출 결과 검증
        if not raw_content:
            print(f"\n[오류] 본문 추출 실패")
            print(f"  URL: {url}")
            return

        # 성공 시 전체 내용 출력
        print(f"\n[본문 추출 성공]")
        print("-" * 80)
        print(f"URL: {url}")
        print(f"본문 길이: {len(raw_content)}자")
        print(f"본문 길이 (줄 수): {len(raw_content.splitlines())}줄")
        print("-" * 80)
        
        print(f"\n[본문 전체 내용]")
        print("=" * 80)
        print(raw_content)
        print("=" * 80)
        
        print(f"\n[요약 정보]")
        print(f"  본문 길이: {len(raw_content)}자")
        print(f"  본문 길이 (줄 수): {len(raw_content.splitlines())}줄")
        print(f"  본문 시작 100자: {raw_content[:100]}...")
        print(f"  본문 끝 100자: ...{raw_content[-100:]}")

        print("\n" + "=" * 80)
        print("테스트 완료")
        print("=" * 80)

    except Exception as e:
        print(f"\n[오류 발생]")
        print(f"  {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jina.ai 본문 추출 테스트")
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="테스트할 뉴스 기사 URL"
    )
    parser.add_argument(
        "--no-check-duplicate",
        action="store_true",
        help="DB 중복 체크 건너뛰기"
    )
    
    args = parser.parse_args()
    
    test_jina_extraction(
        url=args.url,
        check_duplicate=not args.no_check_duplicate
    )
