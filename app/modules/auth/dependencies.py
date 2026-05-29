"""Reusable auth dependencies for gating ops write endpoints.

`require_employee` is applied as a route dependency to every mutating business
route so only an employee with a live SuperTokens session can reach them.

The session is read through `controller._session_dep` — the same singleton the
existing tests override — and the employee lookup goes through
`get_auth_service()`, a DB-backed provider tests can override to a mongomock db.
"""

from fastapi import Depends, HTTPException

from app.core.database import get_db
from app.modules.auth.controller import _session_dep
from app.modules.auth.service import AuthService


def get_auth_service() -> AuthService:
    """DB-backed `AuthService` provider; overridable in tests."""
    return AuthService.from_db(get_db())


def require_employee(
    session=Depends(_session_dep),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """Require a live SuperTokens session linked to an employee.

    - 401 when there is no session (raised by `_session_dep` itself).
    - 403 when the session resolves to a customer or to no linked record.

    Returns the resolved employee document on success.
    """
    user_id = session.get_user_id()
    resolved = service.resolve_session_user(user_id)
    if resolved is None or resolved["user_type"] != "employee":
        raise HTTPException(status_code=403, detail="forbidden")
    return resolved["doc"]
