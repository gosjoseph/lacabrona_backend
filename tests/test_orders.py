"""End-to-end tests for the orders router (controller + service + repo)."""

from __future__ import annotations

import pytest

from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService


def _payload(**overrides) -> dict:
    base = {
        "channel": "table",
        "customer": "Anon",
        "table": 4,
        "items": [
            {"id": "taco-1", "qty": 2, "subtotal": 200.0},
            {"id": "agua-1", "qty": 1, "subtotal": 50.0},
        ],
        "delivery": 0,
        "etaMinutes": 15,
    }
    base.update(overrides)
    return base


def test_create_order_assigns_first_id_and_totals(api_client):
    client, _ = api_client
    response = client.post("/api/orders", json=_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "ord-1001"
    assert body["status"] == "new"
    assert body["subtotal"] == 250.0
    assert body["total"] == 250.0


def test_create_order_includes_delivery_in_total(api_client):
    client, _ = api_client
    response = client.post(
        "/api/orders",
        json=_payload(channel="delivery", address="Calle 1", phone="099", delivery=80),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["delivery"] == 80
    assert body["total"] == 330.0


def test_create_order_increments_id(api_client):
    client, _ = api_client
    first = client.post("/api/orders", json=_payload()).json()
    second = client.post("/api/orders", json=_payload()).json()
    assert first["id"] == "ord-1001"
    assert second["id"] == "ord-1002"


def test_list_orders_returns_in_reverse_chronological_order(api_client):
    client, _ = api_client
    client.post("/api/orders", json=_payload())
    client.post("/api/orders", json=_payload())
    response = client.get("/api/orders")
    assert response.status_code == 200
    orders = response.json()["orders"]
    assert len(orders) == 2
    assert orders[0]["id"] == "ord-1002"


def test_list_orders_filters_by_status(api_client):
    client, _ = api_client
    client.post("/api/orders", json=_payload())
    client.post("/api/orders", json=_payload())
    # Move one order to "preparing".
    client.patch("/api/orders/ord-1001/status", json={"status": "preparing"})

    new_only = client.get("/api/orders", params={"status": "new"}).json()["orders"]
    prep_only = client.get("/api/orders", params={"status": "preparing"}).json()["orders"]

    assert [o["id"] for o in new_only] == ["ord-1002"]
    assert [o["id"] for o in prep_only] == ["ord-1001"]


def test_get_existing_order(api_client):
    client, _ = api_client
    client.post("/api/orders", json=_payload())
    response = client.get("/api/orders/ord-1001")
    assert response.status_code == 200
    assert response.json()["customer"] == "Anon"


def test_get_missing_order_returns_404(api_client):
    client, _ = api_client
    assert client.get("/api/orders/ord-9999").status_code == 404


def test_set_status_updates_doc(api_client):
    client, _ = api_client
    client.post("/api/orders", json=_payload())
    response = client.patch("/api/orders/ord-1001/status", json={"status": "ready"})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_set_status_missing_returns_404(api_client):
    client, _ = api_client
    response = client.patch("/api/orders/ord-9999/status", json={"status": "ready"})
    assert response.status_code == 404


def test_set_status_invalid_value_rejected_by_validation(api_client):
    client, _ = api_client
    client.post("/api/orders", json=_payload())
    response = client.patch("/api/orders/ord-1001/status", json={"status": "garbage"})
    assert response.status_code == 422


def test_delete_existing_order(api_client):
    client, db = api_client
    client.post("/api/orders", json=_payload())
    response = client.delete("/api/orders/ord-1001")
    assert response.status_code == 204
    assert db.orders.find_one({"id": "ord-1001"}) is None


def test_delete_missing_order_returns_404(api_client):
    client, _ = api_client
    assert client.delete("/api/orders/ord-9999").status_code == 404


# ---- service-level _next_order_id fallback path -------------------------

def test_next_order_id_falls_back_when_existing_id_unparseable(mongo_test_db):
    mongo_test_db.orders.insert_one({"id": "no-numeric-suffix", "created": "now"})
    svc = OrderService(OrderRepository(mongo_test_db))
    next_id = svc._next_order_id()
    assert next_id.startswith("ord-")
    # Fallback uses a unix timestamp; "ord-" + digits.
    assert next_id.split("-")[1].isdigit()
