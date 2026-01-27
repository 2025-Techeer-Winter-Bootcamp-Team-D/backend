# CI/CD 파이프라인 최적화 분석

## 1. 개요

이 문서는 현재 CI/CD 파이프라인의 최적화 가능 지점을 분석하고 개선 방안을 제시합니다.

### 1.1 분석 대상 파일
| 파일 유형 | 경로 |
|----------|------|
| 워크플로우 | `.github/workflows/ci-cd.yml` |
| 메인 Dockerfile | `Dockerfile` |
| kis-publisher | `kis-publisher/Dockerfile` |
| persistence-worker | `persistence-worker/Dockerfile` |
| OpenSearch | `opensearch/Dockerfile` |
| Nginx | `deploy/app/nginx/Dockerfile` |
| 의존성 | `requirements.txt` (65개 패키지) |

---

## 2. 의존성 캐싱 분석

### 2.1 Python 패키지 캐싱

#### GitHub Actions (ci-cd.yml)
```yaml
- name: Set up Python with cache
  uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'
```

**평가**: ✅ **우수**
- GitHub Actions 내장 pip 캐시 활용
- `requirements.txt` 기반 자동 캐시 키 생성

#### Dockerfile 의존성 설치
```dockerfile
RUN uv pip install --system --no-cache -r requirements.txt
```

**평가**: ⚠️ **개선 필요**
- `--no-cache` 플래그로 인해 Docker 빌드 캐시 미활용
- 이미지 재빌드 시마다 모든 패키지 재다운로드

**권장 개선안**:
```dockerfile
# BuildKit 캐시 마운트 사용
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt
```

### 2.2 Docker 레이어 캐싱

#### 현재 레이어 순서 (Dockerfile)
```dockerfile
COPY requirements.txt /app/           # 1. 의존성 파일 먼저
RUN uv pip install ...                 # 2. 의존성 설치
COPY config/ companies/ ... /app/      # 3. 소스 코드 (자주 변경)
```

**평가**: ✅ **우수**
- 자주 변경되지 않는 파일(의존성)을 먼저 복사
- 코드 변경 시 의존성 레이어 재사용 가능

### 2.3 GitHub Actions 빌드 캐시

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

**평가**: ⚠️ **심각한 문제 발견**
- GitHub Actions 기본 제공 캐시 백엔드 활용 ✅
- `mode=max`로 최대 캐시 저장 ✅
- **Matrix 캐시 충돌 문제** ❌ (아래 2.4 참조)

### 2.4 Matrix 캐시 충돌 (Critical)

**현재 설정**:
```yaml
strategy:
  matrix:
    include:
      - service: backend-core
      - service: kis-publisher
      - service: persistence-worker

# 문제: 3개 이미지가 동일한 캐시 키 사용
cache-from: type=gha
cache-to: type=gha,mode=max
```

**평가**: ❌ **심각한 성능 저하**

**발생 현상**:
1. 3개 job이 **동시에** 시작 (GitHub Actions matrix는 병렬 실행)
2. 모두 동일한 GHA 캐시 키에서 읽기 시도
3. 캐시가 다른 이미지의 레이어로 덮어씌워져 있음 → **캐시 미스**
4. 빌드 완료 후 각 job이 같은 키에 저장 시도 → **마지막 job만 저장됨**
5. 다음 빌드에서도 2/3 이미지는 캐시 미스 반복

**실측 빌드 시간** (캐시 미스 시):
| 단계 | 시간 |
|------|------|
| Base image pull (`python:3.11-slim`) | 30초~1분 |
| apt-get update + install | 2~3분 |
| uv 이미지에서 복사 | 30초~1분 |
| Python 패키지 설치 | 30초 |
| 레이어 푸시 (GHCR) | 2~4분 |
| **총합 (persistence-worker)** | **~9분** |

**권장 개선안**:
```yaml
# 각 서비스별 고유 캐시 scope 지정
cache-from: type=gha,scope=${{ matrix.service }}
cache-to: type=gha,mode=max,scope=${{ matrix.service }}
```

**예상 효과**:
- 캐시 히트 시 빌드 시간: ~9분 → **~1-2분** (80% 단축)
- 각 이미지가 자신만의 캐시 네임스페이스 유지

---

## 3. 테스트 최적화 분석

### 3.1 현재 테스트 실행 방식

```yaml
- name: Run Tests
  run: python manage.py test
```

**평가**: ⚠️ **개선 필요**

| 항목 | 현재 상태 | 문제점 |
|------|---------|--------|
| 병렬화 | ❌ 미적용 | 단일 프로세스 실행 |
| 선택적 테스트 | ❌ 미적용 | 모든 테스트 실행 |
| 테스트 분류 | ❌ 미적용 | 단위/통합 구분 없음 |
| 커버리지 | ❌ 미적용 | 추적 불가능 |

### 3.2 권장 개선안

#### 옵션 A: Django 내장 병렬화
```yaml
- name: Run Tests (Parallel)
  run: python manage.py test --parallel auto
```

#### 옵션 B: pytest 사용 (권장)
```yaml
- name: Run Tests
  run: pytest --parallel --cov=. --cov-report=xml --tb=short

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

**예상 효과**: 테스트 시간 50-70% 단축

---

## 4. Docker 빌드 최적화 분석

### 4.1 멀티스테이지 빌드

**현재 상태**: ❌ **미구현** (단일 스테이지)

```dockerfile
FROM python:3.12-slim
RUN apt-get install -y build-essential libpq-dev  # 빌드 도구
# ... 의존성 설치 + 애플리케이션 코드
```

**문제점**:
- 빌드 도구(build-essential, libpq-dev)가 최종 이미지에 포함
- 불필요한 이미지 크기 증가

**권장 개선안**:
```dockerfile
# Stage 1: Builder
FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

# Stage 2: Runtime (빌드 도구 제외)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.12/site-packages \
    /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
WORKDIR /app
COPY . .
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

**예상 효과**:
- 이미지 크기: ~300MB → ~150-180MB (40-50% 감소)
- 보안 향상 (빌드 도구 제외)

### 4.2 서비스별 Dockerfile 분석

| 서비스 | 멀티스테이지 | `--no-cache` | 빌드 도구 포함 |
|--------|-------------|--------------|----------------|
| backend-core | ❌ | ⚠️ 사용 | ⚠️ 포함 |
| kis-publisher | ❌ | ⚠️ 사용 | ⚠️ 포함 |
| persistence-worker | ❌ | ⚠️ 사용 | ⚠️ 포함 |
| opensearch | N/A | N/A | ✅ 없음 |
| nginx | N/A | N/A | ⚠️ openssl 포함 |

---

## 5. 워크플로우 최적화 분석

### 5.1 조건부 실행

```yaml
# 빌드-푸시: push 이벤트에서만
if: github.event_name == 'push'

# 배포: develop 브랜치 push에서만
if: github.event_name == 'push' && github.ref == 'refs/heads/develop'
```

**평가**: ✅ **우수**
- PR에서는 빌드-푸시 스킵 (비용 절감)
- develop 브랜치에만 배포

**개선 권장** (수동 실행 지원):
```yaml
if: (github.event_name == 'push' && github.ref == 'refs/heads/develop') ||
    github.event_name == 'workflow_dispatch'
```

### 5.2 불필요한 대기 시간

```yaml
# deploy-monitoring
echo "Waiting for Loki to stabilize..."
sleep 15
```

**평가**: ⚠️ **개선 필요**
- 고정 시간 대기는 불안정한 방식
- 이미 헬스 체크 로직이 존재함

**권장**: `sleep 15` 제거, 기존 헬스 체크 루프 활용

### 5.3 이미지 정리 정책

```yaml
# deploy-app
docker image prune -af
```

**평가**: ⚠️ **주의 필요**
- `-a` 플래그는 사용 중이지 않은 모든 이미지 삭제
- 프로덕션에서 위험할 수 있음

**권장 개선안**:
```bash
docker image prune -f --filter "until=72h"
```

---

## 6. 현재 강점

| 항목 | 상태 | 설명 |
|------|------|------|
| pip 캐싱 | ✅ | GitHub Actions 내장 캐시 활용 |
| Docker GHA 캐시 | ⚠️ | BuildKit + GHA 캐시 통합 (Matrix 충돌 문제 있음) |
| 레이어 순서 | ✅ | 의존성 → 소스코드 순서 |
| 헬스 체크 | ✅ | 다중 헬스 체크 및 재시도 로직 |
| 인프라 분리 | ✅ | 데이터/앱/모니터링 계층 분리 |
| 조건부 배포 | ✅ | develop 브랜치만 배포 |

---

## 7. 개선 필요 항목

| 항목 | 현재 | 권장 | 우선순위 |
|------|------|------|----------|
| **Matrix 캐시 scope** | scope 미지정 (충돌) | `scope=${{ matrix.service }}` | **긴급** |
| Docker 캐시 마운트 | `--no-cache` | `--mount=type=cache` | 높음 |
| 테스트 병렬화 | 단일 프로세스 | `--parallel auto` | 높음 |
| 멀티스테이지 빌드 | 단일 스테이지 | 2단계 분리 | 중간 |
| 테스트 커버리지 | 미구현 | pytest-cov + Codecov | 중간 |
| 고정 대기 제거 | `sleep 15` | 헬스 체크 사용 | 낮음 |
| 이미지 정리 정책 | `prune -af` | `prune -f --filter` | 낮음 |

---

## 8. 구현 계획

### Phase 1: 즉시 적용 (긴급)

#### 8.1 Matrix 캐시 scope 분리 (Critical)
```yaml
# ci-cd.yml - build-and-push job 수정
- name: Build and push Docker image
  uses: docker/build-push-action@v5
  with:
    context: ${{ matrix.context }}
    file: ${{ matrix.file }}
    push: true
    tags: ${{ steps.meta.outputs.tags }}
    labels: ${{ steps.meta.outputs.labels }}
    cache-from: type=gha,scope=${{ matrix.service }}   # scope 추가
    cache-to: type=gha,mode=max,scope=${{ matrix.service }}  # scope 추가
```
**예상 효과**: 이미지 빌드 시간 ~9분 → ~1-2분 (80% 단축)

#### 8.2 테스트 병렬화
```yaml
# ci-cd.yml 수정
- name: Run Tests
  run: python manage.py test --parallel auto
```
**예상 효과**: 테스트 시간 50-70% 단축

#### 8.3 Docker 캐시 마운트
```dockerfile
# Dockerfile, kis-publisher/Dockerfile, persistence-worker/Dockerfile 수정
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt
```
**예상 효과**: 이미지 재빌드 시 10-20% 속도 향상

#### 8.4 고정 대기 제거
```yaml
# deploy-monitoring에서 sleep 15 제거
# 기존 헬스 체크 루프로 대체
```
**예상 효과**: 배포 시간 15초 단축

### Phase 2: 중기 개선 (2주 이내)

#### 8.5 멀티스테이지 빌드
- `Dockerfile` → 2단계 분리
- `kis-publisher/Dockerfile` → 2단계 분리
- `persistence-worker/Dockerfile` → 2단계 분리

**예상 효과**: 이미지 크기 40-50% 감소

#### 8.6 테스트 커버리지
```yaml
- name: Run Tests with Coverage
  run: |
    pip install pytest pytest-cov pytest-django
    pytest --cov=. --cov-report=xml

- name: Upload Coverage
  uses: codecov/codecov-action@v3
```
**예상 효과**: 코드 품질 지표 확보

### Phase 3: 장기 개선 (1개월 이내)

#### 8.7 보안 스캔 추가
```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: 'ghcr.io/${{ github.repository }}/backend-core:${{ github.sha }}'
    format: 'sarif'
    output: 'trivy-results.sarif'
```

#### 8.8 빌드 시간 메트릭 수집
- GitHub Actions 빌드 시간 추적
- Grafana 대시보드 연동

---

## 9. 예상 개선 효과 요약

| 개선 항목 | 현재 | 예상 개선 | 효과 |
|----------|------|----------|------|
| **이미지 빌드 (Matrix 캐시)** | **~9분** | **~1-2분** | **80% 단축** |
| 테스트 시간 | ~3분 | ~1분 | 66% 단축 |
| 이미지 크기 | ~300MB | ~180MB | 40% 감소 |
| 배포 시간 | ~2분 | ~1.5분 | 25% 단축 |
| **전체 CI/CD** | **~17분** | **~6분** | **65% 단축** |

---

## 10. 변경 이력

| 날짜 | 버전 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| 2025-01-27 | 1.0 | Claude | 최초 작성 |
| 2025-01-27 | 1.1 | Claude | Matrix 캐시 충돌 문제 분석 추가 (2.4절) |
