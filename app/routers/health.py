"""Health endpoints, including a SuperTokens core reachability probe."""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/supertokens")
async def supertokens_health() -> JSONResponse:
    """Return 200 if the SuperTokens core responds, 503 otherwise."""
    url = f"{settings.supertokens_core_url.rstrip('/')}/hello"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "detail": str(exc)},
        )

    if response.status_code == 200:
        return JSONResponse(status_code=200, content={"status": "ok"})

    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "upstream_status": response.status_code},
    )
