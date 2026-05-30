"""End-to-end tests for the inventory router (controller + service + repo).

Covers the dual-stock model (`stock_real` + `stock_estimated`), multi-provider
pricing, the add/set `/restock` endpoint, and legacy-document normalization.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.service import InventoryService


def _payload(**overrides) -> dict:
    base = {
        "id": "tomate",
        "name": "Tomate",
        "category": "verduras",
        "unit": "kg",
        "min": 5.0,
        "stock_real": 10.0,
        "stock_estimated": 10.0,
        "providers": [{"name": "Granja", "price": 30.0}],
    }
    base.update(overrides)
    return base


# ---- CRUD basics ----------------------------------------------------------

def test_list_empty(api_client):
    client, _ = api_client
    response = client.get("/api/v1/inventory")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_create_then_get(api_client):
    client, _ = api_client
    create = client.post("/api/v1/inventory", json=_payload())
    assert create.status_code == 201
    fetch = client.get("/api/v1/inventory/tomate")
    assert fetch.status_code == 200
    assert fetch.json()["name"] == "Tomate"


def test_create_duplicate_returns_409(api_client):
    client, _ = api_client
    client.post("/api/v1/inventory", json=_payload())
    second = client.post("/api/v1/inventory", json=_payload())
    assert second.status_code == 409


def test_get_missing_returns_404(api_client):
    client, _ = api_client
    assert client.get("/api/v1/inventory/none").status_code == 404


def test_update_with_no_fields_returns_400(api_client):
    client, _ = api_client
    client.post("/api/v1/inventory", json=_payload())
    response = client.put("/api/v1/inventory/tomate", json={})
    assert response.status_code == 400


def test_update_missing_returns_404(api_client):
    client, _ = api_client
    assert (
        client.put("/api/v1/inventory/none", json={"name": "X"}).status_code == 404
    )


def test_delete_existing_returns_204(api_client):
    client, db = api_client
    client.post("/api/v1/inventory", json=_payload())
    response = client.delete("/api/v1/inventory/tomate")
    assert response.status_code == 204
    assert db.inventory.find_one({"id": "tomate"}) is None


def test_delete_missing_returns_404(api_client):
    client, _ = api_client
    assert client.delete("/api/v1/inventory/none").status_code == 404


# ---- T-B1 / T-B2 / T-B3: create variants ----------------------------------

def test_create_defaults_estimated_to_real(api_client):  # T-B1
    client, _ = api_client
    payload = _payload(stock_real=12.0)
    payload.pop("stock_estimated", None)
    assert client.post("/api/v1/inventory", json=payload).status_code == 201
    body = client.get("/api/v1/inventory/tomate").json()
    assert body["stock_real"] == 12.0
    assert body["stock_estimated"] == 12.0


def test_create_with_both_stocks_distinct(api_client):  # T-B2
    client, _ = api_client
    client.post(
        "/api/v1/inventory", json=_payload(stock_real=10.0, stock_estimated=4.0)
    )
    body = client.get("/api/v1/inventory/tomate").json()
    assert body["stock_real"] == 10.0
    assert body["stock_estimated"] == 4.0


def test_create_with_providers(api_client):  # T-B3
    client, _ = api_client
    providers = [
        {"name": "Granja", "price": 30.0},
        {"name": "Mercado", "price": 35.0},
    ]
    client.post("/api/v1/inventory", json=_payload(providers=providers))
    body = client.get("/api/v1/inventory/tomate").json()
    assert body["providers"] == providers


# ---- T-B4..T-B8: restock --------------------------------------------------

def test_restock_add(api_client):  # T-B4
    client, _ = api_client
    client.post(
        "/api/v1/inventory", json=_payload(stock_real=10.0, stock_estimated=4.0)
    )
    response = client.post(
        "/api/v1/inventory/tomate/restock", json={"mode": "add", "amount": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stock_real"] == 15
    assert body["stock_estimated"] == 9


def test_restock_add_clamps_at_zero(api_client):  # T-B5
    client, _ = api_client
    client.post(
        "/api/v1/inventory", json=_payload(stock_real=10.0, stock_estimated=4.0)
    )
    response = client.post(
        "/api/v1/inventory/tomate/restock", json={"mode": "add", "amount": -100}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stock_real"] == 0
    assert body["stock_estimated"] == 0


def test_restock_set(api_client):  # T-B6
    client, _ = api_client
    client.post(
        "/api/v1/inventory", json=_payload(stock_real=10.0, stock_estimated=4.0)
    )
    response = client.post(
        "/api/v1/inventory/tomate/restock", json={"mode": "set", "amount": 20}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stock_real"] == 20
    assert body["stock_estimated"] == 20


def test_restock_set_is_absolute(api_client):  # T-B7
    client, _ = api_client
    client.post(
        "/api/v1/inventory", json=_payload(stock_real=50.0, stock_estimated=2.0)
    )
    response = client.post(
        "/api/v1/inventory/tomate/restock", json={"mode": "set", "amount": 3}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stock_real"] == 3
    assert body["stock_estimated"] == 3


def test_restock_missing_returns_404(api_client):  # T-B8
    client, _ = api_client
    response = client.post(
        "/api/v1/inventory/none/restock", json={"mode": "add", "amount": 1}
    )
    assert response.status_code == 404


# ---- T-B9 / T-B10: metadata update never touches stock --------------------

def test_update_providers_replaces_list(api_client):  # T-B9
    client, _ = api_client
    client.post(
        "/api/v1/inventory",
        json=_payload(stock_real=10.0, stock_estimated=4.0),
    )
    new_providers = [
        {"name": "Otra Granja", "price": 40.0},
        {"name": "Feria", "price": 28.0},
    ]
    response = client.put(
        "/api/v1/inventory/tomate", json={"providers": new_providers}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["providers"] == new_providers
    assert body["stock_real"] == 10.0
    assert body["stock_estimated"] == 4.0


def test_update_ignores_stock_real(api_client):  # T-B10
    client, _ = api_client
    client.post(
        "/api/v1/inventory",
        json=_payload(stock_real=10.0, stock_estimated=4.0),
    )
    response = client.put(
        "/api/v1/inventory/tomate", json={"name": "Tomate Perita", "stock_real": 999}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Tomate Perita"
    assert body["stock_real"] == 10.0
    assert body["stock_estimated"] == 4.0


# ---- T-B11 / T-B12: legacy-document normalization -------------------------

def _insert_legacy(db) -> None:
    db.inventory.insert_one(
        {
            "id": "legacy",
            "name": "Insumo Viejo",
            "category": "verduras",
            "unit": "kg",
            "min": 5,
            "stock": 8,
            "supplier": "Viejo",
            "updated": datetime.now(timezone.utc).isoformat(),
        }
    )


def test_legacy_normalization_on_read(api_client):  # T-B11
    client, db = api_client
    _insert_legacy(db)
    response = client.get("/api/v1/inventory/legacy")
    assert response.status_code == 200
    body = response.json()
    assert body["stock_real"] == 8
    assert body["stock_estimated"] == 8
    assert body["providers"] == [{"name": "Viejo", "price": 0.0}]
    assert "stock" not in body
    assert "supplier" not in body


def test_legacy_restock_uses_normalized_base(api_client):  # T-B12
    client, db = api_client
    _insert_legacy(db)
    response = client.post(
        "/api/v1/inventory/legacy/restock", json={"mode": "add", "amount": 2}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stock_real"] == 10
    assert body["stock_estimated"] == 10


# ---- T-CI1 / T-CI2 / T-CI3: consume_estimated -----------------------------
# Estimated-only drawdown used when an order is marked ready. `stock_real` is
# never touched; the demand is clamped at 0; a missing item is a silent no-op.

def _inventory_service(db) -> InventoryService:
    return InventoryService(InventoryRepository(db))


def test_consume_estimated_touches_only_estimated(api_client):  # T-CI1
    client, db = api_client
    client.post(
        "/api/v1/inventory", json=_payload(stock_real=10.0, stock_estimated=8.0)
    )
    _inventory_service(db).consume_estimated("tomate", 3.0)
    body = client.get("/api/v1/inventory/tomate").json()
    assert body["stock_estimated"] == 5.0
    assert body["stock_real"] == 10.0


def test_consume_estimated_clamps_at_zero(api_client):  # T-CI2
    client, db = api_client
    client.post(
        "/api/v1/inventory", json=_payload(stock_real=10.0, stock_estimated=4.0)
    )
    _inventory_service(db).consume_estimated("tomate", 100.0)
    body = client.get("/api/v1/inventory/tomate").json()
    assert body["stock_estimated"] == 0
    assert body["stock_real"] == 10.0


def test_consume_estimated_missing_item_is_noop(api_client):  # T-CI3
    client, db = api_client
    # No document for "ghost"; the call must not raise and must not create one.
    _inventory_service(db).consume_estimated("ghost", 5.0)
    assert client.get("/api/v1/inventory/ghost").status_code == 404
