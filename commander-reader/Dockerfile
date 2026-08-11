FROM python:3.12-slim

WORKDIR /app

# curl is needed for the container healthcheck (docker-compose.yml)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Data directory for SQLite price history
RUN mkdir -p /app/data

EXPOSE 8200

# PORT is configurable via env var (defaults to 8200)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8200}"]
