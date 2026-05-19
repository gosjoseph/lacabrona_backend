"""End-to-end tests for the menu router (controller + service + repo)."""

from __future__ import annotations

import pytest

from app.modules.menu.repository import MenuRepository
from app.modules.menu.service import MenuService


def _payload(**overrides) -> dict:
    base = {
        "id": "taco-1",
        "category": "tacos",
        "name": "Taco al pastor",
        "description": "Cerdo marinado",
        "price": 200.0,
        "unit": "u",
        "tags": ["spicy"],
        "spice": 2,
        "vegetarian": False,
        "glutenFree": False,
        "image": None,
        "available": True,
    }
    base.update(overrides)
    return base


def test_list_menu_default_currency_uyu(api_client):
    client, _ = api_client
    response = client.get("/api/v1/menu")
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "UYU"
    assert body["items"] == []


def test_list_menu_uses_meta_currency_when_set(api_client):
    client, db = api_client
    db.meta.insert_one({"_id": "menu", "currency": "USD"})
    response = client.get("/api/v1/menu")
    assert response.json()["currency"] == "USD"


def test_create_then_get_item(api_client):
    client, _ = api_client
    create = client.post("/api/v1/menu", json=_payload())
    assert create.status_code == 201
    fetch = client.get("/api/v1/menu/taco-1")
    assert fetch.status_code == 200
    assert fetch.json()["name"] == "Taco al pastor"


def test_create_duplicate_returns_409(api_client):
    client, _ = api_client
    client.post("/api/v1/menu", json=_payload())
    second = client.post("/api/v1/menu", json=_payload())
    assert second.status_code == 409


def test_get_missing_returns_404(api_client):
    client, _ = api_client
    assert client.get("/api/v1/menu/none").status_code == 404


def test_filter_by_category(api_client):
    client, _ = api_client
    client.post("/api/v1/menu", json=_payload(id="t1", category="tacos"))
    client.post("/api/v1/menu", json=_payload(id="b1", category="bebidas"))

    response = client.get("/api/v1/menu", params={"category": "tacos"})
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == "t1"


def test_update_partial_fields(api_client):
    client, _ = api_client
    client.post("/api/v1/menu", json=_payload())
    response = client.put("/api/v1/menu/taco-1", json={"price": 250.0})
    assert response.status_code == 200
    assert response.json()["price"] == 250.0
    # Untouched fields remain.
    assert response.json()["name"] == "Taco al pastor"


def test_update_with_no_fields_returns_400(api_client):
    client, _ = api_client
    client.post("/api/v1/menu", json=_payload())
    response = client.put("/api/v1/menu/taco-1", json={})
    assert response.status_code == 400


def test_update_missing_returns_404(api_client):
    client, _ = api_client
    response = client.put("/api/v1/menu/none", json={"price": 1.0})
    assert response.status_code == 404


def test_delete_existing_returns_204(api_client):
    client, db = api_client
    client.post("/api/v1/menu", json=_payload())
    response = client.delete("/api/v1/menu/taco-1")
    assert response.status_code == 204
    assert db.menu.find_one({"id": "taco-1"}) is None


def test_delete_missing_returns_404(api_client):
    client, _ = api_client
    assert client.delete("/api/v1/menu/none").status_code == 404


# ---- Service-level safety net ---------------------------------------------

def test_service_get_missing_raises_404(mongo_test_db):
    from fastapi import HTTPException

    svc = MenuService(MenuRepository(mongo_test_db))
    with pytest.raises(HTTPException) as exc:
        svc.get_item("missing")
    assert exc.value.status_code == 404
