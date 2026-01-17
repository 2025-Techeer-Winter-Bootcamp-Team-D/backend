FROM python:3.12-alpine

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    postgresql-dev \
    curl \
    && apk add --no-cache --virtual .build-deps \
    gcc \
    g++ \
    musl-dev \
    pkgconfig

# Copy uv from official image (much faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY requirements.txt /app/

# Install Python dependencies using uv (much faster than pip)
RUN uv pip install --system --no-cache -r requirements.txt

# Remove build dependencies
RUN apk del .build-deps

# Copy application code (자주 변경되는 파일은 마지막에 복사하여 레이어 캐싱 최적화)
# 자주 변경되지 않는 파일들을 먼저 복사
COPY manage.py /app/
COPY config/ /app/config/
COPY companies/ /app/companies/
COPY comparisons/ /app/comparisons/
COPY core/ /app/core/
COPY industries/ /app/industries/
COPY indices/ /app/indices/
COPY news/ /app/news/
COPY users/ /app/users/

# Daphne ASGI 서버 (WebSocket 지원)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]