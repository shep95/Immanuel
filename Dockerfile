FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for lxml
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Data directory (mount a Railway volume here to persist the DB)
RUN mkdir -p /app/data
ENV DATABASE_PATH=/app/data/immanuel.db

# Railway injects PORT; the FastAPI server binds to it (also satisfies healthchecks)
EXPOSE 8000

CMD ["python", "-m", "immanuel.main"]
