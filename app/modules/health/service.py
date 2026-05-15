"""Health probes for external dependencies."""

from __future__ import annotations

import httpx

from app.core.config import settings


class HealthService:
    async def supertokens_status(self) -> tuple[int, dict]:
        url = f"{settings.supertokens_core_url.rstrip('/')}/hello"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            return 503, {"status": "unavailable", "detail": str(exc)}

        if response.status_code == 200:
            return 200, {"status": "ok"}

        return 503, {"status": "unavailable", "upstream_status": response.status_code}
