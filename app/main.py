import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.auth.controller import router as auth_router
from app.modules.auth.supertokens import init_supertokens
from app.modules.categories.controller import router as categories_router
from app.modules.health.controller import router as health_router
from app.modules.inventory.controller import router as inventory_router
from app.modules.menu.controller import router as menu_router
from app.modules.orders.controller import router as orders_router
from app.modules.reservations.controller import router as reservations_router

# Initialise SuperTokens before FastAPI is constructed. No-op when
# ENVIRONMENT=test so the test suite doesn't need a real core.
init_supertokens()

app = FastAPI(title="La Cabrona API", version="1.0.0")

# Mount the SuperTokens ASGI middleware in non-test environments.
if os.getenv("ENVIRONMENT") != "test":
    from supertokens_python.exceptions import SuperTokensError
    from supertokens_python.framework.fastapi import get_middleware

    app.add_middleware(get_middleware())

    @app.exception_handler(SuperTokensError)
    async def supertokens_error_handler(request, exc: SuperTokensError):  # noqa: ARG001
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=500, content={"detail": "Authentication error"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(categories_router)
app.include_router(menu_router)
app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(reservations_router)
app.include_router(auth_router)
app.include_router(health_router)


@app.get("/")
def root():
    return {"app": "La Cabrona", "status": "ok"}


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
