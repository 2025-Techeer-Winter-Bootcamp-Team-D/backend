FROM python:3.11-alpine

WORKDIR /app

# PostgreSQL C 라이브러리 및 빌드 도구 설치
RUN apk add --no-cache postgresql-dev gcc musl-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# 로그 즉시 출력을 위해 환경변수 설정
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]