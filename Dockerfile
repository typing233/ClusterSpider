FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -e .

COPY . .

FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "clusterspider.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["celery", "-A", "clusterspider.workers.celery_app", "worker", "-Q", "scans,reports", "--loglevel=info", "-c", "4"]
