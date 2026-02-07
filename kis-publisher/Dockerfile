# kis-publisher/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 네트워크 통신을 위한 최소 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from official image (much faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY kis-publisher/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

COPY kis-publisher/main.py .
COPY kis-publisher/fetch_symbols.py .
COPY kis-publisher/companies_data.csv .
COPY kis-publisher/mock_server.py .
COPY kis-publisher/subscription_handler.py .

CMD ["python", "main.py"]