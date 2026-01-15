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

COPY . /app/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]