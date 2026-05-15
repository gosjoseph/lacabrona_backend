"""Health endpoints, including a SuperTokens core reachability probe."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.modules.health.service import HealthService

router = APIRouter(prefix="/api/v1/health", tags=["health"])


def get_service() -> HealthService:
    return HealthService()


@router.get("/supertokens")
async def supertokens_health(
    service: HealthService = Depends(get_service),
) -> JSONResponse:
    """Return 200 if the SuperTokens core responds, 503 otherwise."""
    status_code, body = await service.supertokens_status()
    return JSONResponse(status_code=status_code, content=body)
