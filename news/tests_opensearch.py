"""
OpenSearch 서비스 테스트 스크립트

이 스크립트는 OpenSearch 서비스가 제대로 작동하는지 테스트합니다.
Django shell에서 실행하거나 독립적으로 실행할 수 있습니다.

사용법:
    # Django shell에서
    python manage.py shell
    >>> exec(open('news/tests_opensearch.py').read())

    # 또는 직접 실행
    python manage.py shell < news/tests_opensearch.py
"""

import os
import django

# Django 설정 로드
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from news.services.opensearch import OpenSearchService
from news.services.embedding import EmbeddingService
from datetime import datetime
import random

print("=" * 60)
print("OpenSearch 서비스 테스트 시작")
print("=" * 60)

# 1. 서비스 초기화 테스트
print("\n[1단계] 서비스 초기화 테스트")
try:
    opensearch_service = OpenSearchService()
    embedding_service = EmbeddingService()
    print("✅ OpenSearchService 초기화 성공")
    print("✅ EmbeddingService 초기화 성공")
except Exception as e:
    print(f"❌ 초기화 실패: {str(e)}")
    exit(1)

# 2. 인덱스 존재 확인
print("\n[2단계] 인덱스 존재 확인")
try:
    exists = opensearch_service.client.indices.exists(
        index=opensearch_service.NEWS_INDEX_NAME
    )
    if exists:
        print(f"✅ 인덱스 '{opensearch_service.NEWS_INDEX_NAME}' 존재 확인")
    else:
        print(f"⚠️ 인덱스 '{opensearch_service.NEWS_INDEX_NAME}'가 없습니다.")
        print("   (자동 생성될 예정입니다)")
except Exception as e:
    print(f"❌ 인덱스 확인 실패: {str(e)}")

# 3. 테스트 데이터 준비
print("\n[3단계] 테스트 데이터 준비")
test_news = [
    {
        "news_id": 1001,
        "title": "삼성전자, AI 반도체 시장 공략 강화",
        "content": "삼성전자가 인공지능(AI) 반도체 시장 공략에 박차를 가하고 있다. 최근 AI 칩 개발에 집중 투자하며 글로벌 경쟁력을 높이고 있다.",
        "published_at": datetime(2024, 1, 15, 10, 0, 0),
    },
    {
        "news_id": 1002,
        "title": "SK하이닉스, 메모리 반도체 수주 증가",
        "content": "SK하이닉스가 최근 메모리 반도체 수주가 크게 증가했다고 발표했다. 데이터센터 수요 증가로 인한 것으로 분석된다.",
        "published_at": datetime(2024, 1, 16, 14, 30, 0),
    },
    {
        "news_id": 1003,
        "title": "네이버, AI 챗봇 서비스 출시",
        "content": "네이버가 새로운 AI 챗봇 서비스를 출시했다. 사용자들의 일상적인 질문에 답변하는 기능을 제공한다.",
        "published_at": datetime(2024, 1, 17, 9, 15, 0),
    },
]

print(f"✅ 테스트 뉴스 {len(test_news)}개 준비 완료")

# 4. 벡터 임베딩 생성
print("\n[4단계] 벡터 임베딩 생성")
try:
    contents = [news["content"] for news in test_news]
    embeddings = embedding_service.get_embeddings_batch(contents)

    if embeddings and len(embeddings) == len(test_news):
        print(f"✅ {len(embeddings)}개 벡터 생성 성공")
        print(f"   벡터 차원: {len(embeddings[0])} (예상: 768)")

        # 각 뉴스에 벡터 추가
        for i, news in enumerate(test_news):
            news["content_vector"] = embeddings[i]
    else:
        print(f"❌ 벡터 생성 실패: {len(embeddings) if embeddings else 0}개 생성됨")
        exit(1)
except Exception as e:
    print(f"❌ 벡터 생성 실패: {str(e)}")
    exit(1)

# 5. 단일 뉴스 저장 테스트
print("\n[5단계] 단일 뉴스 저장 테스트")
try:
    first_news = test_news[0]
    success = opensearch_service.save_news_vector(
        news_id=first_news["news_id"],
        title=first_news["title"],
        content=first_news["content"],
        content_vector=first_news["content_vector"],
        published_at=first_news["published_at"],
    )

    if success:
        print(f"✅ 뉴스 저장 성공: news_id={first_news['news_id']}")
    else:
        print(f"❌ 뉴스 저장 실패: news_id={first_news['news_id']}")
except Exception as e:
    print(f"❌ 저장 실패: {str(e)}")

# 6. 배치 저장 테스트
print("\n[6단계] 배치 저장 테스트")
try:
    # 나머지 뉴스들을 배치로 저장
    batch_docs = [
        {
            "news_id": news["news_id"],
            "title": news["title"],
            "content": news["content"],
            "content_vector": news["content_vector"],
            "published_at": news["published_at"],
        }
        for news in test_news[1:]  # 첫 번째는 이미 저장했으므로 제외
    ]

    success_count, failed_count = opensearch_service.save_news_vectors_batch(batch_docs)

    print(f"✅ 배치 저장 완료: 성공 {success_count}개, 실패 {failed_count}개")
except Exception as e:
    print(f"❌ 배치 저장 실패: {str(e)}")

# 7. 뉴스 조회 테스트
print("\n[7단계] 뉴스 조회 테스트")
try:
    retrieved_news = opensearch_service.get_news(test_news[0]["news_id"])

    if retrieved_news:
        print(f"✅ 뉴스 조회 성공: news_id={test_news[0]['news_id']}")
        print(f"   제목: {retrieved_news.get('title', 'N/A')}")
        print(f"   본문 길이: {len(retrieved_news.get('content', ''))}자")
        print(f"   벡터 차원: {len(retrieved_news.get('content_vector', []))}")
    else:
        print(f"❌ 뉴스 조회 실패: news_id={test_news[0]['news_id']}")
except Exception as e:
    print(f"❌ 조회 실패: {str(e)}")

# 8. 유사도 검색 테스트
print("\n[8단계] 유사도 검색 테스트")
try:
    # 첫 번째 뉴스와 유사한 뉴스 검색
    query_vector = test_news[0]["content_vector"]
    similar_news = opensearch_service.search_similar_news(
        query_vector=query_vector,
        size=5,
        min_score=0.5,
    )

    print(f"✅ 유사도 검색 완료: {len(similar_news)}개 결과")
    for i, result in enumerate(similar_news[:3], 1):  # 상위 3개만 출력
        print(f"   {i}. news_id={result['news_id']}, score={result['score']:.4f}")
        print(f"      제목: {result['title'][:50]}...")
except Exception as e:
    print(f"❌ 검색 실패: {str(e)}")

# 9. 삭제 테스트 (선택적)
print("\n[9단계] 삭제 테스트 (선택적)")
try:
    # 테스트용 뉴스 삭제
    test_news_id = test_news[0]["news_id"]
    success = opensearch_service.delete_news(test_news_id)

    if success:
        print(f"✅ 뉴스 삭제 성공: news_id={test_news_id}")

        # 삭제 확인
        deleted_news = opensearch_service.get_news(test_news_id)
        if deleted_news is None:
            print(f"✅ 삭제 확인 완료")
        else:
            print(f"⚠️ 삭제되었지만 여전히 조회됨 (refresh 지연 가능)")
    else:
        print(f"❌ 뉴스 삭제 실패: news_id={test_news_id}")
except Exception as e:
    print(f"❌ 삭제 실패: {str(e)}")

# 10. 인덱스 통계 확인
print("\n[10단계] 인덱스 통계 확인")
try:
    stats = opensearch_service.client.indices.stats(
        index=opensearch_service.NEWS_INDEX_NAME
    )
    doc_count = stats["indices"][opensearch_service.NEWS_INDEX_NAME]["total"]["docs"][
        "count"
    ]
    print(f"✅ 인덱스 문서 수: {doc_count}개")
except Exception as e:
    print(f"⚠️ 통계 확인 실패: {str(e)}")

print("\n" + "=" * 60)
print("OpenSearch 서비스 테스트 완료")
print("=" * 60)
