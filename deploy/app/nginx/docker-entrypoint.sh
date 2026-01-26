#!/bin/sh
set -e

# =============================================================================
# Nginx 시작 전 SSL 인증서 확인 및 더미 인증서 생성
# =============================================================================

CERT_PATH="/etc/letsencrypt/live/${DOMAIN}"

# 인증서 디렉토리 및 파일 확인
if [ ! -f "${CERT_PATH}/fullchain.pem" ] || [ ! -f "${CERT_PATH}/privkey.pem" ]; then
    echo "=== SSL 인증서가 없습니다. 더미 인증서를 생성합니다... ==="

    # 디렉토리 생성
    mkdir -p "${CERT_PATH}"

    # 자체 서명 인증서 생성 (nginx 시작용)
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
        -keyout "${CERT_PATH}/privkey.pem" \
        -out "${CERT_PATH}/fullchain.pem" \
        -subj "/CN=localhost"

    echo "=== 더미 인증서 생성 완료 ==="
    echo "주의: 실제 HTTPS 서비스를 위해서는 init-letsencrypt.sh를 실행하세요."
else
    echo "=== SSL 인증서가 존재합니다 ==="
fi

# 기본 nginx entrypoint 실행
exec /docker-entrypoint.sh "$@"
