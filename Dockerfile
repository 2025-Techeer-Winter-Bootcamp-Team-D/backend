FROM python:3.11-alpine

WORKDIR /app

COPY requirements.txt /app/

RUN apk add --no-cache mariadb-connector-c-dev \
    && apk add --no-cache --virtual .build-deps gcc musl-dev pkgconfig \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY . /app/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]