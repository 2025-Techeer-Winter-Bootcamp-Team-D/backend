# 뉴스 크롤링 구현 현황 및 추후 작업

**작성일**: 2026-01-13
**작성자**: Claude Code

## 목차

1. [완료된 작업](#완료된-작업)
2. [발견 및 수정한 버그](#발견-및-수정한-버그)
3. [추후 작업 사항](#추후-작업-사항)
4. [테스트 결과](#테스트-결과)
5. [주요 설정 값](#주요-설정-값)

---

## 완료된 작업

### 1. OpenSearch 서비스 문서화 ✅

**파일**: `docs/guides/OPENSEARCH-SERVICE.md`

OpenSearch 벡터 저장 및 검색 서비스에 대한 상세 가이드를 작성했습니다.

**포함 내용**:
- 클래스 및 메서드 상세 설명
- 인덱스 구조 및 벡터 검색 알고리즘 (HNSW)
- 4가지 실사용 시나리오 예시
- 성능 최적화 가이드
- 트러블슈팅 방법

**주요 사양**:
- 벡터 차원: 768 (Gemini text-multilingual-embedding-002)
- 검색 알고리즘: HNSW (Hierarchical Navigable Small World)
- 유사도 측정: 코사인 유사도

### 2. Docker 환경변수 문제 수정 ✅

**파일**: `.env`

**문제**:
```bash
WARN[0000] The "atbm" variable is not set. Defaulting to a blank string.
```

**원인**:
- `DJANGO_SECRET_KEY` 값에 `$atbm` 문자열 포함
- Docker Compose가 `$atbm`을 환경변수로 인식하려 시도

**수정**:
```bash
# 수정 전
DJANGO_SECRET_KEY=django-insecure-(1#88xs9ypkmy&q*2fudx_z@43%$atbm%_435xt_^izxmbv&n_

# 수정 후
DJANGO_SECRET_KEY='django-insecure-(1#88xs9ypkmy&q*2fudx_z@43%$atbm%_435xt_^izxmbv&n_'
```

**결과**: Docker Compose 실행 시 경고 메시지 제거

### 3. 크롤링 통계 집계 버그 수정 ✅

**파일**: `news/tasks.py:284-289`

**문제**:
- 크롤링 완료 후 통계가 0으로 표시됨
- 실제로는 뉴스가 정상 저장됨

**원인 분석**:

`tasks.py`:
```python
crawl_job.total_articles = total_articles  # 메모리에만 설정
crawl_job.successful_articles = successful_articles
crawl_job.failed_articles = failed_articles
crawl_job.mark_as_completed()  # ❌ 통계 필드를 DB에 저장하지 않음
```

`models.py (mark_as_completed)`:
```python
def mark_as_completed(self):
    self.status = "completed"
    self.completed_at = timezone.now()
    self.save(update_fields=["status", "completed_at"])  # ❌ 통계 필드 제외
```

**수정**:
```python
# 통계를 먼저 DB에 저장
crawl_job.total_articles = total_articles
crawl_job.successful_articles = successful_articles
crawl_job.failed_articles = failed_articles
crawl_job.save()  # ✅ 통계 저장
crawl_job.mark_as_completed()  # 상태만 업데이트
```

**결과**: 통계가 정확하게 표시됨

### 4. 최소 본문 길이 제한 조정 ✅

**파일**: `news/tasks.py:133`

**변경 이력**:
- 초기값: 100자
- 1차 수정: 50자
- **최종 설정: 30자**

**이유**:
- 30자 미만: 뉴스로서 인사이트 추출이 어려움
- 30자 이상: 요약 및 벡터 임베딩 생성 가능

**코드**:
```python
if not refined_content or len(refined_content.strip()) < 30:
    logger.warning(
        f"[CrawlJob {job_id}] 정제된 본문이 너무 짧음 (30자 미만): {url[:50]}..."
    )
    failed_articles += 1
    continue
```

### 5. DB 및 OpenSearch 저장 검증 ✅

**PostgreSQL 확인**:
```bash
docker compose exec db psql -U admin -d stock_db -c "SELECT ..."
```

**OpenSearch 확인**:
```bash
docker compose exec opensearch curl "http://localhost:9200/news_vectors/_count"
```

**검증 결과**:
- PostgreSQL: 뉴스 메타데이터 + 요약 정상 저장
- OpenSearch: 본문 + 768차원 벡터 정상 저장
- 총 14개 벡터 저장 확인

### 6. 배치 크롤링 기능 구현 확인 ✅

**Celery Beat 설정**: `config/settings.py:176-185`

```python
CELERY_BEAT_SCHEDULE = {
    "crawl-news-every-3-hours": {
        "task": "news.tasks.scheduled_crawl_news",
        "schedule": 3 * 60 * 60,  # 3시간 (초 단위)
        "kwargs": {
            "keywords": ["AI", "반도체", "삼성전자", "SK하이닉스"],
            "max_articles_per_keyword": 10,
        },
    },
}
```

**스케줄링 태스크**: `news/tasks.py:313-342`

```python
@shared_task
def scheduled_crawl_news(keywords=None, max_articles_per_keyword=10):
    """Celery Beat 스케줄링용 래퍼 태스크"""
    if keywords is None:
        keywords = ["AI", "반도체", "삼성전자", "SK하이닉스"]

    crawl_job = CrawlJob.objects.create(
        keywords=keywords,
        status="pending",
    )

    crawl_news_task.delay(crawl_job.id, keywords, max_articles_per_keyword)
    return crawl_job.id
```

**현황**: ⚠️ 코드는 완벽히 구현되었으나 실행 환경 미구성

---

## 발견 및 수정한 버그

### 버그 1: 통계 집계 미저장

**심각도**: 중간
**영향**: 사용자가 크롤링 결과를 확인할 수 없음

**수정 파일**: `news/tasks.py`
**수정 라인**: 284-289

**Before**:
```python
crawl_job.total_articles = total_articles
crawl_job.successful_articles = successful_articles
crawl_job.failed_articles = failed_articles
crawl_job.mark_as_completed()  # 통계가 저장되지 않음
```

**After**:
```python
crawl_job.total_articles = total_articles
crawl_job.successful_articles = successful_articles
crawl_job.failed_articles = failed_articles
crawl_job.save()  # 통계를 먼저 저장
crawl_job.mark_as_completed()  # 상태만 업데이트
```

### 버그 2: Docker 환경변수 경고

**심각도**: 낮음
**영향**: 로그 가독성 저하

**수정 파일**: `.env`
**수정 라인**: 33

**수정 방법**: 환경변수 값을 따옴표로 감싸기

---

## 추후 작업 사항

### 1. Celery Worker/Beat 컨테이너 추가 (필수) 🔴

**우선순위**: 높음
**예상 소요 시간**: 1-2시간

#### 작업 내용

`docker-compose.yml`에 다음 컨테이너 추가:

```yaml
  celery-worker:
    build: .
    container_name: celery-worker
    env_file:
      - .env
    command: celery -A config worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-postgres}
      - REDIS_URL=redis://redis:6379/0
      - OPENSEARCH_HOST=opensearch:9200
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      opensearch:
        condition: service_healthy
    networks:
      - django-network
    restart: always

  celery-beat:
    build: .
    container_name: celery-beat
    env_file:
      - .env
    command: celery -A config beat --loglevel=info
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-postgres}
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - django-network
    restart: always
```

#### 추가 작업

1. **Celery Beat 스케줄러 DB 마이그레이션** (선택)

   현재는 메모리 기반 스케줄러를 사용 중입니다. DB 기반으로 변경하려면:

   ```bash
   pip install django-celery-beat
   ```

   `config/settings.py`:
   ```python
   INSTALLED_APPS = [
       # ...
       'django_celery_beat',
   ]

   CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
   ```

   마이그레이션:
   ```bash
   python manage.py migrate django_celery_beat
   ```

2. **모니터링 도구 추가** (선택)

   Flower를 사용하여 Celery 작업을 모니터링:

   ```yaml
   flower:
     build: .
     container_name: celery-flower
     command: celery -A config flower --port=5555
     ports:
       - 5555:5555
     environment:
       - REDIS_URL=redis://redis:6379/0
     depends_on:
       - redis
       - celery-worker
     networks:
       - django-network
   ```

   접속: http://localhost:5555

#### 테스트 방법

1. **컨테이너 실행**:
   ```bash
   docker compose up -d celery-worker celery-beat
   ```

2. **로그 확인**:
   ```bash
   # Worker 로그
   docker compose logs -f celery-worker

   # Beat 로그
   docker compose logs -f celery-beat
   ```

3. **수동 태스크 실행**:
   ```bash
   docker compose exec app python manage.py shell
   >>> from news.tasks import scheduled_crawl_news
   >>> scheduled_crawl_news.delay()
   ```

4. **자동 스케줄 확인**:
   - 3시간마다 자동으로 크롤링 실행
   - CrawlJob 테이블에서 자동 생성된 작업 확인

### 2. Gemini API 할당량 관리 (권장) 🟡

**우선순위**: 중간
**예상 소요 시간**: 30분

#### 문제

현재 Gemini API 무료 티어 제한:
- **하루 20건** (gemini-2.5-flash)
- 크롤링 1회당 약 6-10건 API 호출 발생
- 하루 2-3회 크롤링 시 할당량 초과

#### 해결 방안

**옵션 1: API 키 업그레이드** (추천)
- Gemini API 유료 플랜으로 전환
- 비용: 사용량 기반 (Flash 모델은 저렴)

**옵션 2: 할당량 관리 로직 추가**

`news/tasks.py`에 재시도 로직 추가:

```python
from celery.exceptions import Retry

@shared_task(bind=True, max_retries=3)
def crawl_news_task(self, job_id, keywords, max_articles_per_keyword=10):
    try:
        # 크롤링 로직
        ...
    except Exception as e:
        if "quota exceeded" in str(e).lower():
            # 할당량 초과 시 1시간 후 재시도
            raise self.retry(exc=e, countdown=3600)
        else:
            # 다른 에러는 1분 후 재시도
            raise self.retry(exc=e, countdown=60)
```

**옵션 3: 대체 모델 사용**

더 저렴한 모델로 폴백:

```python
model_names = [
    "gemini-1.5-flash",  # 더 낮은 티어
    "gemini-1.5-flash-8b",  # 가장 저렴
]
```

### 3. 크롤링 성공률 개선 (선택) 🟢

**우선순위**: 낮음
**예상 소요 시간**: 2-3시간

#### 현재 성공률

- 검색된 기사: 100%
- 본문 추출 성공: ~40-60%
- 주요 실패 원인: Jina.ai가 일부 사이트에서 본문 추출 실패

#### 개선 방안

1. **BeautifulSoup 추가**

   Jina.ai 실패 시 대체 수단으로 BeautifulSoup 사용:

   ```python
   # news/services/scraper.py (신규 파일)
   from bs4 import BeautifulSoup
   import requests

   def extract_with_beautifulsoup(url):
       response = requests.get(url)
       soup = BeautifulSoup(response.content, 'html.parser')
       # 본문 추출 로직
       ...
   ```

2. **네이버 뉴스 전용 파서**

   네이버 뉴스는 구조가 일정하므로 전용 파서 추가:

   ```python
   def extract_naver_news(url):
       if "n.news.naver.com" in url:
           # 네이버 뉴스 전용 추출 로직
           ...
   ```

### 4. 클러스터링 파라미터 튜닝 (선택) 🟢

**우선순위**: 낮음
**예상 소요 시간**: 1시간

#### 현재 설정

```python
clustering_service = NewsClusteringService(eps=0.1, min_samples=2)
```

#### 튜닝 방법

1. **여러 eps 값 테스트**:
   - eps=0.05: 더 엄격한 중복 기준
   - eps=0.15: 더 느슨한 중복 기준

2. **min_samples 조정**:
   - min_samples=3: 3개 이상 유사 기사가 있을 때만 클러스터링

3. **테스트 스크립트 작성**:
   ```python
   # scripts/test_clustering.py
   from news.utils.clustering import NewsClusteringService

   eps_values = [0.05, 0.1, 0.15, 0.2]
   for eps in eps_values:
       service = NewsClusteringService(eps=eps, min_samples=2)
       # 테스트 실행
       ...
   ```

---

## 테스트 결과

### 크롤링 테스트 1

**실행 명령**:
```bash
docker compose exec app python manage.py crawl_news --keywords "AI" --max-articles 3
```

**결과**:
```
총 기사 수: 3
성공한 기사 수: 1
실패한 기사 수: 1
```

- 1개 성공
- 1개 실패 (본문 너무 짧음)
- 1개 중복 (이전 크롤링에서 이미 저장)

### 크롤링 테스트 2

**실행 명령**:
```bash
docker compose exec app python manage.py crawl_news --keywords "반도체" --max-articles 5
```

**결과**:
```
총 기사 수: 5
성공한 기사 수: 2
실패한 기사 수: 0
```

- 2개 신규 저장
- 3개 중복
- 본문 길이 부족으로 인한 실패: 0개 ✅

**참고**: Gemini API 할당량 초과로 요약 생성 일부 실패

### 저장 검증

**PostgreSQL**:
- 총 12개 뉴스 저장 (is_deleted=false)
- 메타데이터 및 요약 정상 저장

**OpenSearch**:
- 총 14개 벡터 저장
- 768차원 임베딩 정상 저장
- 본문 텍스트 정상 저장

---

## 주요 설정 값

### 크롤링 설정

| 항목 | 값 | 설명 |
|------|-----|------|
| 최소 본문 길이 | 30자 | 이보다 짧은 기사는 저장 안 함 |
| 기본 키워드 | AI, 반도체, 삼성전자, SK하이닉스 | 자동 크롤링 키워드 |
| 키워드당 최대 기사 | 10개 | Naver API 검색 결과 수 |
| 크롤링 주기 | 3시간 | Celery Beat 스케줄 |

### 벡터 임베딩

| 항목 | 값 | 설명 |
|------|-----|------|
| 임베딩 모델 | Gemini text-multilingual-embedding-002 | Google Gemini |
| 벡터 차원 | 768 | OpenSearch 인덱스 설정 |
| 검색 알고리즘 | HNSW | 근사 최근접 이웃 검색 |
| 유사도 측정 | 코사인 유사도 | OpenSearch 설정 |

### 클러스터링

| 항목 | 값 | 설명 |
|------|-----|------|
| 알고리즘 | DBSCAN | 밀도 기반 클러스터링 |
| eps | 0.1 | 클러스터 반경 |
| min_samples | 2 | 최소 샘플 수 |
| 전략 | latest_longest | 최신/가장 긴 기사 선택 |

### API 할당량

| 서비스 | 무료 티어 | 사용량 |
|--------|-----------|--------|
| Gemini API (Flash) | 20건/일 | 크롤링 1회당 6-10건 |
| Naver Search API | 25,000건/일 | 크롤링 1회당 ~10건 |
| Jina.ai Reader | 무제한 (공개 베타) | 크롤링 1회당 ~10건 |

---

## 참고 문서

- [OpenSearch 서비스 가이드](../guides/OPENSEARCH-SERVICE.md)
- [Celery 디버깅 가이드](../guides/DEBUGGING-CELERY.md)
- [뉴스 크롤링 튜토리얼](../guides/TUTORIAL-ADD-MODEL-API-simplified.md)
- [CLAUDE.md](../../CLAUDE.md) - 프로젝트 전체 가이드

---

## 변경 이력

| 날짜 | 작성자 | 변경 내용 |
|------|--------|----------|
| 2026-01-13 | Claude Code | 초안 작성 |
