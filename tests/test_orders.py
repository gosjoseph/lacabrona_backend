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
    response = client.post("/api/v1/orders", json=_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "ord-1001"
    assert body["status"] == "new"
    assert body["subtotal"] == 250.0
    assert body["total"] == 250.0


def test_create_order_includes_delivery_in_total(api_client):
    client, _ = api_client
    response = client.post(
        "/api/v1/orders",
        json=_payload(channel="delivery", address="Calle 1", phone="099", delivery=80),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["delivery"] == 80
    assert body["total"] == 330.0


def test_create_order_increments_id(api_client):
    client, _ = api_client
    first = client.post("/api/v1/orders", json=_payload()).json()
    second = client.post("/api/v1/orders", json=_payload()).json()
    assert first["id"] == "ord-1001"
    assert second["id"] == "ord-1002"


def test_list_orders_returns_in_reverse_chronological_order(api_client):
    client, _ = api_client
    client.post("/api/v1/orders", json=_payload())
    client.post("/api/v1/orders", json=_payload())
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    orders = response.json()["orders"]
    assert len(orders) == 2
    assert orders[0]["id"] == "ord-1002"


def test_list_orders_filters_by_status(api_client):
    client, _ = api_client
    client.post("/api/v1/orders", json=_payload())
    client.post("/api/v1/orders", json=_payload())
    # Move one order to "preparing".
    client.patch("/api/v1/orders/ord-1001/status", json={"status": "preparing"})

    new_only = client.get("/api/v1/orders", params={"status": "new"}).json()["orders"]
    prep_only = client.get("/api/v1/orders", params={"status": "preparing"}).json()["orders"]

    assert [o["id"] for o in new_only] == ["ord-1002"]
    assert [o["id"] for o in prep_only] == ["ord-1001"]


def test_get_existing_order(api_client):
    client, _ = api_client
    client.post("/api/v1/orders", json=_payload())
    response = client.get("/api/v1/orders/ord-1001")
    assert response.status_code == 200
    assert response.json()["customer"] == "Anon"


def test_get_missing_order_returns_404(api_client):
    client, _ = api_client
    assert client.get("/api/v1/orders/ord-9999").status_code == 404


def test_set_status_updates_doc(api_client):
    client, _ = api_client
    client.post("/api/v1/orders", json=_payload())
    response = client.patch("/api/v1/orders/ord-1001/status", json={"status": "ready"})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_set_status_missing_returns_404(api_client):
    client, _ = api_client
    response = client.patch("/api/v1/orders/ord-9999/status", json={"status": "ready"})
    assert response.status_code == 404


def test_set_status_invalid_value_rejected_by_validation(api_client):
    client, _ = api_client
    client.post("/api/v1/orders", json=_payload())
    response = client.patch("/api/v1/orders/ord-1001/status", json={"status": "garbage"})
    assert response.status_code == 422


def test_delete_existing_order(api_client):
    client, db = api_client
    client.post("/api/v1/orders", json=_payload())
    response = client.delete("/api/v1/orders/ord-1001")
    assert response.status_code == 204
    assert db.orders.find_one({"id": "ord-1001"}) is None


def test_delete_missing_order_returns_404(api_client):
    client, _ = api_client
    assert client.delete("/api/v1/orders/ord-9999").status_code == 404


# ---- service-level _next_order_id fallback path -------------------------

def test_next_order_id_falls_back_when_existing_id_unparseable(mongo_test_db):
    mongo_test_db.orders.insert_one({"id": "no-numeric-suffix", "created": "now"})
    svc = OrderService(OrderRepository(mongo_test_db))
    next_id = svc._next_order_id()
    assert next_id.startswith("ord-")
    # Fallback uses a unix timestamp; "ord-" + digits.
    assert next_id.split("-")[1].isdigit()


# =========================================================================
# T-CO1..T-CO9: estimated-inventory deduction when an order is marked ready
# =========================================================================
# When an order first reaches "ready" the service expands every line through
# its menu item's recipe, aggregates per inventory item, and subtracts from
# stock_estimated (clamped at 0). stock_real is NEVER touched, the deduction
# is idempotent, and any gap (missing menu item, empty recipe, unknown
# inventory id) is skipped — marking ready must always succeed.

def _seed_inventory(client, item_id, *, real, estimated):
    resp = client.post(
        "/api/v1/inventory",
        json={
            "id": item_id,
            "name": item_id,
            "category": "insumos",
            "unit": "kg",
            "min": 0.0,
            "stock_real": real,
            "stock_estimated": estimated,
            "providers": [],
        },
    )
    assert resp.status_code == 201


def _seed_menu(client, item_id, recipe):
    resp = client.post(
        "/api/v1/menu",
        json={
            "id": item_id,
            "category": "comida",
            "name": item_id,
            "description": "—",
            "price": 100.0,
            "unit": "porción",
            "recipe": recipe,
        },
    )
    assert resp.status_code == 201


def _order_with_lines(client, lines):
    """Create an order from ``(menu_id, qty)`` pairs; returns its id."""
    items = [{"id": lid, "qty": qty, "subtotal": 100.0 * qty} for lid, qty in lines]
    resp = client.post("/api/v1/orders", json=_payload(items=items))
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_status(client, order_id, status):
    return client.patch(f"/api/v1/orders/{order_id}/status", json={"status": status})


def _stock(client, item_id):
    body = client.get(f"/api/v1/inventory/{item_id}").json()
    return body["stock_real"], body["stock_estimated"]


def test_ready_deducts_per_ingredient_totals(api_client):  # T-CO1
    client, _ = api_client
    _seed_inventory(client, "harina", real=100, estimated=100)
    _seed_inventory(client, "queso", real=50, estimated=50)
    _seed_inventory(client, "lechuga", real=20, estimated=20)
    _seed_menu(
        client,
        "pizza",
        [{"inventory_id": "harina", "qty": 2}, {"inventory_id": "queso", "qty": 1}],
    )
    _seed_menu(client, "ensalada", [{"inventory_id": "lechuga", "qty": 1}])

    order_id = _order_with_lines(client, [("pizza", 3), ("ensalada", 2)])
    assert _set_status(client, order_id, "ready").status_code == 200

    assert _stock(client, "harina") == (100, 100 - 2 * 3)  # 94
    assert _stock(client, "queso") == (50, 50 - 1 * 3)  # 47
    assert _stock(client, "lechuga") == (20, 20 - 1 * 2)  # 18


def test_ready_deduction_is_idempotent(api_client):  # T-CO2
    client, _ = api_client
    _seed_inventory(client, "harina", real=100, estimated=100)
    _seed_menu(client, "pan", [{"inventory_id": "harina", "qty": 1}])

    order_id = _order_with_lines(client, [("pan", 4)])
    assert _set_status(client, order_id, "ready").status_code == 200
    assert _stock(client, "harina") == (100, 96)

    # Re-marking ready, and a served -> ready reopen, must not deduct again.
    assert _set_status(client, order_id, "ready").status_code == 200
    assert _set_status(client, order_id, "served").status_code == 200
    assert _set_status(client, order_id, "ready").status_code == 200
    assert _stock(client, "harina") == (100, 96)


def test_ready_clamps_estimated_at_zero(api_client):  # T-CO3
    client, _ = api_client
    _seed_inventory(client, "sal", real=10, estimated=2)
    _seed_menu(client, "salado", [{"inventory_id": "sal", "qty": 10}])

    order_id = _order_with_lines(client, [("salado", 1)])
    assert _set_status(client, order_id, "ready").status_code == 200

    assert _stock(client, "sal") == (10, 0)


def test_ready_aggregates_shared_inventory_id(api_client):  # T-CO4
    client, _ = api_client
    _seed_inventory(client, "aceite", real=100, estimated=100)
    _seed_menu(client, "papas", [{"inventory_id": "aceite", "qty": 3}])
    _seed_menu(client, "milanesa", [{"inventory_id": "aceite", "qty": 2}])

    order_id = _order_with_lines(client, [("papas", 2), ("milanesa", 4)])
    assert _set_status(client, order_id, "ready").status_code == 200

    # 3*2 + 2*4 = 14, deducted exactly once from the shared item.
    assert _stock(client, "aceite") == (100, 86)


def test_ready_empty_recipe_contributes_nothing(api_client):  # T-CO5
    client, _ = api_client
    _seed_inventory(client, "harina", real=10, estimated=10)
    _seed_menu(client, "agua", [])

    order_id = _order_with_lines(client, [("agua", 3)])
    resp = _set_status(client, order_id, "ready")
    assert resp.status_code == 200
    assert resp.json()["inventory_applied"] is True
    assert _stock(client, "harina") == (10, 10)


def test_ready_skips_unknown_menu_item(api_client):  # T-CO6
    client, _ = api_client
    _seed_inventory(client, "harina", real=10, estimated=10)
    _seed_menu(client, "real-item", [{"inventory_id": "harina", "qty": 2}])

    # "ghost-menu" has no menu document; it is skipped, the real line deducts.
    order_id = _order_with_lines(client, [("real-item", 1), ("ghost-menu", 5)])
    assert _set_status(client, order_id, "ready").status_code == 200

    assert _stock(client, "harina") == (10, 8)


def test_ready_skips_unknown_inventory_id(api_client):  # T-CO7
    client, _ = api_client
    _seed_inventory(client, "harina", real=10, estimated=10)
    _seed_menu(
        client,
        "thing",
        [{"inventory_id": "harina", "qty": 2}, {"inventory_id": "ghost-inv", "qty": 99}],
    )

    order_id = _order_with_lines(client, [("thing", 1)])
    assert _set_status(client, order_id, "ready").status_code == 200

    assert _stock(client, "harina") == (10, 8)
    # The unknown ingredient never created an inventory document.
    assert client.get("/api/v1/inventory/ghost-inv").status_code == 404


def test_preparing_does_not_deduct(api_client):  # T-CO8
    client, _ = api_client
    _seed_inventory(client, "harina", real=10, estimated=10)
    _seed_menu(client, "pan", [{"inventory_id": "harina", "qty": 1}])

    order_id = _order_with_lines(client, [("pan", 5)])
    resp = _set_status(client, order_id, "preparing")
    assert resp.status_code == 200
    assert resp.json()["inventory_applied"] is False
    assert _stock(client, "harina") == (10, 10)

    # Reaching ready afterwards still deducts.
    assert _set_status(client, order_id, "ready").status_code == 200
    assert _stock(client, "harina") == (10, 5)


def test_inventory_applied_flag_flips_on_ready(api_client):  # T-CO9
    client, _ = api_client
    _seed_inventory(client, "harina", real=10, estimated=10)
    _seed_menu(client, "pan", [{"inventory_id": "harina", "qty": 1}])

    order_id = _order_with_lines(client, [("pan", 1)])
    assert client.get(f"/api/v1/orders/{order_id}").json()["inventory_applied"] is False

    assert _set_status(client, order_id, "ready").status_code == 200
    assert client.get(f"/api/v1/orders/{order_id}").json()["inventory_applied"] is True
