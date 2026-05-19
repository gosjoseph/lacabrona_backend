"""Auth routes.

`GET /api/v1/auth/me` returns the identity of the SuperTokens-authenticated
caller so the SPA can rebuild its auth state on every page load.
"""

import os

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _make_session_dependency():
    """`verify_session()` in normal runs; a 401-raising stub under ENVIRONMENT=test.

    The SuperTokens core is never reachable in tests (init is a no-op), so the
    real `verify_session()` cannot run there. Tests override this dependency to
    inject a session; when they don't, the stub denies the request — which is
    the correct outcome for the "no session" case.
    """
    if os.getenv("ENVIRONMENT") == "test":

        async def _session_unavailable():
            raise HTTPException(status_code=401, detail="unauthorised")

        return _session_unavailable

    from supertokens_python.recipe.session.framework.fastapi import verify_session

    return verify_session()


# Module-level singleton so tests can target it via app.dependency_overrides.
_session_dep = _make_session_dependency()


def get_service() -> AuthService:
    return AuthService.from_db(get_db())


@router.get("/me")
async def me(
    session=Depends(_session_dep),
    service: AuthService = Depends(get_service),
) -> dict:
    """Return the authenticated caller's identity for SPA session rehydration."""
    user_id = session.get_user_id()
    resolved = service.resolve_session_user(user_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail="user not found")

    doc = resolved["doc"]
    return {
        "user_id": user_id,
        "email": doc.get("email"),
        "user_type": resolved["user_type"],
        "first_name": doc.get("first_name"),
        "last_name": doc.get("last_name"),
    }
