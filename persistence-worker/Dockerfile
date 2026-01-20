FROM python:3.11-alpine

WORKDIR /app

# PostgreSQL C 라이브러리 및 빌드 도구 설치
RUN apk add --no-cache postgresql-dev gcc musl-dev

# Copy uv from official image (much faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY persistence-worker/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY persistence-worker/main.py .

# 로그 즉시 출력을 위해 환경변수 설정
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]