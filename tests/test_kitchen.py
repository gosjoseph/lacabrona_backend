"""Tests for the Kitchen Display System slice: station resolution, the kitchen
read endpoint, line-ready toggling + status derivation, and model defaults."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.categories.repository import CategoryRepository
from app.modules.kitchen import controller as kitchen_ctrl
from app.modules.kitchen.resolver import StationResolver
from app.modules.kitchen.service import KitchenService
from app.modules.menu.repository import MenuRepository
from app.modules.orders import controller as orders_ctrl
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schema import OrderCreate
from app.modules.orders.service import OrderService
from tests.conftest import employee_auth_overrides


# ---- Helpers ---------------------------------------------------------------


def _order_doc(order_id: str, status: str, items: list[dict], **extra) -> dict:
    base = {
        "id": order_id,
        "channel": "table",
        "created": datetime(2026, 5, 28, 20, 0, 0, tzinfo=timezone.utc),
        "status": status,
        "customer": "Cliente",
        "address": None,
        "phone": None,
        "table": 1,
        "items": items,
        "subtotal": 10.0,
        "delivery": 0,
        "total": 10.0,
        "etaMinutes": None,
    }
    base.update(extra)
    return base


def _line(item_id: str, **extra) -> dict:
    line = {"id": item_id, "qty": 1, "subtotal": 10.0, "station": "general", "ready": False}
    line.update(extra)
    return line


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def kitchen_client(mongo_test_db):
    db = mongo_test_db
    overrides = {
        orders_ctrl.get_service: lambda: OrderService(
            OrderRepository(db), MenuRepository(db), CategoryRepository(db)
        ),
        kitchen_ctrl.get_service: lambda: KitchenService(
            OrderRepository(db), MenuRepository(db), CategoryRepository(db)
        ),
    }
    overrides.update(employee_auth_overrides(db))
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


@pytest.fixture
def anon_client(mongo_test_db):
    from app.modules.auth import dependencies as auth_deps
    from app.modules.auth.service import AuthService

    db = mongo_test_db
    overrides = {
        orders_ctrl.get_service: lambda: OrderService(
            OrderRepository(db), MenuRepository(db), CategoryRepository(db)
        ),
        auth_deps.get_auth_service: lambda: AuthService.from_db(db),
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


# ---- T-K1..K3: resolver ----------------------------------------------------


def test_resolver_item_station_overrides_category():
    resolver = StationResolver(
        menu_by_id={"m1": {"id": "m1", "category": "c1", "station": "parrilla"}},
        category_by_id={"c1": {"id": "c1", "default_station": "frios"}},
    )
    assert resolver.station_for("m1") == "parrilla"


def test_resolver_uses_category_default_when_item_has_no_station():
    resolver = StationResolver(
        menu_by_id={"m1": {"id": "m1", "category": "c1", "station": None}},
        category_by_id={"c1": {"id": "c1", "default_station": "frios"}},
    )
    assert resolver.station_for("m1") == "frios"


def test_resolver_falls_back_to_general():
    resolver = StationResolver(
        menu_by_id={"m1": {"id": "m1", "category": "c1"}},
        category_by_id={"c1": {"id": "c1"}},
    )
    assert resolver.station_for("m1") == "general"
    assert resolver.station_for("unknown-id") == "general"


# ---- T-K4: create stamps station + ready, ignoring client values -----------


def test_create_stamps_resolved_station_and_ready_ignoring_client(mongo_test_db):
    db = mongo_test_db
    db.categories.insert_one({
        "id": "c1", "name": "Parrilla", "icon": "i", "color": "#000", "order": 1,
        "default_station": "parrilla",
    })
    db.menu.insert_one({
        "id": "m1", "category": "c1", "name": "Asado", "description": "d",
        "price": 100.0, "unit": "u", "station": None,
    })
    db.menu.insert_one({
        "id": "m2", "category": "c1", "name": "Flan", "description": "d",
        "price": 50.0, "unit": "u", "station": "postres",
    })
    svc = OrderService(
        OrderRepository(db), MenuRepository(db), CategoryRepository(db)
    )
    body = OrderCreate(
        channel="table",
        customer="Mesa 1",
        items=[
            {"id": "m1", "qty": 1, "subtotal": 100.0, "station": "HACK", "ready": True},
            {"id": "m2", "qty": 1, "subtotal": 50.0},
        ],
    )
    result = svc.create_order(body)
    lines = {line["id"]: line for line in result["items"]}
    # client-sent station "HACK" and ready=True are ignored
    assert lines["m1"]["station"] == "parrilla"  # category default
    assert lines["m1"]["ready"] is False
    assert lines["m2"]["station"] == "postres"  # item station wins
    assert lines["m2"]["ready"] is False


# ---- T-K5: kitchen returns only active tickets -----------------------------


def test_kitchen_returns_only_new_and_preparing(kitchen_client):
    client, db = kitchen_client
    for status in ("new", "preparing", "ready", "served", "cancelled"):
        db.orders.insert_one(_order_doc(f"ord-{status}", status, [_line("m1")]))
    resp = client.get("/api/v1/kitchen")
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()["tickets"]}
    assert ids == {"ord-new", "ord-preparing"}


# ---- T-K6: legacy line resolved on read without mutating stored doc --------


def test_kitchen_resolves_legacy_line_without_mutating_storage(kitchen_client):
    client, db = kitchen_client
    db.categories.insert_one({
        "id": "c1", "name": "Parrilla", "icon": "i", "color": "#000", "order": 1,
        "default_station": "parrilla",
    })
    db.menu.insert_one({
        "id": "m1", "category": "c1", "name": "Asado", "description": "d",
        "price": 100.0, "unit": "u",
    })
    # legacy line: no `station` key at all, no `ready`
    db.orders.insert_one(
        _order_doc("ord-legacy", "preparing", [{"id": "m1", "qty": 1, "subtotal": 100.0}])
    )

    resp = client.get("/api/v1/kitchen")
    ticket = next(t for t in resp.json()["tickets"] if t["id"] == "ord-legacy")
    assert ticket["items"][0]["station"] == "parrilla"
    assert ticket["items"][0]["ready"] is False

    # the stored document on disk is untouched
    stored = db.orders.find_one({"id": "ord-legacy"})
    assert "station" not in stored["items"][0]
    assert "ready" not in stored["items"][0]


# ---- T-K7: single-line preparing toggle ------------------------------------


def test_single_line_ready_toggles_status(kitchen_client):
    client, db = kitchen_client
    db.orders.insert_one(_order_doc("ord-1", "preparing", [_line("m1")]))

    up = client.patch("/api/v1/orders/ord-1/lines/m1/ready", json={"ready": True})
    assert up.status_code == 200
    assert up.json()["status"] == "ready"

    down = client.patch("/api/v1/orders/ord-1/lines/m1/ready", json={"ready": False})
    assert down.status_code == 200
    assert down.json()["status"] == "preparing"


# ---- T-K8: multi-line preparing --------------------------------------------


def test_multi_line_ready_status_progression(kitchen_client):
    client, db = kitchen_client
    db.orders.insert_one(
        _order_doc("ord-2", "preparing", [_line("m1"), _line("m2", station="parrilla")])
    )

    r1 = client.patch("/api/v1/orders/ord-2/lines/m1/ready", json={"ready": True})
    assert r1.json()["status"] == "preparing"

    r2 = client.patch("/api/v1/orders/ord-2/lines/m2/ready", json={"ready": True})
    assert r2.json()["status"] == "ready"

    r3 = client.patch("/api/v1/orders/ord-2/lines/m1/ready", json={"ready": False})
    assert r3.json()["status"] == "preparing"


# ---- T-K9: new orders never auto-advance -----------------------------------


def test_new_order_does_not_auto_advance(kitchen_client):
    client, db = kitchen_client
    db.orders.insert_one(_order_doc("ord-3", "new", [_line("m1")]))
    r = client.patch("/api/v1/orders/ord-3/lines/m1/ready", json={"ready": True})
    assert r.json()["status"] == "new"


# ---- T-K10: terminal statuses are immutable --------------------------------


@pytest.mark.parametrize("status", ["served", "cancelled"])
def test_terminal_status_unchanged(kitchen_client, status):
    client, db = kitchen_client
    db.orders.insert_one(_order_doc(f"ord-{status}", status, [_line("m1")]))
    r = client.patch(f"/api/v1/orders/ord-{status}/lines/m1/ready", json={"ready": True})
    assert r.status_code == 200
    assert r.json()["status"] == status


# ---- T-K11: 404s -----------------------------------------------------------


def test_line_ready_404_unknown_order_and_line(kitchen_client):
    client, db = kitchen_client
    db.orders.insert_one(_order_doc("ord-4", "preparing", [_line("m1")]))
    assert (
        client.patch("/api/v1/orders/ord-9999/lines/m1/ready", json={"ready": True}).status_code
        == 404
    )
    assert (
        client.patch("/api/v1/orders/ord-4/lines/nope/ready", json={"ready": True}).status_code
        == 404
    )


# ---- T-K12: anonymous PATCH line-ready -> 401 ------------------------------


def test_anonymous_patch_line_ready_unauthorized(anon_client):
    resp = anon_client.patch(
        "/api/v1/orders/ord-1/lines/m1/ready", json={"ready": True}
    )
    assert resp.status_code == 401


# ---- T-K14: model defaults -------------------------------------------------


def test_model_defaults():
    from app.modules.categories.model import Category
    from app.modules.menu.model import MenuItem
    from app.modules.menu.schema import MenuItemUpdate
    from app.modules.orders.model import OrderLine

    item = MenuItem(
        id="m", category="c", name="n", description="d", price=1.0, unit="u"
    )
    assert item.station is None

    cat = Category(id="c", name="n", icon="i", color="#000", order=1)
    assert cat.default_station is None

    line = OrderLine(id="m", qty=1, subtotal=1.0)
    assert line.ready is False
    assert line.station is None

    upd = MenuItemUpdate(station="parrilla")
    assert upd.station == "parrilla"
