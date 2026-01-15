# kis-publisher/Dockerfile
FROM python:3.11-alpine

WORKDIR /app

# 네트워크 통신을 위한 최소 의존성 설치
RUN apk add --no-cache gcc musl-dev

# Copy uv from official image (much faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY main.py .
COPY fetch_symbols.py .
COPY companies_data.csv .
COPY mock_server.py .

CMD ["python", "main.py"]