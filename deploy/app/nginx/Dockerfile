FROM nginx:latest

# 템플릿 파일 복사
COPY deploy/app/nginx/conf.d/default.conf.template /etc/nginx/templates/default.conf.template

# nginx 공식 이미지는 /etc/nginx/templates/*.template 파일을
# 자동으로 envsubst로 처리하여 /etc/nginx/conf.d/에 생성합니다.

# 환경변수 치환 대상 (nginx 변수 $host 등은 보호)
ENV NGINX_ENVSUBST_FILTER=MONITORING_HOST|DATA_HOST|DOMAIN

# 기본값 설정 (docker-compose에서 override 가능)
ENV MONITORING_HOST=host.docker.internal
ENV DATA_HOST=host.docker.internal
ENV DOMAIN=localhost
