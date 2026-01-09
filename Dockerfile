FROM python:3.11-alpine

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    postgresql-dev \
    curl \
    && apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    pkgconfig

COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Remove build dependencies
RUN apk del .build-deps

COPY . /app/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]