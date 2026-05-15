"""End-to-end tests for the inventory router (controller + service + repo)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _payload(**overrides) -> dict:
    base = {
        "id": "tomate",
        "name": "Tomate",
        "category": "verduras",
        "stock": 10.0,
        "unit": "kg",
        "min": 5.0,
        "supplier": "Granja",
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def test_list_empty(api_client):
    client, _ = api_client
    response = client.get("/api/inventory")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_create_then_get(api_client):
    client, _ = api_client
    create = client.post("/api/inventory", json=_payload())
    assert create.status_code == 201
    fetch = client.get("/api/inventory/tomate")
    assert fetch.status_code == 200
    assert fetch.json()["name"] == "Tomate"


def test_create_duplicate_returns_409(api_client):
    client, _ = api_client
    client.post("/api/inventory", json=_payload())
    second = client.post("/api/inventory", json=_payload())
    assert second.status_code == 409


def test_get_missing_returns_404(api_client):
    client, _ = api_client
    assert client.get("/api/inventory/none").status_code == 404


def test_update_partial(api_client):
    client, _ = api_client
    client.post("/api/inventory", json=_payload())
    response = client.put("/api/inventory/tomate", json={"supplier": "Nueva Granja"})
    assert response.status_code == 200
    body = response.json()
    assert body["supplier"] == "Nueva Granja"


def test_update_with_no_fields_returns_400(api_client):
    client, _ = api_client
    client.post("/api/inventory", json=_payload())
    response = client.put("/api/inventory/tomate", json={})
    assert response.status_code == 400


def test_update_missing_returns_404(api_client):
    client, _ = api_client
    assert client.put("/api/inventory/none", json={"stock": 1.0}).status_code == 404


def test_adjust_stock_positive_delta(api_client):
    client, _ = api_client
    client.post("/api/inventory", json=_payload(stock=10.0))
    response = client.post("/api/inventory/tomate/adjust", json={"delta": 3.5})
    assert response.status_code == 200
    assert response.json()["stock"] == 13.5


def test_adjust_stock_clamped_at_zero(api_client):
    client, _ = api_client
    client.post("/api/inventory", json=_payload(stock=2.0))
    response = client.post("/api/inventory/tomate/adjust", json={"delta": -10.0})
    assert response.status_code == 200
    assert response.json()["stock"] == 0


def test_adjust_missing_returns_404(api_client):
    client, _ = api_client
    response = client.post("/api/inventory/none/adjust", json={"delta": 1.0})
    assert response.status_code == 404


def test_delete_existing_returns_204(api_client):
    client, db = api_client
    client.post("/api/inventory", json=_payload())
    response = client.delete("/api/inventory/tomate")
    assert response.status_code == 204
    assert db.inventory.find_one({"id": "tomate"}) is None


def test_delete_missing_returns_404(api_client):
    client, _ = api_client
    assert client.delete("/api/inventory/none").status_code == 404
