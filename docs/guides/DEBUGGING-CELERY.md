# Celery 디버깅 가이드

**작성일**: 2026-01-13  
**목적**: Celery 워커, Beat, Flower 디버깅 방법

---

## 목차

1. [컨테이너 상태 확인](#컨테이너-상태-확인)
2. [로그 확인](#로그-확인)
3. [Flower를 통한 모니터링](#flower를-통한-모니터링)
4. [태스크 실행 및 상태 확인](#태스크-실행-및-상태-확인)
5. [일반적인 문제 해결](#일반적인-문제-해결)

---

## 컨테이너 상태 확인

### 모든 Celery 관련 컨테이너 상태 확인

```bash
# 컨테이너 상태 확인
docker compose ps | grep -E "(celery|flower)"

# 또는 전체 상태
docker compose ps
```

**예상 출력**:
```
NAME                STATUS          PORTS
celery-worker       Up 5 minutes    
celery-beat         Up 5 minutes    
celery-flower       Up 2 minutes    0.0.0.0:5555->5555/tcp
```

### 컨테이너가 실행되지 않는 경우

```bash
# 컨테이너 시작
docker compose up -d celery-worker celery-beat flower

# 로그 확인 (에러 원인 파악)
docker compose logs celery-worker
docker compose logs celery-beat
docker compose logs flower
```

---

## 로그 확인

### 실시간 로그 모니터링

```bash
# Celery Worker 로그 (실시간)
docker compose logs -f celery-worker

# Celery Beat 로그 (실시간)
docker compose logs -f celery-beat

# Flower 로그 (실시간)
docker compose logs -f flower

# 모든 Celery 관련 로그 동시 확인
docker compose logs -f celery-worker celery-beat flower
```

### 최근 로그만 확인

```bash
# 최근 100줄
docker compose logs --tail=100 celery-worker

# 특정 키워드 필터링
docker compose logs celery-worker | grep -i "error"
docker compose logs celery-worker | grep -i "crawl"
```

### 로그 레벨 변경

현재 설정: `--loglevel=info`

더 자세한 디버깅이 필요한 경우:

```yaml
# docker-compose.yml에서 수정
celery-worker:
  command: celery -A config worker --loglevel=debug
```

---

## Flower를 통한 모니터링

### Flower 접속

1. **웹 브라우저에서 접속**: http://localhost:5555

2. **주요 기능**:
   - **Workers**: 활성 워커 상태 확인
   - **Tasks**: 실행 중/완료/실패한 태스크 목록
   - **Monitor**: 실시간 태스크 모니터링
   - **Broker**: Redis 연결 상태

### Flower에서 확인할 수 있는 정보

- **태스크 상태**: PENDING, STARTED, SUCCESS, FAILURE, RETRY
- **실행 시간**: 각 태스크의 소요 시간
- **에러 메시지**: 실패한 태스크의 상세 에러
- **워커 상태**: CPU, 메모리 사용량
- **태스크 결과**: 반환값 확인

---

## 태스크 실행 및 상태 확인

### 1. Django Shell에서 태스크 실행

```bash
docker compose exec app python manage.py shell
```

```python
# 태스크 실행
from news.tasks import scheduled_crawl_news
result = scheduled_crawl_news.delay()

# Task ID 확인
print(f"Task ID: {result.id}")

# 상태 확인
print(f"State: {result.state}")  # PENDING, STARTED, SUCCESS, FAILURE

# 결과 확인 (완료된 경우)
if result.ready():
    print(f"Result: {result.result}")
```

### 2. AsyncResult로 상태 확인

```python
from celery.result import AsyncResult

# Task ID로 결과 조회
task_id = "40653b69-2de3-414c-84dc-0d6891395653"
result = AsyncResult(task_id)

# 상태 확인
print(f"State: {result.state}")
print(f"Ready: {result.ready()}")
print(f"Successful: {result.successful()}")

# 에러 확인
if result.failed():
    print(f"Error: {result.info}")

# 결과 확인
if result.ready():
    print(f"Result: {result.result}")
```

### 3. DB에서 CrawlJob 확인

```python
from news.models import CrawlJob

# 최근 작업 확인
latest_job = CrawlJob.objects.order_by('-created_at').first()
print(f"ID: {latest_job.id}")
print(f"Status: {latest_job.status}")
print(f"Keywords: {latest_job.keywords}")
print(f"Total: {latest_job.total_articles}")
print(f"Success: {latest_job.successful_articles}")
print(f"Failed: {latest_job.failed_articles}")

# 실패한 작업 확인
failed_jobs = CrawlJob.objects.filter(status='failed')
for job in failed_jobs:
    print(f"Job {job.id}: {job.error_message}")
```

### 4. Management Command로 실행

```bash
# 비동기 실행
docker compose exec app python manage.py crawl_news \
  --keywords "AI" "반도체" --max-articles 5 --async

# 동기 실행 (디버깅용 - 완료될 때까지 대기)
docker compose exec app python manage.py crawl_news \
  --keywords "AI" --max-articles 3
```

---

## 일반적인 문제 해결

### 문제 1: Celery Worker가 태스크를 받지 않음

**증상**: 태스크가 PENDING 상태에서 멈춤

**확인 사항**:
```bash
# Worker가 실행 중인지 확인
docker compose ps celery-worker

# Worker 로그 확인
docker compose logs celery-worker | grep -i "ready"

# Redis 연결 확인
docker compose exec celery-worker python -c "import redis; r=redis.from_url('redis://redis:6379/0'); print(r.ping())"
```

**해결 방법**:
1. Worker 재시작: `docker compose restart celery-worker`
2. Redis 연결 확인: `CELERY_BROKER_URL` 환경변수 확인
3. 네트워크 확인: `docker-network` 네트워크에 연결되어 있는지 확인

### 문제 2: 태스크가 실패함

**증상**: 태스크가 FAILURE 상태

**확인 방법**:
```python
# Django Shell에서
from celery.result import AsyncResult
result = AsyncResult("task-id")
print(result.info)  # 에러 메시지 확인
print(result.traceback)  # 스택 트레이스 확인
```

**Flower에서 확인**:
- http://localhost:5555 접속
- Tasks 탭에서 실패한 태스크 클릭
- "Traceback" 섹션에서 상세 에러 확인

**일반적인 원인**:
- API 키 누락/만료 (Gemini, Naver, Jina)
- DB 연결 실패
- OpenSearch 연결 실패
- 메모리 부족

### 문제 3: Celery Beat가 스케줄을 실행하지 않음

**증상**: 3시간마다 자동 실행되지 않음

**확인 사항**:
```bash
# Beat 로그 확인
docker compose logs celery-beat | grep -i "beat"

# 스케줄 확인
docker compose exec app python manage.py shell
>>> from django_celery_beat.models import PeriodicTask
>>> PeriodicTask.objects.all()  # DB 스케줄러 사용 시
```

**해결 방법**:
1. Beat 재시작: `docker compose restart celery-beat`
2. 설정 확인: `config/settings.py`의 `CELERY_BEAT_SCHEDULE` 확인
3. 시간대 확인: `CELERY_TIMEZONE = "Asia/Seoul"` 설정 확인

### 문제 4: Flower가 접속되지 않음

**증상**: http://localhost:5555 접속 불가

**확인 사항**:
```bash
# Flower 컨테이너 상태
docker compose ps flower

# Flower 로그 확인
docker compose logs flower

# 포트 확인
docker compose ps | grep 5555
```

**해결 방법**:
1. Flower 재시작: `docker compose restart flower`
2. 포트 충돌 확인: 다른 서비스가 5555 포트 사용 중인지 확인
3. 빌드 확인: `docker compose build flower` (flower 패키지 설치 확인)

### 문제 5: 메모리 부족

**증상**: Worker가 갑자기 종료되거나 태스크 실패

**확인 방법**:
```bash
# 컨테이너 리소스 사용량 확인
docker stats celery-worker

# Flower에서 확인
# http://localhost:5555 → Workers 탭 → Memory 사용량 확인
```

**해결 방법**:
1. Worker 수 조정: `docker-compose.yml`에서 `--concurrency` 옵션 조정
2. 메모리 제한 설정: `docker-compose.yml`에 `mem_limit` 추가

---

## 디버깅 팁

### 1. 상세 로그 활성화

```yaml
# docker-compose.yml
celery-worker:
  command: celery -A config worker --loglevel=debug --logfile=/dev/stdout
```

### 2. 태스크 실행 시간 측정

Flower의 "Tasks" 탭에서 각 태스크의 실행 시간을 확인할 수 있습니다.

### 3. 태스크 재시도 확인

```python
# Django Shell에서
from celery.result import AsyncResult
result = AsyncResult("task-id")
print(f"Retries: {result.retries}")
```

### 4. Redis 상태 확인

```bash
# Redis 연결 테스트
docker compose exec redis redis-cli ping

# 큐에 대기 중인 태스크 확인
docker compose exec redis redis-cli LLEN celery
```

### 5. 태스크 강제 취소

```python
# Django Shell에서
from celery.result import AsyncResult
result = AsyncResult("task-id")
result.revoke(terminate=True)  # 실행 중인 태스크 강제 종료
```

---

## 유용한 명령어 모음

```bash
# 모든 Celery 관련 컨테이너 재시작
docker compose restart celery-worker celery-beat flower

# 모든 Celery 관련 컨테이너 로그 확인
docker compose logs -f celery-worker celery-beat flower

# 특정 태스크 ID로 로그 필터링
docker compose logs celery-worker | grep "task-id"

# 컨테이너 내부에서 직접 Celery 명령 실행
docker compose exec celery-worker celery -A config inspect active
docker compose exec celery-worker celery -A config inspect registered

# Worker 통계 확인
docker compose exec celery-worker celery -A config stats
```

---

## 참고 문서

- [Celery 공식 문서](https://docs.celeryq.dev/)
- [Flower 공식 문서](https://flower.readthedocs.io/)
- [OpenSearch 서비스 가이드](./OPENSEARCH-SERVICE.md)
- [뉴스 크롤링 구현 현황](../plans/news-crawling-implementation-status.md)
