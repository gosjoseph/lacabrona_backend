"""End-to-end tests for the categories router (controller + service + repo)."""

from __future__ import annotations

import pytest

from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schema import CategoryCreate
from app.modules.categories.service import CategoryService


def _payload(**overrides) -> dict:
    base = {
        "id": "tacos",
        "name": "Tacos",
        "icon": "taco",
        "color": "#fff",
        "order": 1,
    }
    base.update(overrides)
    return base


# ---- HTTP-level tests ----------------------------------------------------

def test_list_categories_empty(api_client):
    client, _ = api_client
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert response.json() == []


def test_create_then_list_returns_in_order(api_client):
    client, _ = api_client
    client.post("/api/categories", json=_payload(id="b", order=2))
    client.post("/api/categories", json=_payload(id="a", order=1))

    response = client.get("/api/categories")
    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body] == ["a", "b"]


def test_create_returns_201_and_persists(api_client):
    client, db = api_client
    response = client.post("/api/categories", json=_payload())
    assert response.status_code == 201
    assert response.json()["id"] == "tacos"
    assert db.categories.find_one({"id": "tacos"}) is not None


def test_create_duplicate_returns_409(api_client):
    client, _ = api_client
    client.post("/api/categories", json=_payload())
    response = client.post("/api/categories", json=_payload())
    assert response.status_code == 409


def test_get_category_404_when_missing(api_client):
    client, _ = api_client
    assert client.get("/api/categories/missing").status_code == 404


def test_get_category_returns_existing(api_client):
    client, _ = api_client
    client.post("/api/categories", json=_payload())
    response = client.get("/api/categories/tacos")
    assert response.status_code == 200
    assert response.json()["name"] == "Tacos"


def test_update_existing_category(api_client):
    client, _ = api_client
    client.post("/api/categories", json=_payload())
    response = client.put(
        "/api/categories/tacos",
        json=_payload(id="tacos", name="Tacos al pastor"),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Tacos al pastor"


def test_update_missing_returns_404(api_client):
    client, _ = api_client
    response = client.put("/api/categories/none", json=_payload(id="none"))
    assert response.status_code == 404


def test_delete_existing_returns_204(api_client):
    client, db = api_client
    client.post("/api/categories", json=_payload())
    response = client.delete("/api/categories/tacos")
    assert response.status_code == 204
    assert db.categories.find_one({"id": "tacos"}) is None


def test_delete_missing_returns_404(api_client):
    client, _ = api_client
    assert client.delete("/api/categories/none").status_code == 404


# ---- Service-level tests (HTTPException paths) ---------------------------

def test_service_get_missing_raises_http_exception(mongo_test_db):
    from fastapi import HTTPException

    svc = CategoryService(CategoryRepository(mongo_test_db))
    with pytest.raises(HTTPException) as exc:
        svc.get_category("nope")
    assert exc.value.status_code == 404


def test_service_create_duplicate_raises_409(mongo_test_db):
    from fastapi import HTTPException

    svc = CategoryService(CategoryRepository(mongo_test_db))
    body = CategoryCreate(**_payload())
    svc.create_category(body)
    with pytest.raises(HTTPException) as exc:
        svc.create_category(body)
    assert exc.value.status_code == 409
