FROM nginx:latest

# OpenSSL 설치 (더미 인증서 생성용)
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

# 템플릿 파일 복사
COPY deploy/app/nginx/conf.d/default.conf.template /etc/nginx/templates/default.conf.template

# 커스텀 entrypoint 스크립트 복사
COPY deploy/app/nginx/docker-entrypoint.sh /docker-entrypoint-wrapper.sh
RUN chmod +x /docker-entrypoint-wrapper.sh

# nginx 공식 이미지는 /etc/nginx/templates/*.template 파일을
# 자동으로 envsubst로 처리하여 /etc/nginx/conf.d/에 생성합니다.

# 환경변수 치환 대상 (nginx 변수 $host 등은 보호)
ENV NGINX_ENVSUBST_FILTER=MONITORING_HOST|DATA_HOST|DOMAIN

# 기본값 설정 (docker-compose에서 override 가능)
ENV MONITORING_HOST=host.docker.internal
ENV DATA_HOST=host.docker.internal
ENV DOMAIN=localhost

# 커스텀 entrypoint 사용
ENTRYPOINT ["/docker-entrypoint-wrapper.sh"]
CMD ["nginx", "-g", "daemon off;"]
