# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 커뮤니케이션 규칙

- 기본 응답: 한국어
- 주석 작성: 한국어
- 커밋 메시지: 한국어
- 변수/함수명: 영어(표준)

## 프로젝트 개요

Django 6.0 기반의 REST API 백엔드 프로젝트입니다. TimescaleDB(PostgreSQL 확장), Redis, OpenSearch를 활용한 마이크로서비스 아키텍처를 구성하고 있습니다.

## 기술 스택

- **웹 프레임워크**: Django 6.0, Django REST Framework, Django Channels (WebSocket)
- **데이터베이스**: TimescaleDB (PostgreSQL 16 기반 시계열 DB)
- **캐시/세션**: Redis 7
- **메시지 브로커**: RabbitMQ 3.13 (Celery 작업 큐)
- **검색 엔진**: OpenSearch
- **비동기 작업**: Celery 5.4+ with Flower 모니터링
- **API 문서화**: drf-spectacular (OpenAPI/Swagger)
- **모니터링**: Prometheus, Grafana, Node Exporter, cAdvisor
- **외부 API**:
  - KIS WebSocket API (실시간 주가 데이터)
  - DART OpenAPI (기업 공시 정보)
  - Naver News API (뉴스 검색)
  - Gemini API (AI 텍스트 처리 및 임베딩)

## 개발 환경 설정

### 로컬 개발 (Python 가상환경)

```bash
# 가상환경 활성화
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# 데이터베이스 마이그레이션
python manage.py migrate

# 개발 서버 실행
python manage.py runserver
```

### Docker Compose 환경

```bash
# 전체 서비스 실행 (db, redis, opensearch, app)
docker-compose up

# 백그라운드 실행
docker-compose up -d

# 특정 서비스만 실행
docker-compose up db redis

# 로그 확인
docker-compose logs -f app

# 서비스 중지 및 컨테이너 제거
docker-compose down

# 볼륨까지 모두 삭제
docker-compose down -v
```

### 서비스 포트

- Django App: `8000`
- PostgreSQL (TimescaleDB): `5432`
- Redis: `6379`
- RabbitMQ: `5672` (AMQP), `15672` (Management UI)
- OpenSearch: `9200` (REST API), `9600` (Performance Analyzer)
- Celery Flower: `5555` (모니터링 대시보드)
- KIS Mock Server: `8080` (테스트용)
- Prometheus: `9090`
- Grafana: `3000`
- cAdvisor: `8081`

## 데이터베이스 아키텍처

### TimescaleDB

PostgreSQL의 시계열 데이터 확장 버전을 사용합니다. 시계열 데이터를 효율적으로 저장하고 쿼리할 수 있습니다.

- 이미지: `timescale/timescaledb:latest-pg16`
- 연결 방식: `config/settings.py`에서 환경변수 기반 설정
  - `DATABASE_URL` 또는 개별 환경변수 (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`) 사용 가능

### Redis

세션 캐싱 및 일반 캐시 저장소로 사용됩니다.

- 세션 백엔드: `django.contrib.sessions.backends.cache`
- 캐시 백엔드: `django.core.cache.backends.redis.RedisCache`

### OpenSearch

검색 및 로그 분석 엔진으로 사용됩니다.

- 개발 환경에서는 보안 플러그인이 비활성화되어 있습니다 (`plugins.security.disabled=true`)
- 프로덕션 환경에서는 `.env` 파일에서 `OPENSEARCH_SECURITY_DISABLED=false`로 변경 필요

## Django 설정 구조

### `config/settings.py` 주요 설정

- **설치된 앱**: `rest_framework`, `drf_spectacular` (Swagger)
- **타임존**: `Asia/Seoul`
- **언어**: `ko-kr`
- **REST Framework**: drf-spectacular를 기본 스키마 클래스로 사용

### Swagger UI 설정

`SPECTACULAR_SETTINGS`에서 API 문서 제목, 설명, 버전을 관리합니다. 추가 API 엔드포인트 작성 시 drf-spectacular의 데코레이터를 사용하여 문서화할 수 있습니다.

## 개발 워크플로우

### 린트 및 코드 품질

```bash
# Ruff 린트 실행 (CI에서도 동일하게 실행)
ruff check .

# 자동 수정
ruff check --fix .

# 포맷팅
ruff format .
```

### Django 명령어

```bash
# 마이그레이션 생성
python manage.py makemigrations

# 마이그레이션 적용
python manage.py migrate

# 슈퍼유저 생성
python manage.py createsuperuser

# Django 셸 실행
python manage.py shell

# 정적 파일 수집
python manage.py collectstatic
```

### Docker 환경에서 Django 명령 실행

```bash
# 앱 컨테이너 내부에서 명령 실행
docker-compose exec app python manage.py migrate
docker-compose exec app python manage.py createsuperuser
docker-compose exec app python manage.py shell
```

## Pull Request 규칙

PR 제목 형식: `[feat] 기능 설명` 또는 `[fix] 버그 수정` 등

필수 섹션:
- 🔎 개요: 구현한 기능 간단 설명
- 📝 작업 내용: 구체적인 구현 내용
- 👀 변경 사항: 협업 시 주의사항
- 📸 UI 스크린샷: UI 변경 시 화면 캡처
- 📦 패키지 설치: 새 패키지 설치 시 이유 명시
- #️⃣ 관련 이슈: 이슈 번호 링크

## 환경 변수

`.env` 파일에서 관리하며 다음 변수들이 필요합니다:

- `POSTGRES_DB`: PostgreSQL 데이터베이스 이름
- `POSTGRES_USER`: PostgreSQL 사용자명
- `POSTGRES_PASSWORD`: PostgreSQL 비밀번호
- `OPENSEARCH_SECURITY_DISABLED`: OpenSearch 보안 플러그인 비활성화 여부 (개발: `true`, 프로덕션: `false`)
- `OPENSEARCH_INITIAL_ADMIN_PASSWORD`: OpenSearch 관리자 비밀번호

Docker Compose 환경에서는 자동으로 `DATABASE_URL`, `REDIS_URL`, `OPENSEARCH_HOST`가 설정됩니다.

## 브랜치 전략

- `main`: 메인 브랜치
- 작업 브랜치: `chore/#이슈번호`, `feat/#이슈번호`, `fix/#이슈번호` 등

## Git 커밋 컨벤션

### 커밋 메시지 형식

```
<IssueType>: <Message>
```

### IssueType 종류

- `feat`: 새로운 기능 추가
- `fix`: 버그 수정
- `docs`: 문서 수정
- `chore`: 빌드, 설정 파일 수정 등 기타 작업
- `refactor`: 코드 리팩토링 (기능 변경 없음)

### 예시

```bash
feat: 회원가입 기능 구현 완료
fix: 로그인 시 토큰 만료 오류 수정
docs: API 명세서 업데이트
chore: Docker Compose 설정 추가
refactor: 사용자 인증 로직 개선
```

### 작성 규칙

- 메시지는 한국어로 작성
- 간결하고 명확하게 작성 (50자 이내 권장)
- 과거형이 아닌 현재형/완료형 사용 ("추가함" 대신 "추가" 또는 "추가 완료")
- 첫 글자는 대문자로 시작하지 않음

## 문서 관리

### 문서 디렉토리 구조

모든 프로젝트 문서는 `docs/` 디렉토리에 저장합니다.

```
docs/
├── PRD.md                    # Product Requirements Document
├── API.md                    # API 명세서
├── ARCHITECTURE.md           # 시스템 아키텍처 문서
├── ERD.md                    # 데이터베이스 ERD 문서
├── guides/                   # 개발 가이드 및 튜토리얼
└── plans/                    # 계획 문서
```

### 문서 작성 규칙

- **언어**: 한국어 (기술 용어는 영어 병기 가능)
- **포맷**: Markdown
- **위치**: 모든 문서는 `docs/` 디렉토리 또는 하위 디렉토리에 저장
- **네이밍**: 대문자로 시작, 언더스코어 대신 하이픈 사용 (예: `API-GUIDE.md`)
- **버전 관리**: Git으로 관리하며, 중요한 변경사항은 커밋 메시지에 명시
- **Plan 문서**: 모든 plan은 `docs/plans/` 디렉토리에 저장
- **Notion 루트 페이지**: "2025 Winter Bootcamp"

## 시스템 아키텍처

이 프로젝트는 마이크로서비스 아키텍처로 설계되어 있으며, 크게 3가지 핵심 시스템으로 구성됩니다:

### 1. 실시간 주가 데이터 처리 (KIS WebSocket)

**서비스 구성**: kis-publisher → Redis Pub/Sub → persistence-worker + subscribe-handler

- **kis-publisher**: KIS WebSocket API에서 실시간 체결 데이터를 수신하여 Redis Pub/Sub에 발행
- **persistence-worker**: Redis에서 데이터를 구독하여 TimescaleDB에 배치 저장 (COPY 명령 사용)
- **subscribe-handler**: Django 내부에서 데이터 구독 및 WebSocket 전송 (Django Channels)

**주요 데이터 모델**:
- `StockTick` (core/models.py): TimescaleDB Hypertable로 시계열 데이터 최적화
- Continuous Aggregates: 1분/15분/1시간/1일봉 자동 생성

### 2. 뉴스 크롤링 및 AI 분석 시스템

**Celery Canvas 파이프라인** (6단계):
1. 검색 (Naver API) → 2. 본문 추출 (Jina API) → 3. 정제+요약 (Gemini AI) → 4. 임베딩 (Gemini) → 5. DB 저장 → 6. 클러스터링+OpenSearch 저장

**주요 서비스**:
- `news/tasks/`: Celery 태스크 정의 (workflows.py가 전체 파이프라인 조율)
- `news/services/`: 외부 API 클라이언트 (jina_api.py, refiner.py, summarizer.py, embedding.py)
- OpenSearch 벡터 검색: HNSW 알고리즘 + 코사인 유사도 (768차원)

### 3. DART 기업 정보 동기화

**배치 작업** (Celery Beat 스케줄링):
- 기업 개황 동기화 (companies/tasks/dart_sync.py)
- 재무제표 동기화 (FinancialStatement 모델)
- 공시보고서 동기화 (Report 모델)
- 시가총액 동기화 (KIS REST API)

**주요 서비스**:
- `companies/services/dart_api.py`: DART OpenAPI 클라이언트
- `companies/services/company_info.py`: 기업 정보 동기화
- `companies/services/financial.py`: 재무제표 처리

### 4. Django 앱 구조

```
companies/     # 기업 정보 (Company, FinancialStatement, Report)
core/          # 주가 데이터 (StockTick, Celery 태스크)
industries/    # 산업 분류 및 지수
news/          # 뉴스 크롤링 및 검색
users/         # 사용자 인증 (JWT)
comparisons/   # 기업 비교 매치업
indices/       # 시장 지수 (KOSPI, KOSDAQ)
```

### 5. 비동기 작업 처리

**Celery 설정**:
- Broker: RabbitMQ (메시지 큐 처리, AMQP 프로토콜)
- Result Backend: Redis (빠른 결과 조회)
- Beat Scheduler: 주기적 작업 스케줄링 (crontab)

**주요 스케줄**:
- 뉴스 크롤링: 3시간마다
- 전체 기업 뉴스 동기화: 3시간마다 (뉴스 크롤링 30분 후, OpenSearch → CompanyNews 매핑)
- DART 동기화: 새벽 3시 (일 1회)
- 시가총액 갱신: 평일 16:10 (장 마감 후)
- 주가 데이터 동기화: 장중 30초~1시간 간격

## 주요 Management Commands

### 데이터 동기화

```bash
# 시가총액 상위 기업 동기화 (API 또는 Shell)
# API: POST /api/companies/admin/sync-top-companies/
# Body: {"limit": 100, "update_existing": false}

# Django Shell에서 실행:
python manage.py shell -c "
from companies.services.top_companies_sync import TopCompaniesSyncService
service = TopCompaniesSyncService()
result = service.sync_top_companies(limit=100)
print(result['stats'])
"

# 뉴스 크롤링 (비동기)
python manage.py crawl_news --keywords "AI" "반도체" --max-articles 10 --async

# 실시간 주가 구독 핸들러 시작
python manage.py subscribe_handler

# 시가총액 순위 계산
python manage.py update_rankings
```

### Celery 작업 실행

```bash
# Celery Worker 시작
celery -A config worker --loglevel=info

# Celery Beat 시작 (스케줄러)
celery -A config beat --loglevel=info

# Flower 모니터링 대시보드
celery -A config flower --port=5555
```

## 테스트

### 단위 테스트

```bash
# 전체 테스트 실행
python manage.py test

# 특정 앱 테스트
python manage.py test companies
python manage.py test news

# 특정 테스트 케이스
python manage.py test companies.tests.test_dart_api
```

### API 테스트

```bash
# Swagger UI 접속
http://localhost:8000/api/schema/swagger-ui/

# API 문서 JSON
http://localhost:8000/api/schema/
```

## 데이터베이스 관리

### TimescaleDB 특수 명령

```sql
-- Hypertable 생성 (마이그레이션에서 자동 실행)
SELECT create_hypertable('stock_ticks', 'time');

-- Continuous Aggregate 생성 예시
CREATE MATERIALIZED VIEW stock_prices_1m
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', time) AS bucket,
       stock_code,
       first(price, time) AS open,
       max(price) AS high,
       min(price) AS low,
       last(price, time) AS close,
       sum(volume) AS volume
FROM stock_ticks
GROUP BY bucket, stock_code;

-- Continuous Aggregate 수동 리프레시
CALL refresh_continuous_aggregate('stock_prices_1m', NULL, NULL);
```

### 마이그레이션 주의사항

- TimescaleDB Hypertable은 `managed=False` 모델로 정의
- `migrations.RunSQL()`로 CREATE TABLE 및 create_hypertable() 실행
- Continuous Aggregates는 별도 마이그레이션 파일로 관리

## 모니터링 및 디버깅

### Celery 작업 모니터링

```bash
# Flower 대시보드
http://localhost:5555

# Celery 작업 상태 확인
celery -A config inspect active
celery -A config inspect stats

# 특정 작업 취소
celery -A config revoke <task_id>
```

### 로그 확인

```bash
# Django 앱 로그
docker-compose logs -f app

# Celery Worker 로그
docker-compose logs -f celery-worker

# kis-publisher 로그
docker-compose logs -f kis-publisher

# persistence-worker 로그
docker-compose logs -f persistence-worker
```

### Prometheus/Grafana 모니터링

```bash
# Prometheus UI
http://localhost:9090

# Grafana 대시보드
http://localhost:3000
# 기본 계정: admin / admin (환경변수로 변경 가능)
```

## 환경별 설정

### 배치 작업 활성화 (개발 환경 토큰 절감)

`.env` 파일에서 배치 작업을 개별적으로 활성화/비활성화할 수 있습니다:

```bash
# 뉴스 크롤링 (Gemini 토큰 사용)
NEWS_BATCH_ENABLED=false  # 기본값

# DART 동기화 (무료 API)
DART_SYNC_ENABLED=true  # 기본값

# 보고서 처리 (Gemini 토큰 사용)
REPORT_PROCESSING_ENABLED=false  # 기본값

# 마켓 지수 동기화
MARKET_INDEX_SYNC_ENABLED=true  # 기본값

# 주가 데이터 동기화
STOCK_PRICE_SYNC_ENABLED=true  # 기본값
```

### KIS API 테스트 모드

실제 KIS API 없이도 테스트 가능:

```bash
KIS_USE_TEST_MODE=true
KIS_TEST_WS_URL=ws://kis-mock-server:8080
```

## 주요 API 엔드포인트

자세한 API 명세는 Swagger UI 참조: `http://localhost:8000/api/schema/swagger-ui/`

### 기업 정보

```
GET /api/companies/              # 기업 목록
GET /api/companies/{stock_code}/ # 기업 상세 정보
GET /api/companies/{stock_code}/financials/  # 재무제표
GET /api/companies/{stock_code}/reports/     # 공시보고서
```

### 뉴스

```
GET /api/news/                   # 뉴스 목록
GET /api/news/{id}/              # 뉴스 상세
GET /api/news/search/            # 벡터 유사도 검색 (OpenSearch)
```

### 주가 데이터

```
GET /api/stocks/{stock_code}/prices/  # 주가 데이터 (시간봉 지정)
GET /api/stocks/{stock_code}/realtime/  # 실시간 WebSocket 연결
```

## 트러블슈팅

### Celery Worker 응답 없음

```bash
# Worker 재시작
docker-compose restart celery-worker

# Worker 상태 확인
celery -A config inspect ping

# Broker 연결 확인 (RabbitMQ)
docker-compose exec rabbitmq rabbitmqctl status
```

### KIS WebSocket 연결 끊김

```bash
# 재연결 시도 횟수 증가
export KIS_MAX_RECONNECT=10

# 구독 종목 수 제한 (과부하 방지)
export KIS_SYMBOL_LIMIT=10

# kis-publisher 재시작
docker-compose restart kis-publisher
```

### TimescaleDB Hypertable 오류

```bash
# Hypertable 상태 확인
docker-compose exec db psql -U postgres -d postgres
postgres=# SELECT * FROM timescaledb_information.hypertables;

# Continuous Aggregate 확인
postgres=# SELECT * FROM timescaledb_information.continuous_aggregates;
```

### OpenSearch 연결 실패

```bash
# 클러스터 상태 확인
curl -X GET "http://localhost:9200/_cluster/health?pretty"

# 인덱스 목록
curl -X GET "http://localhost:9200/_cat/indices?v"
```

## 공통 서비스 베이스 클래스

### Gemini API 서비스

새로운 Gemini API 서비스 작성 시 베이스 클래스를 상속받아 사용합니다:

```python
# 텍스트 생성 서비스
from services.base import GeminiGenerativeClient

class MyTextService(GeminiGenerativeClient):
    def __init__(self):
        super().__init__(model_name="gemini-2.0-flash")

    def process(self, text: str) -> str:
        prompt = f"다음 텍스트를 처리하세요: {text}"
        return self.generate_content(prompt)

# 임베딩 서비스
from services.base import GeminiEmbeddingClient

class MyEmbeddingService(GeminiEmbeddingClient):
    def get_vectors(self, texts: list[str]) -> list:
        return self.get_embeddings_batch(texts, task_type="RETRIEVAL_DOCUMENT")
```

**베이스 클래스 제공 메서드**:

| 클래스 | 메서드 | 설명 |
|--------|--------|------|
| `GeminiGenerativeClient` | `generate_content(prompt)` | 텍스트 생성 |
| | `truncate_text(text, max_length)` | 텍스트 길이 제한 |
| `GeminiEmbeddingClient` | `create_embedding(text, task_type)` | 단일 텍스트 임베딩 |
| | `get_embeddings_batch(texts, task_type)` | 배치 임베딩 |
| `ExternalAPIClient` | `get(endpoint, params)` | GET 요청 |
| | `post(endpoint, data)` | POST 요청 |

### 공통 유틸리티

```python
from utils.pagination import paginate_queryset
from utils.responses import success_response, error_response
```

## Serializer 작성 주의사항

### drf-spectacular 호환성

`ModelSerializer`에서 관계 필드를 `source`로 매핑할 때 Mixin 패턴 대신 명시적 필드 정의를 사용합니다:

```python
# ❌ 잘못된 방식 (drf-spectacular 스키마 생성 오류)
class CompanyNewsSerializer(CompanyFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = CompanyNews
        fields = ["title", "content"]  # title이 News 모델에 있으면 오류

# ✅ 올바른 방식
class CompanyNewsSerializer(serializers.Serializer):
    title = serializers.CharField(source="news.title", read_only=True)
    content = serializers.CharField(source="news.content", read_only=True)
```

## Dockerfile 수정 시 주의사항

새 디렉토리 추가 시 `Dockerfile`에 COPY 명령 추가 필요:

```dockerfile
# 현재 포함된 디렉토리 (9개)
COPY config/ /app/config/
COPY companies/ /app/companies/
COPY comparisons/ /app/comparisons/
COPY core/ /app/core/
COPY industries/ /app/industries/
COPY indices/ /app/indices/
COPY news/ /app/news/
COPY users/ /app/users/
COPY services/ /app/services/
# 새 디렉토리 추가 시 여기에 COPY 추가
```

## 참고 문서

- 시스템 아키텍처: `docs/SYSTEM_ARCHITECTURE.md`
- 리팩토링 계획: `docs/plans/REFACTORING-PLAN.md`

## 에이전트 작동 규칙

1. 오류 해결 시에는 명확한 원인을 찾고, 원인이 불분명할 때는 사용자에게 필요한 정보를 요청하거나 인터넷 검색을 통해 레퍼런스를 찾습니다.
2. 코드 변경 시 관련 테스트 파일도 함께 확인합니다.
3. 새로운 Celery 태스크 추가 시:
   - 앱의 `tasks/__init__.py`에 import 및 `__all__` 목록에 추가하여 autodiscover가 인식하도록 합니다.
   - 필요시 `config/celery.py`에 명시적 import를 추가합니다 (core.tasks 등 특수한 경우).
4. TimescaleDB 관련 변경은 일반 Django 마이그레이션이 아닌 `migrations.RunSQL()`을 사용합니다.
5. 로컬 명령어 사용할 때는 반드시 가상환경을 활성화한 다음 실행.
6. PR 생성 시에는 `.github/pull_request_template.md`를 참조.
7. 새 Gemini 서비스 작성 시 `services/base`의 베이스 클래스를 상속.
8. 새 디렉토리 추가 시 `Dockerfile`에 COPY 명령 추가 필수.