# La Cabrona — Backend (FastAPI)

REST API powering the customer website and the operations console.

## Endpoints

- `GET /api/categories` — menu categories
- `GET /api/menu` (optional `?category=`) — menu items
- `GET /api/inventory` — stock items
- `POST /api/inventory/{id}/adjust` — `{ "delta": -1 }` to subtract stock
- `GET /api/orders` (optional `?status=new|preparing|ready|served`)
- `POST /api/orders` — create order
- `PATCH /api/orders/{id}/status` — advance order state
- `GET /api/reservations` (optional `?date=YYYY-MM-DD`)
- `POST /api/reservations` — create reservation

## Env vars

- `MONGO_URL` — Mongo connection string (default `mongodb://localhost:27017`)
- `MONGO_DB` — database name (default `lacabrona`)
- `CORS_ORIGINS` — comma-separated list (default dev origins)

## Run locally

```bash
pip install -r requirements.txt
MONGO_URL=mongodb://localhost:27017 uvicorn app.main:app --reload
```

Or via the combined docker-compose at the frontend repo:

```bash
cd ../lacabrona_frontend && docker compose up --build
```

Then visit http://localhost:5173 (customer site), http://localhost:5173/ops (console)
and http://localhost:8000/docs (API).
