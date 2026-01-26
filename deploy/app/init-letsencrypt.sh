#!/bin/bash

# =============================================================================
# Let's Encrypt 초기 인증서 발급 스크립트
# 사용법: cd deploy/app && ./init-letsencrypt.sh
# =============================================================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Let's Encrypt SSL 인증서 발급 ===${NC}"

# .env 파일에서 환경변수 로드
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 도메인 확인
if [ -z "$DOMAIN" ]; then
    echo -e "${RED}오류: DOMAIN 환경변수가 설정되지 않았습니다.${NC}"
    echo ""
    echo "방법 1: .env 파일에 DOMAIN 추가"
    echo "  echo 'DOMAIN=example.com' >> .env"
    echo ""
    echo "방법 2: 직접 지정"
    echo "  DOMAIN=example.com ./init-letsencrypt.sh"
    exit 1
fi

# 이메일 확인
if [ -z "$CERTBOT_EMAIL" ]; then
    echo -e "${YELLOW}알림: CERTBOT_EMAIL이 설정되지 않았습니다.${NC}"
    echo "인증서 만료 알림을 받으려면 이메일을 설정하세요."
    read -p "이메일 주소 입력 (생략하려면 Enter): " CERTBOT_EMAIL
fi

echo ""
echo "도메인: $DOMAIN"
echo "이메일: ${CERTBOT_EMAIL:-없음 (알림 비활성화)}"
echo ""

# -----------------------------------------------------------------------------
# 1. 디렉토리 생성
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[1/6] 디렉토리 생성...${NC}"
mkdir -p ./certbot/conf
mkdir -p ./certbot/www

# -----------------------------------------------------------------------------
# 2. 기존 컨테이너 정리
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[2/6] 기존 컨테이너 정리...${NC}"
docker compose down nginx certbot 2>/dev/null || true

# -----------------------------------------------------------------------------
# 3. 임시(더미) 인증서 생성 (nginx 시작용)
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[3/6] 임시 인증서 생성...${NC}"
if [ ! -d "./certbot/conf/live/$DOMAIN" ]; then
    mkdir -p "./certbot/conf/live/$DOMAIN"

    # OpenSSL로 자체 서명 인증서 생성
    docker run --rm \
        -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
        alpine/openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
        -keyout "/etc/letsencrypt/live/$DOMAIN/privkey.pem" \
        -out "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" \
        -subj "/CN=localhost"

    echo "임시 인증서 생성 완료"
else
    echo "기존 인증서 디렉토리 존재 - 건너뜀"
fi

# -----------------------------------------------------------------------------
# 4. Nginx 시작 (HTTP 모드)
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[4/6] Nginx 시작 (ACME 챌린지용)...${NC}"
docker compose up -d nginx
sleep 5  # Nginx 시작 대기

# HTTP 연결 테스트
echo "HTTP 연결 테스트 중..."
if curl -sf "http://${DOMAIN}/.well-known/acme-challenge/test" > /dev/null 2>&1 || \
   curl -sf "http://${DOMAIN}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}HTTP 연결 성공!${NC}"
else
    echo -e "${YELLOW}경고: HTTP 연결 테스트 실패 (DNS 전파 대기 중일 수 있음)${NC}"
fi

# -----------------------------------------------------------------------------
# 5. 실제 인증서 발급
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[5/6] Let's Encrypt 인증서 발급...${NC}"

# 임시 인증서 삭제
rm -rf "./certbot/conf/live/$DOMAIN"
rm -rf "./certbot/conf/archive/$DOMAIN"
rm -rf "./certbot/conf/renewal/$DOMAIN.conf"

# 이메일 옵션
if [ -n "$CERTBOT_EMAIL" ]; then
    EMAIL_ARG="--email $CERTBOT_EMAIL"
else
    EMAIL_ARG="--register-unsafely-without-email"
fi

# 스테이징 모드 확인 (테스트용)
if [ "$STAGING" = "1" ]; then
    echo "스테이징 모드로 실행 (테스트용)"
    STAGING_ARG="--staging"
else
    STAGING_ARG=""
fi

# Certbot 실행
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    $EMAIL_ARG \
    $STAGING_ARG \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

# 발급 결과 확인
if [ $? -ne 0 ]; then
    echo -e "${RED}인증서 발급 실패!${NC}"
    echo ""
    echo "확인 사항:"
    echo "  1. DNS 설정이 올바른지 확인: dig +short $DOMAIN"
    echo "  2. 80 포트가 열려있는지 확인 (보안 그룹)"
    echo "  3. 도메인이 서버 IP를 가리키는지 확인"
    echo ""
    echo "테스트 모드로 먼저 시도하려면:"
    echo "  STAGING=1 ./init-letsencrypt.sh"
    exit 1
fi

# -----------------------------------------------------------------------------
# 6. Nginx 재시작 (HTTPS 모드)
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[6/6] Nginx 재시작 (HTTPS 활성화)...${NC}"
docker compose restart nginx

echo ""
echo -e "${GREEN}=== 인증서 발급 완료! ===${NC}"
echo ""
echo "접속 URL:"
echo "  - API: https://$DOMAIN/api/"
echo "  - Swagger: https://$DOMAIN/api/schema/swagger-ui/"
echo "  - Grafana: https://$DOMAIN/grafana/"
echo "  - Flower: https://$DOMAIN/celery-flower/"
echo ""
echo "인증서 정보 확인:"
echo "  docker compose run --rm certbot certificates"
echo ""
echo "인증서는 자동으로 갱신됩니다 (certbot 컨테이너가 12시간마다 확인)"
