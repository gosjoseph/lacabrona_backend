import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.modules.auth.controller import router as auth_router
from app.modules.auth.supertokens import init_supertokens
from app.modules.categories.controller import router as categories_router
from app.modules.customers.controller import router as customers_router
from app.modules.health.controller import router as health_router
from app.modules.inventory.controller import router as inventory_router
from app.modules.menu.controller import router as menu_router
from app.modules.orders.controller import router as orders_router
from app.modules.reservations.controller import router as reservations_router
from app.modules.uploads.controller import router as uploads_router

# Initialise SuperTokens before FastAPI is constructed. No-op when
# ENVIRONMENT=test so the test suite doesn't need a real core.
init_supertokens()

app = FastAPI(title="La Cabrona API", version="1.0.0")

# Mount the SuperTokens ASGI middleware in non-test environments. The
# middleware translates session errors into the correct 401/403 responses, so
# we deliberately register NO app-level handler for SuperTokensError or its
# session subclasses (UnauthorisedError, TryRefreshTokenError,
# InvalidClaimsError, ClaimValidationError). A blanket SuperTokensError->500
# handler here would shadow that translation and turn every unauthenticated
# request into a 500 — see tests/test_session_error_translation.py.
if os.getenv("ENVIRONMENT") != "test":
    from supertokens_python.framework.fastapi import get_middleware

    app.add_middleware(get_middleware())

# Credentialed CORS requires explicit origins — never "*" — so the ops console
# can send the SuperTokens session cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(categories_router)
app.include_router(menu_router)
app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(reservations_router)
app.include_router(customers_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(uploads_router)

os.makedirs(os.path.join(settings.media_dir, "menu"), exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")


@app.get("/")
def root():
    return {"app": "La Cabrona", "status": "ok"}


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
