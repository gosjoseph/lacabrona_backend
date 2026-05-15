from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import categories, inventory, menu, orders, reservations

app = FastAPI(title="La Cabrona API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(categories.router)
app.include_router(menu.router)
app.include_router(inventory.router)
app.include_router(orders.router)
app.include_router(reservations.router)


@app.get("/")
def root():
    return {"app": "La Cabrona", "status": "ok"}


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
