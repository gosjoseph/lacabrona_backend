import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.supertokens_init import init_supertokens
from .config import settings
from .routers import categories, health, inventory, menu, orders, reservations

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

app.include_router(categories.router)
app.include_router(menu.router)
app.include_router(inventory.router)
app.include_router(orders.router)
app.include_router(reservations.router)
app.include_router(health.router)


@app.get("/")
def root():
    return {"app": "La Cabrona", "status": "ok"}


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
