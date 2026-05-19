"""Top-level FastAPI app smoke tests (root, healthz, CORS)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_root_returns_app_metadata():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"app": "La Cabrona", "status": "ok"}


def test_healthz_returns_ok():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allowed_origin_echoed_back():
    with TestClient(app) as client:
        response = client.options(
            "/healthz",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_app_metadata_title_and_version():
    assert app.title == "La Cabrona API"
    assert app.version == "1.0.0"


def test_all_routers_mounted():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/v1/categories" in paths
    assert "/api/v1/menu" in paths
    assert "/api/v1/inventory" in paths
    assert "/api/v1/orders" in paths
    assert "/api/v1/reservations" in paths
    assert "/api/v1/health/supertokens" in paths
