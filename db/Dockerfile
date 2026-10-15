FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

RUN pip install --no-cache-dir "psycopg[binary]>=3.1"

COPY bootstrap.py .

CMD ["python", "bootstrap.py"]
