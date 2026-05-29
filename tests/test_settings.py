"""Tests for the operational settings singleton: defaults-merged read, the
computed open/closed status, section-level replace, and the orders-create
wiring (channel gating, authoritative delivery fee, charges)."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.orders import controller as orders_ctrl
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.settings import controller as settings_ctrl
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.service import SettingsService, compute_open_status
from tests.conftest import employee_auth_overrides


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def settings_client(mongo_test_db):
    """Employee client with the settings and orders services bound to mongomock.

    The orders service is wired with the same settings repository so the
    create-order behaviour reflects the configured settings.
    """
    db = mongo_test_db
    overrides = {
        settings_ctrl.get_service: lambda: SettingsService(SettingsRepository(db)),
        orders_ctrl.get_service: lambda: OrderService(
            OrderRepository(db), settings_repository=SettingsRepository(db)
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
def anon_settings_client(mongo_test_db):
    """Anonymous client — no session override, so `_session_dep` returns 401."""
    from app.modules.auth import dependencies as auth_deps
    from app.modules.auth.service import AuthService

    db = mongo_test_db
    overrides = {
        settings_ctrl.get_service: lambda: SettingsService(SettingsRepository(db)),
        auth_deps.get_auth_service: lambda: AuthService.from_db(db),
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


def _order_payload(**overrides) -> dict:
    base = {
        "channel": "table",
        "customer": "Mesa 1",
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


# ---- T-S1: defaults on empty DB --------------------------------------------


def test_get_settings_empty_db_returns_defaults(settings_client):
    client, _ = settings_client
    resp = client.get("/api/v1/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["channels"] == {"delivery": True, "pickup": True, "table": True}
    assert body["hours"] == {}
    assert body["delivery_zones"] == []
    assert body["tables"] == []
    assert body["stations"] == []
    assert body["charges"] == {
        "tax_rate": 0,
        "service_rate": 0,
        "tip_default_rate": 0,
        "tax_included": False,
    }
    assert body["identity"] == {
        "name": "",
        "tagline": "",
        "phone": "",
        "address": "",
        "neighborhood": "",
        "social": {},
    }
    # well-formed status object
    assert set(body["status"].keys()) == {"open", "until"}
    assert isinstance(body["status"]["open"], bool)
    assert body["status"]["until"] is None or isinstance(body["status"]["until"], str)


# ---- T-S2: PUT channels persists -------------------------------------------


def test_put_channels_persists(settings_client):
    client, _ = settings_client
    resp = client.put(
        "/api/v1/settings",
        json={"channels": {"delivery": False, "pickup": True, "table": True}},
    )
    assert resp.status_code == 200
    assert resp.json()["channels"]["delivery"] is False
    again = client.get("/api/v1/settings").json()
    assert again["channels"] == {"delivery": False, "pickup": True, "table": True}


# ---- T-S3: section-level replace -------------------------------------------


def test_section_replace_leaves_other_sections_untouched(settings_client):
    client, _ = settings_client
    client.put("/api/v1/settings", json={"stations": ["parrilla", "frios"]})
    client.put(
        "/api/v1/settings",
        json={"channels": {"delivery": False, "pickup": False, "table": True}},
    )
    body = client.get("/api/v1/settings").json()
    # stations untouched by the later channels-only PUT
    assert body["stations"] == ["parrilla", "frios"]
    assert body["channels"] == {"delivery": False, "pickup": False, "table": True}


# ---- T-S4: compute_open_status unit tests ----------------------------------

# A reference week: 2026-05-25 is Monday ... 2026-05-31 is Sunday.
_HOURS_SINGLE = {"mon": [{"open": "19:00", "close": "23:00"}]}
_HOURS_MULTI = {
    "mon": [
        {"open": "12:00", "close": "15:00"},
        {"open": "19:00", "close": "23:00"},
    ]
}
_HOURS_OVERNIGHT = {"sat": [{"open": "23:00", "close": "02:00"}]}
_HOURS_EMPTY_DAY = {"mon": []}


@pytest.mark.parametrize(
    "hours, now, expected",
    [
        # inside a single range -> open + correct until
        (_HOURS_SINGLE, datetime(2026, 5, 25, 20, 0), {"open": True, "until": "23:00"}),
        # before the range -> closed
        (_HOURS_SINGLE, datetime(2026, 5, 25, 18, 0), {"open": False, "until": None}),
        # after the range -> closed
        (_HOURS_SINGLE, datetime(2026, 5, 25, 23, 30), {"open": False, "until": None}),
        # multiple ranges same day: inside the second
        (_HOURS_MULTI, datetime(2026, 5, 25, 20, 0), {"open": True, "until": "23:00"}),
        # multiple ranges same day: inside the first
        (_HOURS_MULTI, datetime(2026, 5, 25, 13, 0), {"open": True, "until": "15:00"}),
        # multiple ranges same day: between them -> closed
        (_HOURS_MULTI, datetime(2026, 5, 25, 16, 0), {"open": False, "until": None}),
        # overnight range active the same evening
        (_HOURS_OVERNIGHT, datetime(2026, 5, 30, 23, 30), {"open": True, "until": "02:00"}),
        # overnight range still active just after midnight (Sun 00:30)
        (_HOURS_OVERNIGHT, datetime(2026, 5, 31, 0, 30), {"open": True, "until": "02:00"}),
        # overnight range after it closes -> closed
        (_HOURS_OVERNIGHT, datetime(2026, 5, 31, 2, 30), {"open": False, "until": None}),
        # explicit empty day -> closed
        (_HOURS_EMPTY_DAY, datetime(2026, 5, 25, 20, 0), {"open": False, "until": None}),
        # missing day key -> closed
        ({}, datetime(2026, 5, 25, 20, 0), {"open": False, "until": None}),
    ],
)
def test_compute_open_status(hours, now, expected):
    assert compute_open_status(hours, now) == expected


# ---- T-S5: status present and well-formed ----------------------------------


def test_status_present_and_well_formed(settings_client):
    client, _ = settings_client
    client.put(
        "/api/v1/settings",
        json={"hours": {"mon": [{"open": "19:00", "close": "23:00"}]}},
    )
    status = client.get("/api/v1/settings").json()["status"]
    assert set(status.keys()) == {"open", "until"}
    assert isinstance(status["open"], bool)
    assert status["until"] is None or isinstance(status["until"], str)


# ---- T-S6: channel gating --------------------------------------------------


def test_delivery_disabled_blocks_delivery_orders(settings_client):
    client, _ = settings_client
    client.put(
        "/api/v1/settings",
        json={"channels": {"delivery": False, "pickup": True, "table": True}},
    )
    blocked = client.post(
        "/api/v1/orders",
        json=_order_payload(channel="delivery", address="Calle 1", phone="099"),
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Canal no disponible"
    # an enabled channel still works
    ok = client.post("/api/v1/orders", json=_order_payload(channel="table"))
    assert ok.status_code == 201


# ---- T-S7: backward compat — default settings allow every channel ----------


@pytest.mark.parametrize("channel", ["delivery", "table", "pickup"])
def test_default_settings_allow_every_channel(settings_client, channel):
    client, _ = settings_client
    resp = client.post("/api/v1/orders", json=_order_payload(channel=channel))
    assert resp.status_code == 201, resp.text


# ---- T-S8: authoritative zone fee ------------------------------------------


def test_zone_fee_is_authoritative(settings_client):
    client, _ = settings_client
    client.put(
        "/api/v1/settings",
        json={"delivery_zones": [{"id": "centro", "name": "Centro", "fee": 120.0}]},
    )
    resp = client.post(
        "/api/v1/orders",
        json=_order_payload(
            channel="delivery",
            address="Calle 1",
            phone="099",
            zone="centro",
            delivery=999.0,  # client-sent value must be ignored
        ),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["delivery"] == 120.0
    assert body["zone"] == "centro"
    assert body["total"] == 250.0 + 120.0  # subtotal + authoritative fee


# ---- T-S9: unknown zone -> 422 ---------------------------------------------


def test_unknown_zone_rejected(settings_client):
    client, _ = settings_client
    client.put(
        "/api/v1/settings",
        json={"delivery_zones": [{"id": "centro", "name": "Centro", "fee": 120.0}]},
    )
    resp = client.post(
        "/api/v1/orders",
        json=_order_payload(
            channel="delivery", address="Calle 1", phone="099", zone="no-existe"
        ),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Zona inválida"


# ---- T-S10: no zone -> client delivery, zone None --------------------------


def test_no_zone_uses_client_delivery(settings_client):
    client, _ = settings_client
    resp = client.post(
        "/api/v1/orders",
        json=_order_payload(
            channel="delivery", address="Calle 1", phone="099", delivery=80.0
        ),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["delivery"] == 80.0
    assert body["zone"] is None
    assert body["total"] == 250.0 + 80.0


# ---- T-S11: charges excluded -----------------------------------------------


def test_charges_excluded_added_to_total(settings_client):
    client, _ = settings_client
    client.put(
        "/api/v1/settings",
        json={
            "charges": {
                "service_rate": 0.1,
                "tax_rate": 0.22,
                "tax_included": False,
            }
        },
    )
    resp = client.post("/api/v1/orders", json=_order_payload(channel="table"))
    assert resp.status_code == 201
    body = resp.json()
    # subtotal 250 -> service 25.0; tax base 275 -> tax 60.5
    assert body["service"] == 25.0
    assert body["tax"] == 60.5
    assert body["total"] == 250.0 + 25.0 + 60.5


# ---- T-S12: charges included -----------------------------------------------


def test_charges_included_not_added_to_total(settings_client):
    client, _ = settings_client
    client.put(
        "/api/v1/settings",
        json={
            "charges": {
                "service_rate": 0.1,
                "tax_rate": 0.22,
                "tax_included": True,
            }
        },
    )
    resp = client.post("/api/v1/orders", json=_order_payload(channel="table"))
    assert resp.status_code == 201
    body = resp.json()
    assert body["service"] == 25.0
    assert body["tax"] == 60.5  # computed and stored
    assert body["total"] == 250.0 + 25.0  # tax NOT added


# ---- T-S13: default zero rates guard existing behaviour --------------------


def test_default_zero_rates_keep_total_simple(settings_client):
    client, _ = settings_client
    resp = client.post(
        "/api/v1/orders", json=_order_payload(channel="table", delivery=0)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["service"] == 0
    assert body["tax"] == 0
    assert body["total"] == body["subtotal"]


# ---- T-S14: tip_default_rate never added to a total ------------------------


def test_tip_default_rate_stored_but_never_added(settings_client):
    client, _ = settings_client
    client.put("/api/v1/settings", json={"charges": {"tip_default_rate": 0.15}})
    assert client.get("/api/v1/settings").json()["charges"]["tip_default_rate"] == 0.15
    resp = client.post(
        "/api/v1/orders", json=_order_payload(channel="table", delivery=0)
    )
    body = resp.json()
    # tip is config only — total is just subtotal + delivery (+ zero charges)
    assert body["total"] == body["subtotal"]
    assert "tip" not in body


# ---- T-S15: anonymous PUT -> 401 -------------------------------------------


def test_anonymous_put_settings_unauthorized(anon_settings_client):
    resp = anon_settings_client.put(
        "/api/v1/settings", json={"channels": {"delivery": False}}
    )
    assert resp.status_code == 401


# ---- T-S16: lists round-trip -----------------------------------------------


def test_lists_round_trip(settings_client):
    client, _ = settings_client
    payload = {
        "delivery_zones": [
            {"id": "centro", "name": "Centro", "fee": 120.0},
            {"id": "pocitos", "name": "Pocitos", "fee": 180.0},
        ],
        "tables": [
            {"id": "t1", "label": "Mesa 1", "seats": 2},
            {"id": "t2", "label": "Mesa 2", "seats": 4},
        ],
        "stations": ["parrilla", "frios", "barra"],
    }
    client.put("/api/v1/settings", json=payload)
    body = client.get("/api/v1/settings").json()
    assert body["delivery_zones"] == payload["delivery_zones"]
    assert body["tables"] == payload["tables"]
    assert body["stations"] == payload["stations"]
