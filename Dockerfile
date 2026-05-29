# ---------------------------------------------------------------------------
# Base: shared dependencies for both dev and prod
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash appuser

COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

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

# Coolify's deploy gate runs a curl-based healthcheck INSIDE the container, so
# curl must be present in the prod image. Install it as root before dropping to
# appuser, minimally and without leaving the apt cache behind.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app
RUN chown -R appuser:appuser /app

USER appuser

# Baked-in healthcheck probes /healthz (the static {"status":"ok"} endpoint).
# Kept stdlib-only (urllib) so it does not depend on curl being installed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2"]
