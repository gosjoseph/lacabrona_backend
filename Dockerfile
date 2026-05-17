# ---------------------------------------------------------------------------
# Base: shared dependencies for both dev and prod
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash appuser

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

EXPOSE 8000

# ---------------------------------------------------------------------------
# Development: source is bind-mounted (see docker-compose.dev.yml) and
# uvicorn --reload restarts the server whenever a file under app/ changes.
# ---------------------------------------------------------------------------
FROM base AS dev

ENV ENVIRONMENT=development

USER appuser

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "app"]

# ---------------------------------------------------------------------------
# Production: source is baked into the image so the container is immutable
# and stable. This is the target Coolify builds.
# ---------------------------------------------------------------------------
FROM base AS prod

ENV ENVIRONMENT=production

COPY app ./app
RUN chown -R appuser:appuser /app

USER appuser

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2"]
