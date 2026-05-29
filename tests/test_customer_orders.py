"""Authenticated-customer ordering: identity stamping, authoritative pricing,
empty-order rejection, channel gating and the per-customer open-order cap.

A logged-in customer may POST /orders; anonymous callers may not, and every
other order route stays employee-only (covered in test_ops_authz). These tests
exercise the customer branch of `OrderService.create_order`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth import controller as auth_ctrl
from app.modules.auth import dependencies as auth_deps
from app.modules.auth.service import AuthService
from app.modules.categories.repository import CategoryRepository
from app.modules.customers import controller as customers_ctrl
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.service import CustomerService
from app.modules.menu.repository import MenuRepository
from app.modules.orders import controller as orders_ctrl
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.settings.repository import SettingsRepository

EMPLOYEE_ST_ID = "st-employee-co"
CUSTOMER_A_ST_ID = "st-customer-a-co"
CUSTOMER_B_ST_ID = "st-customer-b-co"


class _FakeSession:
    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def get_user_id(self) -> str:
        return self._user_id


def _payload(**overrides) -> dict:
    base = {
        "channel": "table",
        "customer": "Cliente Form",
        "table": 5,
        "items": [
            {"id": "taco-1", "qty": 2, "subtotal": 200.0},
            {"id": "agua-1", "qty": 1, "subtotal": 50.0},
        ],
        "delivery": 0,
        "etaMinutes": 35,
    }
    base.update(overrides)
    return base


def _set_settings(db, **sections) -> None:
    SettingsRepository(db).replace_sections(sections)


def _seed_order(db, order_id: str, customer_id: str, status: str) -> None:
    db.orders.insert_one({
        "id": order_id,
        "channel": "table",
        "created": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        "status": status,
        "customer": "Seed",
        "customer_id": customer_id,
        "items": [],
        "subtotal": 0,
        "delivery": 0,
        "total": 0,
    })


@pytest.fixture
def env(mongo_test_db):
    """Client + db with two customers and one employee linked to sessions.

    `set_actor(st_id_or_None)` switches the resolved session for the next
    request (None makes `_session_dep` raise 401, i.e. anonymous).
    """
    db = mongo_test_db
    db.employees.insert_one({
        "_id": ObjectId(),
        "email": "staff@lacabrona.uy",
        "name": "Staff CO",
        "role": "admin",
        "supertokens_user_id": EMPLOYEE_ST_ID,
    })
    cust_a_oid = ObjectId()
    cust_b_oid = ObjectId()
    db.customers.insert_one({
        "_id": cust_a_oid,
        "email": "ana@lacabrona.uy",
        "first_name": "Ana",
        "last_name": "Cliente",
        "supertokens_user_id": CUSTOMER_A_ST_ID,
    })
    db.customers.insert_one({
        "_id": cust_b_oid,
        "email": "beto@lacabrona.uy",
        "first_name": "Beto",
        "last_name": "Cliente",
        "supertokens_user_id": CUSTOMER_B_ST_ID,
    })

    holder = {"user_id": CUSTOMER_A_ST_ID}

    def _session():
        uid = holder["user_id"]
        if uid is None:
            raise HTTPException(status_code=401, detail="unauthorised")
        return _FakeSession(uid)

    overrides = {
        orders_ctrl.get_service: lambda: OrderService(
            OrderRepository(db),
            menu_repository=MenuRepository(db),
            category_repository=CategoryRepository(db),
            settings_repository=SettingsRepository(db),
            customer_repository=CustomerRepository(db),
        ),
        customers_ctrl.get_customers_service: lambda: CustomerService(
            CustomerRepository(db)
        ),
        auth_deps.get_auth_service: lambda: AuthService.from_db(db),
        auth_ctrl._session_dep: _session,
    }
    app.dependency_overrides.update(overrides)

    def set_actor(user_id):
        holder["user_id"] = user_id

    try:
        with TestClient(app) as client:
            yield {
                "client": client,
                "db": db,
                "set_actor": set_actor,
                "customer_a_id": str(cust_a_oid),
                "customer_b_id": str(cust_b_oid),
            }
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


# ---- T-CO1: anonymous cannot order -----------------------------------------

def test_anonymous_post_orders_401(env):
    env["set_actor"](None)
    resp = env["client"].post("/api/v1/orders", json=_payload())
    assert resp.status_code == 401


# ---- T-CO2: identity stamped from session, client status ignored -----------

def test_customer_identity_comes_from_session(env):
    env["set_actor"](CUSTOMER_A_ST_ID)
    resp = env["client"].post(
        "/api/v1/orders",
        json=_payload(
            customer="Nombre Falso",
            customer_id="cust-evil",
            status="served",
        ),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "new"
    assert body["customer"] == "Ana Cliente"
    assert body["customer_id"] == env["customer_a_id"]


# ---- T-CO3: server-authoritative pricing -----------------------------------

def test_customer_pricing_is_server_authoritative(env):
    _set_settings(
        env["db"],
        delivery_zones=[{"id": "centro", "name": "Centro", "fee": 120.0}],
    )
    env["set_actor"](CUSTOMER_A_ST_ID)
    resp = env["client"].post(
        "/api/v1/orders",
        json=_payload(
            channel="delivery",
            address="Calle 1234",
            zone="centro",
            delivery=9999,  # client-sent fee — ignored
            subtotal=1,     # ignored (not a model field)
            total=2,        # ignored
        ),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["subtotal"] == 250.0
    assert body["delivery"] == 120.0
    assert body["total"] == 370.0


# ---- T-CO4: empty order rejected -------------------------------------------

def test_customer_empty_items_422(env):
    env["set_actor"](CUSTOMER_A_ST_ID)
    resp = env["client"].post("/api/v1/orders", json=_payload(items=[]))
    assert resp.status_code == 422


# ---- T-CO5: per-customer open-order cap -------------------------------------

def test_cap_blocks_fourth_active_order(env):
    db = env["db"]
    cid = env["customer_a_id"]
    for i, status in enumerate(("new", "preparing", "ready")):
        _seed_order(db, f"ord-{2000 + i}", cid, status)
    env["set_actor"](CUSTOMER_A_ST_ID)
    resp = env["client"].post("/api/v1/orders", json=_payload())
    assert resp.status_code == 429


def test_served_and_cancelled_do_not_count_towards_cap(env):
    db = env["db"]
    cid = env["customer_a_id"]
    for i, status in enumerate(("served", "cancelled", "served", "cancelled")):
        _seed_order(db, f"ord-{3000 + i}", cid, status)
    env["set_actor"](CUSTOMER_A_ST_ID)
    resp = env["client"].post("/api/v1/orders", json=_payload())
    assert resp.status_code == 201, resp.text


# ---- T-CO6: the cap is scoped per customer ---------------------------------

def test_cap_is_per_customer(env):
    db = env["db"]
    for i, status in enumerate(("new", "preparing", "ready")):
        _seed_order(db, f"ord-{4000 + i}", env["customer_a_id"], status)

    # Customer B is unaffected by A being at cap.
    env["set_actor"](CUSTOMER_B_ST_ID)
    resp_b = env["client"].post("/api/v1/orders", json=_payload())
    assert resp_b.status_code == 201, resp_b.text

    # Customer A is still blocked.
    env["set_actor"](CUSTOMER_A_ST_ID)
    resp_a = env["client"].post("/api/v1/orders", json=_payload())
    assert resp_a.status_code == 429


# ---- T-CO7: employee path is uncapped and links a canonical customer -------

def test_employee_is_not_capped_and_sets_customer(env):
    env["set_actor"](EMPLOYEE_ST_ID)
    last = None
    for _ in range(5):  # well over the customer cap of 3
        resp = env["client"].post("/api/v1/orders", json=_payload(customer="Mesa VIP"))
        assert resp.status_code == 201, resp.text
        last = resp.json()
    assert last["customer"] == "Mesa VIP"
    # Part 1: every new order links to a canonical customer. A typed, unknown
    # name on a staff order creates a name-only canonical row and stamps its id.
    assert last["customer_id"] is not None
    assert last["customer_id"].startswith("cust-")


# ---- T-CO8: channel gating for a customer ----------------------------------

def test_customer_delivery_blocked_when_channel_disabled(env):
    _set_settings(
        env["db"],
        channels={"delivery": False, "pickup": True, "table": True},
    )
    env["set_actor"](CUSTOMER_A_ST_ID)
    resp = env["client"].post(
        "/api/v1/orders",
        json=_payload(channel="delivery", address="Calle 1"),
    )
    assert resp.status_code == 409


# ---- T-CO9: zone fee is authoritative; unknown zone rejected ---------------

def test_customer_delivery_zone_fee_and_unknown_zone(env):
    _set_settings(
        env["db"],
        delivery_zones=[{"id": "centro", "name": "Centro", "fee": 150.0}],
    )
    env["set_actor"](CUSTOMER_A_ST_ID)

    ok = env["client"].post(
        "/api/v1/orders",
        json=_payload(channel="delivery", address="Calle 9", zone="centro"),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["delivery"] == 150.0

    bad = env["client"].post(
        "/api/v1/orders",
        json=_payload(channel="delivery", address="Calle 9", zone="inexistente"),
    )
    assert bad.status_code == 422


# ---- T-CU5: manual order with a picked customer_id links it, creates none --

def test_cu5_manual_order_with_picked_customer_id(env):
    db = env["db"]
    db.customers.insert_one({
        "id": "cust-5005",
        "name": "Pre Existente",
        "created": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    })
    before = db.customers.count_documents({})
    env["set_actor"](EMPLOYEE_ST_ID)

    resp = env["client"].post(
        "/api/v1/orders",
        json=_payload(customer="Pre Existente", customer_id="cust-5005"),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["customer_id"] == "cust-5005"
    # A picked id is used as-is: no new customer is created.
    assert db.customers.count_documents({}) == before


# ---- T-CU6: manual order with a typed unknown name creates a name-only row --

def test_cu6_manual_order_with_typed_name_creates_name_only_customer(env):
    db = env["db"]
    before = db.customers.count_documents({})
    env["set_actor"](EMPLOYEE_ST_ID)

    resp = env["client"].post(
        "/api/v1/orders", json=_payload(customer="Cliente Nuevo CU6")
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["customer_id"]
    assert cid is not None and cid.startswith("cust-")
    assert db.customers.count_documents({}) == before + 1

    created = db.customers.find_one({"id": cid})
    assert created["name"] == "Cliente Nuevo CU6"
    assert created.get("phone") in (None, "")  # name-only row


# ---- T-ORD-LINK1: typed unknown name links the created name-only customer ---

def test_ord_link1_manual_order_typed_name_stamps_created_customer_id(env):
    db = env["db"]
    before = db.customers.count_documents({})
    env["set_actor"](EMPLOYEE_ST_ID)

    resp = env["client"].post(
        "/api/v1/orders", json=_payload(customer="Mesa 1")
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["customer_id"]
    # The id returned by create_name_only reaches the order — it is NOT dropped.
    assert cid is not None and cid.startswith("cust-")
    assert db.customers.count_documents({}) == before + 1

    # And the persisted order (not just the response) carries the same id.
    stored_order = db.orders.find_one({"id": resp.json()["id"]})
    assert stored_order["customer_id"] == cid

    created = db.customers.find_one({"id": cid})
    assert created is not None
    assert created["name"] == "Mesa 1"  # name == the typed name


# ---- T-ORD-LINK2: picked customer_id is used as-is; no new customer made -----

def test_ord_link2_manual_order_picked_id_links_without_creating(env):
    db = env["db"]
    db.customers.insert_one({
        "id": "cust-6006",
        "name": "Cliente Elegido",
        "created": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    })
    before = db.customers.count_documents({})
    env["set_actor"](EMPLOYEE_ST_ID)

    resp = env["client"].post(
        "/api/v1/orders",
        json=_payload(customer="Cliente Elegido", customer_id="cust-6006"),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["customer_id"] == "cust-6006"
    stored_order = db.orders.find_one({"id": resp.json()["id"]})
    assert stored_order["customer_id"] == "cust-6006"
    # A picked id is used as-is: no new customer row is created.
    assert db.customers.count_documents({}) == before


# ---- T-CU7: an authenticated customer order links the caller's canonical id -

def test_cu7_authenticated_customer_order_links_canonical_id(env):
    db = env["db"]
    db.customers.insert_one({
        "_id": ObjectId(),
        "id": "cust-7007",
        "name": "Caro Canon",
        "email": "caro@ex.com",
        "supertokens_user_id": "st-caro-7",
    })
    env["set_actor"]("st-caro-7")

    resp = env["client"].post("/api/v1/orders", json=_payload())
    assert resp.status_code == 201, resp.text
    assert resp.json()["customer_id"] == "cust-7007"
