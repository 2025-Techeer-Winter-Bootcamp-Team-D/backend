# kis-publisher/Dockerfile
FROM python:3.11-alpine

WORKDIR /app

# 네트워크 통신을 위한 최소 의존성 설치
RUN apk add --no-cache gcc musl-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY fetch_symbols.py .
COPY companies_data.csv .

CMD ["python", "main.py"]