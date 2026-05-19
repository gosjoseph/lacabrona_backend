"""Endpoint-versioning contract tests.

Verifies the business CRUD routers and the new auth endpoint are exposed under
`/api/v1/*`, that the old unversioned `/api/*` paths no longer exist, and that
`GET /api/v1/auth/me` is gated by a SuperTokens session.
"""

from __future__ import annotations

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth import controller as auth_ctrl
from app.modules.auth.service import AuthService

V1_PATHS = [
    "/api/v1/categories",
    "/api/v1/categories/{category_id}",
    "/api/v1/inventory",
    "/api/v1/inventory/{item_id}",
    "/api/v1/inventory/{item_id}/adjust",
    "/api/v1/menu",
    "/api/v1/menu/{item_id}",
    "/api/v1/orders",
    "/api/v1/orders/{order_id}",
    "/api/v1/orders/{order_id}/status",
    "/api/v1/reservations",
    "/api/v1/reservations/{reservation_id}",
    "/api/v1/auth/me",
    "/api/v1/health/supertokens",
    "/healthz",
]

STALE_PATHS = [
    "/api/categories",
    "/api/categories/{category_id}",
    "/api/inventory",
    "/api/inventory/{item_id}",
    "/api/inventory/{item_id}/adjust",
    "/api/menu",
    "/api/menu/{item_id}",
    "/api/orders",
    "/api/orders/{order_id}",
    "/api/orders/{order_id}/status",
    "/api/reservations",
    "/api/reservations/{reservation_id}",
]

EXPECTED_ME_KEYS = {"user_id", "email", "user_type", "first_name", "last_name"}


def _openapi_paths() -> set[str]:
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    return set(response.json()["paths"].keys())


# ---- T-B1 / T-B2: OpenAPI path inventory ----------------------------------

def test_openapi_exposes_all_v1_paths():
    paths = _openapi_paths()
    missing = [p for p in V1_PATHS if p not in paths]
    assert not missing, f"expected paths missing from OpenAPI: {missing}"


def test_openapi_has_no_unversioned_paths():
    paths = _openapi_paths()
    leftover = [p for p in STALE_PATHS if p in paths]
    assert not leftover, f"stale unversioned paths still in OpenAPI: {leftover}"


# ---- T-B3 / T-B4: GET /api/v1/auth/me -------------------------------------

@pytest.fixture
def auth_client(mongo_test_db):
    """Bind the auth router's AuthService to a mongomock database.

    Yields the test database. Cleans up both the service override and any
    fake-session override installed via `_login_as`.
    """

    def _service() -> AuthService:
        return AuthService.from_db(mongo_test_db)

    app.dependency_overrides[auth_ctrl.get_service] = _service
    try:
        yield mongo_test_db
    finally:
        app.dependency_overrides.pop(auth_ctrl.get_service, None)
        app.dependency_overrides.pop(auth_ctrl._session_dep, None)


def _login_as(user_id: str) -> None:
    """Override the session dependency with a stub container for `user_id`."""

    class _FakeSession:
        def get_user_id(self) -> str:
            return user_id

    app.dependency_overrides[auth_ctrl._session_dep] = lambda: _FakeSession()


def test_auth_me_without_session_returns_401():
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_auth_me_with_session_returns_customer_profile(auth_client):
    auth_client.customers.insert_one({
        "_id": ObjectId(),
        "email": "cliente@lacabrona.uy",
        "first_name": "Clienta",
        "last_name": "Prueba",
        "supertokens_user_id": "st-customer-1",
    })
    _login_as("st-customer-1")

    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == EXPECTED_ME_KEYS
    assert body["user_type"] in {"customer", "employee"}
    assert body["user_type"] == "customer"
    assert body["user_id"] == "st-customer-1"
    assert body["email"] == "cliente@lacabrona.uy"
    assert body["first_name"] == "Clienta"
    assert body["last_name"] == "Prueba"


def test_auth_me_with_session_returns_employee_profile(auth_client):
    auth_client.employees.insert_one({
        "_id": ObjectId(),
        "email": "staff@lacabrona.uy",
        "name": "Staff Uno",
        "role": "admin",
        "supertokens_user_id": "st-employee-1",
    })
    _login_as("st-employee-1")

    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == EXPECTED_ME_KEYS
    assert body["user_type"] == "employee"
    assert body["email"] == "staff@lacabrona.uy"
    # Employee documents carry no first/last name — these come back null.
    assert body["first_name"] is None
    assert body["last_name"] is None


def test_auth_me_session_without_matching_record_returns_404(auth_client):
    _login_as("st-unlinked-user")  # no customer/employee linked to this id

    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 404
    assert response.json() == {"detail": "user not found"}
