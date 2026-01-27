FROM python:3.11-slim

WORKDIR /app

# PostgreSQL C 라이브러리 및 빌드 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from official image (much faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY persistence-worker/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

COPY persistence-worker/main.py .

# 로그 즉시 출력을 위해 환경변수 설정
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]