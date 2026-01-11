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

- **웹 프레임워크**: Django 6.0, Django REST Framework
- **데이터베이스**: TimescaleDB (PostgreSQL 16 기반 시계열 DB)
- **캐시**: Redis 7
- **검색 엔진**: OpenSearch
- **API 문서화**: drf-spectacular (OpenAPI/Swagger)

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
- OpenSearch: `9200` (REST API), `9600` (Performance Analyzer)

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
└── guides/                   # 개발 가이드 및 튜토리얼
```

### 문서 작성 규칙

- **언어**: 한국어 (기술 용어는 영어 병기 가능)
- **포맷**: Markdown
- **위치**: 모든 문서는 `docs/` 디렉토리 또는 하위 디렉토리에 저장
- **네이밍**: 대문자로 시작, 언더스코어 대신 하이픈 사용 (예: `API-GUIDE.md`)
- **버전 관리**: Git으로 관리하며, 중요한 변경사항은 커밋 메시지에 명시
