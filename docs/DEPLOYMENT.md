# 프로덕션 배포 가이드

AWS EC2에서 HTTPS를 적용한 프로덕션 배포 가이드입니다.

## 아키텍처 개요

```
                    인터넷
                       │
                       ▼
              ┌─────────────────┐
              │  Nginx (80/443) │  ← SSL 종료, 리버스 프록시
              │  + Certbot      │
              └────────┬────────┘
                       │
    ┌──────────────────┼──────────────────┐
    │                  │                  │
    ▼                  ▼                  ▼
┌─────────┐      ┌─────────┐      ┌─────────┐
│   App   │      │  Data   │      │Monitor  │
│  Layer  │      │  Layer  │      │  Layer  │
└─────────┘      └─────────┘      └─────────┘
```

## 디렉토리 구조

```
deploy/
├── app/                    # 애플리케이션 서버
│   ├── docker-compose.yml
│   ├── .env
│   ├── init-letsencrypt.sh # SSL 인증서 발급 스크립트
│   ├── certbot/            # 인증서 저장 (자동 생성)
│   └── nginx/
│       ├── Dockerfile
│       └── conf.d/
│           └── default.conf.template
├── data/                   # 데이터베이스 서버
│   ├── docker-compose.yml
│   └── .env
├── monitoring/             # 모니터링 서버
│   ├── docker-compose.yml
│   └── .env
└── env/                    # 환경변수 예시
    ├── .env.app.example
    └── .env.data.example
```

## 사전 요구사항

- AWS EC2 인스턴스 (Ubuntu 22.04+ 권장)
- 도메인 및 DNS 설정 완료
- Docker 및 Docker Compose 설치

## 1. EC2 보안 그룹 설정

| 포트 | 프로토콜 | 설명 |
|------|---------|------|
| 22 | TCP | SSH |
| 80 | TCP | HTTP (HTTPS 리다이렉트) |
| 443 | TCP | HTTPS |

## 2. DNS 설정

도메인 DNS에 A 레코드 추가:

| 타입 | 이름 | 값 |
|-----|-----|-----|
| A | @ | EC2_PUBLIC_IP |
| A | www | EC2_PUBLIC_IP |

DNS 전파 확인:
```bash
dig +short your-domain.com
```

## 3. 환경변수 설정

```bash
cd deploy/app

# 예시 파일 복사
cp ../env/.env.app.example .env

# 환경변수 수정
nano .env
```

**필수 수정 항목:**
```bash
# HTTPS 설정
DOMAIN=your-domain.com
CERTBOT_EMAIL=your-email@example.com

# 데이터 레이어 연결 (Data 서버 IP)
DB_HOST=10.0.1.xxx
REDIS_HOST=10.0.1.xxx
OPENSEARCH_HOST=10.0.1.xxx

# 인증 정보
POSTGRES_PASSWORD=<강력한_비밀번호>
REDIS_PASSWORD=<강력한_비밀번호>

# Django
DJANGO_SECRET_KEY=<새로운_시크릿_키>
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# KIS API (실제 키)
KIS_APP_KEY=<실제_키>
KIS_APP_SECRET=<실제_시크릿>
KIS_USE_TEST_MODE=false
```

### Django SECRET_KEY 생성

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 4. SSL 인증서 발급

```bash
cd deploy/app

# 스크립트 실행 권한 부여
chmod +x init-letsencrypt.sh

# 인증서 발급
./init-letsencrypt.sh
```

### 수동 발급 (스크립트 실패 시)

```bash
# 1. 디렉토리 생성
mkdir -p certbot/conf certbot/www

# 2. 임시 인증서 생성 (nginx 시작용)
docker run --rm -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
  alpine/openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -keyout "/etc/letsencrypt/live/$DOMAIN/privkey.pem" \
  -out "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" \
  -subj "/CN=localhost"

# 3. Nginx 시작
docker compose up -d nginx

# 4. 실제 인증서 발급
rm -rf certbot/conf/live/$DOMAIN
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d your-domain.com \
  -d www.your-domain.com

# 5. Nginx 재시작
docker compose restart nginx
```

## 5. 서비스 시작

```bash
cd deploy/app

# 전체 서비스 시작
docker compose up -d

# 로그 확인
docker compose logs -f
```

## 6. 접속 확인

| 서비스 | URL |
|--------|-----|
| API | https://your-domain.com/api/ |
| Swagger UI | https://your-domain.com/api/schema/swagger-ui/ |
| Grafana | https://your-domain.com/grafana/ |
| Prometheus | https://your-domain.com/prometheus/ |
| Flower | https://your-domain.com/celery-flower/ |
| RabbitMQ | https://your-domain.com/rabbitmq/ |

## 7. 인증서 자동 갱신

Certbot 컨테이너가 자동으로 12시간마다 갱신을 확인합니다.
수동 갱신이 필요한 경우:

```bash
docker compose run --rm certbot renew
docker compose restart nginx
```

## 유용한 명령어

### 서비스 관리

```bash
# 상태 확인
docker compose ps

# 로그 확인
docker compose logs -f app
docker compose logs -f nginx

# 재시작
docker compose restart app

# 컨테이너 접속
docker compose exec app bash
```

### 인증서 관리

```bash
# 인증서 상태 확인
docker compose run --rm certbot certificates

# 강제 갱신 (테스트)
docker compose run --rm certbot renew --dry-run
```

### 데이터베이스

```bash
# Django 마이그레이션
docker compose exec app python manage.py migrate

# 정적 파일 수집
docker compose exec app python manage.py collectstatic --noinput
```

## 트러블슈팅

### SSL 인증서 발급 실패

1. **DNS 확인**: `dig +short your-domain.com` → EC2 IP 반환 확인
2. **포트 확인**: 보안 그룹에서 80, 443 포트 열림 확인
3. **테스트 모드**: `STAGING=1 ./init-letsencrypt.sh`로 먼저 테스트

### Nginx 502 Bad Gateway

```bash
# app 컨테이너 상태 확인
docker compose logs app

# 헬스체크
curl http://localhost:8000/health/
```

### WebSocket 연결 실패

```bash
# Nginx 설정 확인
docker compose exec nginx nginx -t

# WebSocket 테스트
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  https://your-domain.com/ws/stock/
```

## 보안 체크리스트

- [ ] 모든 기본 비밀번호 변경
- [ ] DEBUG=false 설정
- [ ] ALLOWED_HOSTS 제한
- [ ] 불필요한 포트 차단 (보안 그룹)
- [ ] SSL Labs 테스트: https://www.ssllabs.com/ssltest/
