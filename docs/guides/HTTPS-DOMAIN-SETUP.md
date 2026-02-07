# HTTPS 및 도메인 설정 가이드

이 문서는 배포 서버에 HTTPS를 설정하고, 도메인(quasa.info)을 프론트엔드(Vercel)와 백엔드(EC2) 모두에서 사용하는 방법을 설명합니다.

## 목차

1. [도메인 구성 전략](#1-도메인-구성-전략)
2. [DNS 설정](#2-dns-설정)
3. [백엔드 HTTPS 설정 (Let's Encrypt)](#3-백엔드-https-설정-lets-encrypt)
4. [Vercel 프론트엔드 도메인 연결](#4-vercel-프론트엔드-도메인-연결)
5. [Nginx 설정 업데이트](#5-nginx-설정-업데이트)

---

## 1. 도메인 구성 전략

### 권장 구성: 서브도메인 분리

| 도메인 | 용도 | 호스팅 |
|--------|------|--------|
| `quasa.info` | 프론트엔드 | Vercel |
| `www.quasa.info` | 프론트엔드 (리다이렉트) | Vercel |
| `api.quasa.info` | 백엔드 API | EC2 (Nginx) |

### 장점
- 프론트엔드와 백엔드가 독립적으로 배포/확장 가능
- CORS 설정이 명확함
- SSL 인증서 관리가 분리됨

---

## 2. DNS 설정 (GCP Cloud DNS)

GCP Cloud DNS에서 DNS 레코드를 설정합니다.

### 2.1. GCP Console에서 DNS 레코드 추가

1. [GCP Console](https://console.cloud.google.com/) 접속
2. **네트워크 서비스** → **Cloud DNS** 이동
3. `quasa.info` 영역 선택
4. **레코드 세트 추가** 클릭

### 2.2. 필요한 DNS 레코드

| DNS 이름 | 유형 | TTL | 데이터 |
|----------|------|-----|--------|
| `quasa.info.` | A | 300 | 76.76.21.21 |
| `www.quasa.info.` | CNAME | 300 | cname.vercel-dns.com. |
| `api.quasa.info.` | A | 300 | `<EC2_PUBLIC_IP>` |

### 2.3. gcloud CLI로 레코드 추가

```bash
# 프론트엔드 (Vercel) - A 레코드
gcloud dns record-sets create quasa.info. \
  --zone=quasa-info \
  --type=A \
  --ttl=300 \
  --rrdatas=76.76.21.21

# 프론트엔드 (Vercel) - www CNAME
gcloud dns record-sets create www.quasa.info. \
  --zone=quasa-info \
  --type=CNAME \
  --ttl=300 \
  --rrdatas=cname.vercel-dns.com.

# 백엔드 (EC2) - api 서브도메인
gcloud dns record-sets create api.quasa.info. \
  --zone=quasa-info \
  --type=A \
  --ttl=300 \
  --rrdatas=<EC2_PUBLIC_IP>
```

### 2.4. DNS 전파 확인

```bash
# DNS 레코드 확인
dig quasa.info
dig www.quasa.info
dig api.quasa.info

# 또는 nslookup
nslookup api.quasa.info
```

> **참고**: DNS 전파에는 최대 48시간이 걸릴 수 있지만, 보통 몇 분 내에 완료됩니다.

---

## 3. 백엔드 HTTPS 설정 (Let's Encrypt)

### 3.1. 사전 준비

EC2 인스턴스에 SSH 접속:

```bash
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

### 3.2. Certbot 설치

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y certbot
```

### 3.3. SSL 인증서 발급

#### 방법 A: Standalone 모드 (Nginx 중지 필요)

```bash
# Nginx 컨테이너 중지
cd ~/techeer-deploy/deploy/app
docker compose stop nginx

# 인증서 발급
sudo certbot certonly --standalone -d api.quasa.info

# Nginx 재시작
docker compose start nginx
```

#### 방법 B: Webroot 모드 (Nginx 중지 불필요) - 권장

1. Nginx 설정에 인증용 경로 추가 (이미 설정됨):

```nginx
location /.well-known/acme-challenge/ {
    root /var/www/certbot;
}
```

2. 인증서 발급:

```bash
# certbot 디렉토리 생성
sudo mkdir -p /var/www/certbot

# 인증서 발급
sudo certbot certonly --webroot -w /var/www/certbot -d api.quasa.info
```

### 3.4. 인증서 파일 위치

발급된 인증서는 다음 경로에 저장됩니다:

```
/etc/letsencrypt/live/api.quasa.info/
├── fullchain.pem   # 인증서 + 체인
├── privkey.pem     # 개인 키
├── cert.pem        # 인증서
└── chain.pem       # 체인
```

### 3.5. Docker Compose 수정

`deploy/app/docker-compose.yml`에서 nginx 서비스에 인증서 볼륨 추가:

```yaml
nginx:
  build:
    context: ../..
    dockerfile: ./deploy/app/nginx/Dockerfile
  container_name: nginx
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ../../static:/app/static
    - ../../media:/app/media
    # SSL 인증서 마운트
    - /etc/letsencrypt:/etc/letsencrypt:ro
    - /var/www/certbot:/var/www/certbot:ro
  # ... 나머지 설정
```

### 3.6. Nginx HTTPS 설정

`deploy/app/nginx/conf.d/default.conf.template` 수정:

```nginx
# HTTP -> HTTPS 리다이렉트
server {
    listen 80;
    server_name api.quasa.info;

    # Let's Encrypt 인증용
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # 나머지는 HTTPS로 리다이렉트
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS 서버
server {
    listen 443 ssl http2;
    server_name api.quasa.info;

    # SSL 인증서
    ssl_certificate /etc/letsencrypt/live/api.quasa.info/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.quasa.info/privkey.pem;

    # SSL 보안 설정
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # HSTS (선택사항)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Docker 내부 DNS 서버
    resolver 127.0.0.11 valid=30s;

    # 공통 Proxy 헤더 설정
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Django API
    location / {
        proxy_pass http://backend_server;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://backend_server;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # 정적 파일
    location /static/ {
        alias /app/static/;
    }

    location /media/ {
        alias /app/media/;
    }
}
```

### 3.7. 인증서 자동 갱신 설정

Let's Encrypt 인증서는 90일마다 만료됩니다. 자동 갱신을 설정하세요:

```bash
# 갱신 테스트
sudo certbot renew --dry-run

# cron 작업 추가 (하루 2번 갱신 시도)
sudo crontab -e
```

crontab에 추가:

```cron
0 0,12 * * * certbot renew --quiet --post-hook "docker restart nginx"
```

---

## 4. Vercel 프론트엔드 도메인 연결

### 4.1. Vercel 프로젝트 설정

1. [Vercel Dashboard](https://vercel.com/dashboard) 접속
2. 프론트엔드 프로젝트 선택
3. **Settings** → **Domains** 이동

### 4.2. 도메인 추가

1. `quasa.info` 입력 후 **Add** 클릭
2. `www.quasa.info` 입력 후 **Add** 클릭 (www 리다이렉트용)

### 4.3. DNS 검증

Vercel이 제시하는 DNS 레코드를 도메인 등록 업체에 추가:

```
quasa.info          A       76.76.21.21
www.quasa.info      CNAME   cname.vercel-dns.com.
```

### 4.4. SSL 자동 설정

Vercel은 도메인 연결 시 자동으로 SSL 인증서를 발급합니다. 별도 설정 불필요.

### 4.5. 환경 변수 설정

Vercel 프로젝트의 환경 변수에서 백엔드 API URL 설정:

```
NEXT_PUBLIC_API_URL=https://api.quasa.info
```

---

## 5. Nginx 설정 업데이트

### 5.1. 전체 Nginx 설정 예시

`deploy/app/nginx/conf.d/default.conf.template`:

```nginx
# =============================================================================
# Upstream 정의
# =============================================================================

upstream backend_server {
    server app:8000;
}

upstream flower_server {
    server flower:5555;
}

# =============================================================================
# HTTP -> HTTPS 리다이렉트
# =============================================================================
server {
    listen 80;
    server_name api.quasa.info;

    # Let's Encrypt 인증용
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # HTTPS로 리다이렉트
    location / {
        return 301 https://$host$request_uri;
    }
}

# =============================================================================
# HTTPS 메인 서버
# =============================================================================
server {
    listen 443 ssl http2;
    server_name api.quasa.info;

    # SSL 인증서
    ssl_certificate /etc/letsencrypt/live/api.quasa.info/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.quasa.info/privkey.pem;

    # SSL 보안 설정
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Docker DNS
    resolver 127.0.0.11 valid=30s;

    # 공통 헤더
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # =========================================================================
    # API 라우팅
    # =========================================================================

    # Django API
    location / {
        proxy_pass http://backend_server;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://backend_server;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # Celery Flower
    location /celery-flower/ {
        proxy_pass http://flower_server;
    }

    # 정적 파일
    location /static/ {
        alias /app/static/;
    }

    location /media/ {
        alias /app/media/;
    }

    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}

# =============================================================================
# 내부 전용 (localhost)
# =============================================================================
server {
    listen 80;
    server_name localhost;

    resolver 127.0.0.11 valid=30s;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    location / {
        proxy_pass http://backend_server;
    }

    location /stub_status {
        stub_status;
        allow 127.0.0.1;
        deny all;
    }

    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

---

## 6. CORS 설정 (Django)

프론트엔드와 백엔드가 다른 도메인을 사용하므로 CORS 설정이 필요합니다.

### 6.1. django-cors-headers 설치

```bash
pip install django-cors-headers
```

### 6.2. settings.py 설정

```python
INSTALLED_APPS = [
    # ...
    'corsheaders',
    # ...
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # 가장 위에 추가
    'django.middleware.common.CommonMiddleware',
    # ...
]

# 허용할 도메인
CORS_ALLOWED_ORIGINS = [
    "https://quasa.info",
    "https://www.quasa.info",
]

# 개발 환경에서는 localhost도 허용
if DEBUG:
    CORS_ALLOWED_ORIGINS += [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

# 인증 정보(쿠키) 전송 허용
CORS_ALLOW_CREDENTIALS = True
```

---

## 7. 체크리스트

### 배포 전 확인사항

- [ ] DNS 레코드 설정 완료
- [ ] EC2 보안 그룹에서 443 포트 허용
- [ ] Let's Encrypt 인증서 발급 완료
- [ ] Nginx HTTPS 설정 완료
- [ ] Docker Compose에 인증서 볼륨 마운트
- [ ] Vercel 도메인 연결 완료
- [ ] CORS 설정 완료
- [ ] 인증서 자동 갱신 cron 설정

### 테스트

```bash
# HTTPS 연결 테스트
curl -I https://api.quasa.info/health

# SSL 인증서 확인
openssl s_client -connect api.quasa.info:443 -servername api.quasa.info

# 프론트엔드에서 API 호출 테스트
curl -I https://quasa.info
```

---

## 8. 문제 해결

### 인증서 발급 실패

```bash
# 로그 확인
sudo cat /var/log/letsencrypt/letsencrypt.log

# DNS 전파 확인
dig api.quasa.info

# 80 포트 접근 가능 확인
curl http://api.quasa.info/.well-known/acme-challenge/test
```

### Nginx 시작 실패 (인증서 없음)

인증서가 없는 상태에서 HTTPS 설정을 하면 Nginx가 시작되지 않습니다.

1. 먼저 HTTP only 설정으로 Nginx 시작
2. 인증서 발급
3. HTTPS 설정 추가 후 Nginx 재시작

### Mixed Content 에러

프론트엔드(HTTPS)에서 백엔드(HTTP)로 요청 시 발생합니다.
- 백엔드도 반드시 HTTPS로 설정해야 합니다.

---

## 9. 참고 자료

- [Let's Encrypt 공식 문서](https://letsencrypt.org/docs/)
- [Certbot 공식 문서](https://certbot.eff.org/)
- [Vercel 도메인 설정](https://vercel.com/docs/projects/domains)
- [Nginx SSL 설정 가이드](https://nginx.org/en/docs/http/configuring_https_servers.html)
