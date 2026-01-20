FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from official image (much faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY requirements.txt /app/

# Install Python dependencies using uv (much faster than pip)
RUN uv pip install --system --no-cache -r requirements.txt

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
COPY sankeys/ /app/sankeys/

# Daphne ASGI 서버 (WebSocket 지원)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]