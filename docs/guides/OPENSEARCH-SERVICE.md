# OpenSearch Service 가이드

## 개요

`news/services/opensearch.py`는 뉴스 본문의 벡터 임베딩을 OpenSearch에 저장하고 검색하는 서비스를 제공합니다. Gemini의 `text-multilingual-embedding-002` 모델을 사용하여 생성된 768차원 벡터를 저장하고, 코사인 유사도 기반의 k-NN 검색을 지원합니다.

## 주요 기능

- **인덱스 생성 및 관리**: OpenSearch 인덱스 자동 생성 및 벡터 검색 최적화
- **벡터 저장**: 단일 또는 배치 방식으로 뉴스 벡터 저장
- **유사도 검색**: 벡터 기반 k-NN 검색으로 유사한 뉴스 검색
- **CRUD 작업**: 뉴스 조회, 삭제 기능 제공

## 클래스 구조

### OpenSearchService

뉴스 벡터 저장 및 검색을 위한 메인 서비스 클래스입니다.

#### 클래스 속성

```python
NEWS_INDEX_NAME = "news_vectors"  # 뉴스 인덱스 이름
VECTOR_DIMENSION = 768            # 벡터 차원 (Gemini embedding)
```

## 메서드 상세 설명

### 1. 초기화 메서드

#### `__init__(self)`

OpenSearch 클라이언트를 초기화하고 인덱스를 생성합니다.

**동작 과정:**
1. `settings.py`에서 OpenSearch 설정 로드
2. 호스트 주소 파싱 (`host:port` 형식)
3. OpenSearch 클라이언트 생성
4. 인덱스 존재 여부 확인 및 생성

**설정 값:**
- `OPENSEARCH_HOST`: OpenSearch 호스트 주소
- `OPENSEARCH_USE_SSL`: SSL 사용 여부
- `OPENSEARCH_VERIFY_CERTS`: 인증서 검증 여부

**예시:**
```python
from news.services.opensearch import OpenSearchService

# 서비스 인스턴스 생성 (자동으로 인덱스 생성)
opensearch_service = OpenSearchService()
```

### 2. 인덱스 관리

#### `_ensure_index_exists(self)` (Private)

인덱스가 존재하는지 확인하고, 없으면 생성합니다.

**인덱스 매핑 구조:**

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `news_id` | long | PostgreSQL의 뉴스 ID (Primary Key) |
| `title` | text | 뉴스 제목 (검색용) |
| `content` | text | 뉴스 본문 텍스트 |
| `content_vector` | knn_vector | 768차원 벡터 임베딩 |
| `published_at` | date | 발행일 |

**벡터 검색 설정:**
- **알고리즘**: HNSW (Hierarchical Navigable Small World)
- **유사도 측정**: 코사인 유사도 (cosinesimil)
- **검색 엔진**: nmslib
- **파라미터**:
  - `ef_construction`: 128 (인덱스 생성 시 정확도)
  - `m`: 24 (각 노드의 최대 연결 수)
  - `ef_search`: 100 (검색 시 성능)

### 3. 벡터 저장

#### `save_news_vector(self, news_id, title, content, content_vector, published_at=None)`

단일 뉴스의 벡터를 OpenSearch에 저장합니다.

**매개변수:**
- `news_id` (int): PostgreSQL의 뉴스 ID
- `title` (str): 뉴스 제목
- `content` (str): 뉴스 본문 텍스트
- `content_vector` (list): 768차원 벡터 리스트
- `published_at` (datetime, optional): 발행일

**반환값:**
- `bool`: 저장 성공 시 `True`, 실패 시 `False`

**검증:**
- 벡터 차원이 768이 아니면 `False` 반환
- 벡터가 `None`이면 `False` 반환

**예시:**
```python
success = opensearch_service.save_news_vector(
    news_id=12345,
    title="삼성전자, AI 반도체 개발 가속화",
    content="삼성전자가 차세대 AI 반도체...",
    content_vector=[0.123, -0.456, ...],  # 768개 요소
    published_at=datetime(2025, 1, 13)
)
```

#### `save_news_vectors_batch(self, news_documents)`

여러 뉴스 벡터를 배치로 저장합니다. 대량의 뉴스를 효율적으로 저장할 때 사용합니다.

**매개변수:**
- `news_documents` (list): 뉴스 문서 리스트. 각 항목은 다음 키를 포함:
  ```python
  {
      "news_id": 12345,
      "title": "뉴스 제목",
      "content": "뉴스 본문",
      "content_vector": [0.1, 0.2, ...],  # 768차원
      "published_at": datetime(2025, 1, 13)  # 선택적
  }
  ```

**반환값:**
- `tuple`: (성공 개수, 실패 개수)

**특징:**
- OpenSearch Bulk API 사용으로 높은 처리량
- 벡터 차원 검증 후 유효한 문서만 저장
- 스트리밍 방식으로 메모리 효율적

**예시:**
```python
news_docs = [
    {
        "news_id": 1,
        "title": "뉴스 1",
        "content": "내용 1",
        "content_vector": [...]
    },
    {
        "news_id": 2,
        "title": "뉴스 2",
        "content": "내용 2",
        "content_vector": [...]
    }
]

success_count, failed_count = opensearch_service.save_news_vectors_batch(news_docs)
print(f"성공: {success_count}, 실패: {failed_count}")
```

### 4. 유사도 검색

#### `search_similar_news(self, query_vector, size=10, min_score=None, published_after=None)`

벡터 유사도 기반으로 유사한 뉴스를 검색합니다.

**매개변수:**
- `query_vector` (list): 검색 쿼리 벡터 (768차원)
- `size` (int, optional): 반환할 결과 개수 (기본값: 10)
- `min_score` (float, optional): 최소 유사도 점수 필터
- `published_after` (datetime, optional): 이 날짜 이후 뉴스만 검색

**반환값:**
- `list`: 검색 결과 리스트. 각 항목 구조:
  ```python
  {
      "news_id": 12345,
      "title": "뉴스 제목",
      "content": "뉴스 본문",
      "score": 0.95,  # 유사도 점수 (높을수록 유사)
      "published_at": "2025-01-13T10:00:00"
  }
  ```

**검색 알고리즘:**
- k-NN (k-Nearest Neighbors) 검색 사용
- 코사인 유사도로 벡터 간 거리 계산
- HNSW 인덱스로 빠른 근사 검색

**예시:**
```python
# 사용자 쿼리를 벡터로 변환 (Gemini API 사용)
query_vector = gemini_service.create_embedding("AI 반도체 기술")

# 유사한 뉴스 검색
results = opensearch_service.search_similar_news(
    query_vector=query_vector,
    size=5,
    min_score=0.7,  # 유사도 0.7 이상만 반환
    published_after=datetime(2025, 1, 1)  # 2025년 이후 뉴스만
)

for news in results:
    print(f"{news['title']} (유사도: {news['score']:.2f})")
```

### 5. 뉴스 관리

#### `delete_news(self, news_id)`

OpenSearch에서 뉴스를 삭제합니다.

**매개변수:**
- `news_id` (int): 삭제할 뉴스 ID

**반환값:**
- `bool`: 삭제 성공 시 `True`, 실패 시 `False`

**예시:**
```python
success = opensearch_service.delete_news(news_id=12345)
```

#### `get_news(self, news_id)`

OpenSearch에서 특정 뉴스를 조회합니다.

**매개변수:**
- `news_id` (int): 조회할 뉴스 ID

**반환값:**
- `dict`: 뉴스 문서 (없으면 `None`)

**예시:**
```python
news = opensearch_service.get_news(news_id=12345)
if news:
    print(f"제목: {news['title']}")
    print(f"벡터 차원: {len(news['content_vector'])}")
```

## 사용 시나리오

### 시나리오 1: 뉴스 수집 후 벡터 저장

```python
from news.services.opensearch import OpenSearchService
from news.services.gemini import GeminiService

# 서비스 초기화
opensearch_service = OpenSearchService()
gemini_service = GeminiService()

# 뉴스 데이터
news_data = {
    "id": 12345,
    "title": "삼성전자, AI 반도체 개발 가속화",
    "content": "삼성전자가 차세대 AI 반도체 개발을 가속화하고 있다...",
    "published_at": datetime.now()
}

# 벡터 임베딩 생성
vector = gemini_service.create_embedding(news_data["content"])

# OpenSearch에 저장
success = opensearch_service.save_news_vector(
    news_id=news_data["id"],
    title=news_data["title"],
    content=news_data["content"],
    content_vector=vector,
    published_at=news_data["published_at"]
)
```

### 시나리오 2: 대량 뉴스 배치 저장

```python
# 수집된 뉴스 목록
news_list = [...]  # PostgreSQL에서 조회

# 벡터 임베딩 생성
news_documents = []
for news in news_list:
    vector = gemini_service.create_embedding(news.content)
    news_documents.append({
        "news_id": news.id,
        "title": news.title,
        "content": news.content,
        "content_vector": vector,
        "published_at": news.published_at
    })

# 배치 저장
success_count, failed_count = opensearch_service.save_news_vectors_batch(news_documents)
```

### 시나리오 3: 유사 뉴스 추천

```python
# 사용자가 읽고 있는 뉴스
current_news = opensearch_service.get_news(news_id=12345)

# 유사한 뉴스 검색
similar_news = opensearch_service.search_similar_news(
    query_vector=current_news["content_vector"],
    size=5,
    min_score=0.8
)

# 추천 뉴스 반환
recommendations = [news["news_id"] for news in similar_news]
```

### 시나리오 4: 키워드 기반 뉴스 검색

```python
# 사용자 검색 쿼리
user_query = "AI 반도체 기술 동향"

# 쿼리를 벡터로 변환
query_vector = gemini_service.create_embedding(user_query)

# 최근 1주일 뉴스에서 검색
from datetime import datetime, timedelta

results = opensearch_service.search_similar_news(
    query_vector=query_vector,
    size=10,
    min_score=0.7,
    published_after=datetime.now() - timedelta(days=7)
)
```

## 성능 최적화

### 인덱스 최적화

- **ef_construction**: 인덱스 생성 시 정확도 (기본값: 128)
  - 높을수록 정확하지만 생성 시간 증가
- **m**: 각 노드의 최대 연결 수 (기본값: 24)
  - 높을수록 검색 정확도 증가, 메모리 사용량 증가
- **ef_search**: 검색 시 탐색할 노드 수 (기본값: 100)
  - 높을수록 정확하지만 검색 속도 감소

### 배치 처리

- 대량 데이터는 `save_news_vectors_batch()` 사용 권장
- Bulk API로 네트워크 오버헤드 감소
- 스트리밍 방식으로 메모리 효율적 처리

### 검색 최적화

- `min_score` 필터로 저품질 결과 제거
- `size` 값을 적절히 조정하여 불필요한 데이터 전송 방지
- `published_after` 필터로 검색 범위 제한

## 주의사항

### 벡터 차원

- 반드시 768차원 벡터 사용 (Gemini text-multilingual-embedding-002)
- 다른 임베딩 모델 사용 시 `VECTOR_DIMENSION` 수정 필요
- 차원 불일치 시 저장 실패

### 인덱스 재생성

인덱스 매핑 변경 시 인덱스 재생성이 필요합니다:

```python
# 1. 기존 인덱스 삭제 (주의: 모든 데이터 삭제됨)
client = OpenSearchService().client
client.indices.delete(index="news_vectors")

# 2. 서비스 재초기화 (새 인덱스 생성)
opensearch_service = OpenSearchService()

# 3. 데이터 재색인
# PostgreSQL에서 뉴스 조회 후 벡터 재생성 및 저장
```

### 에러 처리

- 모든 메서드는 예외 발생 시 로깅 후 기본값 반환
- 저장/삭제 실패 시 `False` 반환
- 검색 실패 시 빈 리스트 `[]` 반환
- 조회 실패 시 `None` 반환

### 동시성

- OpenSearch 클라이언트는 thread-safe
- 여러 요청이 동시에 발생해도 안전
- 배치 작업 시 적절한 chunk size 조절 권장

## 로깅

서비스는 Python 표준 로깅 모듈을 사용합니다:

```python
import logging

# 로그 레벨 설정
logging.basicConfig(level=logging.INFO)

# 디버그 모드
logging.basicConfig(level=logging.DEBUG)
```

**로그 레벨별 메시지:**
- `DEBUG`: 개별 작업 성공/실패 상세 정보
- `INFO`: 인덱스 생성, 배치 작업 결과
- `WARNING`: 예상치 못한 응답, 유효하지 않은 데이터
- `ERROR`: 작업 실패, 예외 발생

## 트러블슈팅

### 1. 인덱스 생성 실패

**증상:** `Failed to create index` 에러

**해결 방법:**
- OpenSearch 서비스가 실행 중인지 확인
- 연결 설정 확인 (`settings.OPENSEARCH_HOST`)
- 권한 확인 (보안 플러그인 활성화 시)

### 2. 벡터 저장 실패

**증상:** `save_news_vector()` 반환값 `False`

**원인:**
- 벡터 차원 불일치 (768차원 아님)
- 벡터가 `None` 또는 빈 리스트
- OpenSearch 연결 끊김

**해결 방법:**
```python
# 벡터 차원 확인
if len(content_vector) != 768:
    print(f"잘못된 벡터 차원: {len(content_vector)}")
```

### 3. 검색 결과 없음

**증상:** `search_similar_news()` 반환값 빈 리스트

**원인:**
- 인덱스에 데이터 없음
- `min_score` 임계값이 너무 높음
- `published_after` 필터가 너무 제한적

**해결 방법:**
```python
# 필터 없이 검색
results = opensearch_service.search_similar_news(
    query_vector=query_vector,
    size=10
    # min_score와 published_after 제거
)

# 인덱스 데이터 확인
news = opensearch_service.get_news(news_id=1)
if not news:
    print("인덱스에 데이터 없음")
```

## 참고 자료

- [OpenSearch 공식 문서](https://opensearch.org/docs/latest/)
- [k-NN 플러그인 가이드](https://opensearch.org/docs/latest/search-plugins/knn/index/)
- [Gemini API 문서](https://ai.google.dev/docs)
- [HNSW 알고리즘](https://arxiv.org/abs/1603.09320)

## 관련 파일

- `config/settings.py`: OpenSearch 연결 설정
- `news/services/gemini.py`: 벡터 임베딩 생성 서비스
- `news/models.py`: 뉴스 모델 정의
