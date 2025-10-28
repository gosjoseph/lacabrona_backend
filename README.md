# Lacabrona Backup API

Minimal FastAPI backend + React frontend runnable with Docker Compose.

## Prerequisites

- Docker engine via Rancher Desktop (or Docker Desktop)
- Git repo checked out locally

## How to run

1. From the repo root:
   docker compose up --build
2. Open the Frontend:
   - App: http://localhost:3000/
3. Open the API:
   - Root: http://localhost:8000/
   - Docs (Swagger UI): http://localhost:8000/docs
   - Health: http://localhost:8000/healthz

## Development tips

- The service runs with Uvicorn --reload and mounts ./app into the container for hot reloads.
- To stop:
  docker compose down
 - Compose expects the frontend at a sibling path: ../lacabrona-frontend

## Project layout

- app/main.py: FastAPI application entrypoint (app.main:app)
- requirements.txt: Python dependencies
- Dockerfile: Backend container build instructions
- docker-compose.yml: Local dev runtime configuration (backend + frontend)
- lacabrona-frontend: React + MUI app (sibling folder to this backend, path: ../lacabrona-frontend)
