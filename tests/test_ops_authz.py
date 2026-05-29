"""Authorization contract tests for the ops write endpoints.

Every mutating route (POST/PUT/PATCH/DELETE) under the seven business routers
must require a SuperTokens session linked to an employee — with the single
exception of `POST /api/v1/reservations`, which stays public for customer
bookings.

The mutating-route inventory is built by introspecting the live app so a new
gated-by-design endpoint can never silently slip past the gate (see T-A6).
"""

from __future__ import annotations

import re

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth import controller as auth_ctrl
from app.modules.auth import dependencies as auth_deps
from app.modules.auth.service import AuthService
from app.modules.categories import controller as categories_ctrl
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.service import CategoryService
from app.modules.customers import controller as customers_ctrl
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.service import CustomerService
from app.modules.inventory import controller as inventory_ctrl
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.service import InventoryService
from app.modules.menu import controller as menu_ctrl
from app.modules.menu.repository import MenuRepository
from app.modules.menu.service import MenuService
from app.modules.orders import controller as orders_ctrl
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.reservations import controller as reservations_ctrl
from app.modules.reservations.repository import ReservationRepository
from app.modules.reservations.service import ReservationService

# ---- Route-policy constants ------------------------------------------------

BUSINESS_PREFIXES = (
    "/api/v1/categories",
    "/api/v1/menu",
    "/api/v1/inventory",
    "/api/v1/orders",
    "/api/v1/reservations",
    "/api/v1/customers",
    "/api/v1/uploads",
)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC_WRITE = {("POST", "/api/v1/reservations")}

EMPLOYEE_ST_ID = "st-employee-authz"
CUSTOMER_ST_ID = "st-customer-authz"


def _mutating_business_routes() -> set[tuple[str, str]]:
    """All (method, path) mutating routes under the seven business prefixes."""
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        if not path.startswith(BUSINESS_PREFIXES):
            continue
        for method in methods & MUTATING_METHODS:
            routes.add((method, path))
    return routes


def _fill(path: str) -> str:
    """Substitute path params with a dummy value so the route can be reached."""
    return re.sub(r"\{[^}]+\}", "test-id", path)


# ---- Fixtures --------------------------------------------------------------


def _service_overrides(db) -> dict:
    """The same business-service overrides as the shared `api_client` fixture,
    plus the auth-service provider bound to the seeded mongomock db."""
    return {
        categories_ctrl.get_service: lambda: CategoryService(CategoryRepository(db)),
        menu_ctrl.get_service: lambda: MenuService(MenuRepository(db)),
        inventory_ctrl.get_service: lambda: InventoryService(InventoryRepository(db)),
        orders_ctrl.get_service: lambda: OrderService(OrderRepository(db)),
        reservations_ctrl.get_service: lambda: ReservationService(
            ReservationRepository(db)
        ),
        customers_ctrl.get_customers_service: lambda: CustomerService(
            CustomerRepository(db)
        ),
        auth_deps.get_auth_service: lambda: AuthService.from_db(db),
    }


class _FakeSession:
    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def get_user_id(self) -> str:
        return self._user_id


@pytest.fixture
def seeded_db(mongo_test_db):
    """Seed one employee and one customer linked to SuperTokens ids."""
    mongo_test_db.employees.insert_one({
        "_id": ObjectId(),
        "email": "staff@lacabrona.uy",
        "name": "Staff Authz",
        "role": "admin",
        "supertokens_user_id": EMPLOYEE_ST_ID,
    })
    mongo_test_db.customers.insert_one({
        "_id": ObjectId(),
        "email": "cliente@lacabrona.uy",
        "first_name": "Clienta",
        "last_name": "Prueba",
        "supertokens_user_id": CUSTOMER_ST_ID,
    })
    return mongo_test_db


def _client(db, session_user_id: str | None):
    """Build a TestClient with services bound to `db` and an optional session.

    Returns (client, overrides) — the caller is responsible for clearing the
    overrides via the fixtures' teardown.
    """
    overrides = _service_overrides(db)
    if session_user_id is not None:
        overrides[auth_ctrl._session_dep] = lambda: _FakeSession(session_user_id)
    app.dependency_overrides.update(overrides)
    return TestClient(app), overrides


@pytest.fixture
def as_employee(seeded_db):
    client, overrides = _client(seeded_db, EMPLOYEE_ST_ID)
    try:
        with client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


@pytest.fixture
def as_customer(seeded_db):
    client, overrides = _client(seeded_db, CUSTOMER_ST_ID)
    try:
        with client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


@pytest.fixture
def as_anonymous(seeded_db):
    # No session override: `_session_dep`'s test stub raises 401.
    client, overrides = _client(seeded_db, None)
    try:
        with client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


# ---- T-A1: anonymous → 401 -------------------------------------------------

def test_anonymous_blocked_on_all_gated_mutations(as_anonymous):
    gated = _mutating_business_routes() - PUBLIC_WRITE
    assert gated, "introspection found no gated mutating routes"
    for method, path in sorted(gated):
        resp = as_anonymous.request(method, _fill(path), json={})
        assert resp.status_code == 401, f"{method} {path} -> {resp.status_code}"


# ---- T-A2: customer → 403 --------------------------------------------------

def test_customer_forbidden_on_all_gated_mutations(as_customer):
    gated = _mutating_business_routes() - PUBLIC_WRITE
    for method, path in sorted(gated):
        resp = as_customer.request(method, _fill(path), json={})
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"


# ---- T-A3: employee → never 401/403 ---------------------------------------

def test_employee_reaches_one_route_per_gated_router(as_employee):
    """A representative valid request to one route per gated router must not be
    blocked by the gate (2xx or a clearly-validation 4xx, never 401/403)."""
    representative = [
        ("POST", "/api/v1/categories", {"json": {
            "id": "cat-1", "name": "Tacos", "icon": "ic", "color": "#fff", "order": 1,
        }}),
        ("POST", "/api/v1/menu", {"json": {
            "id": "menu-1", "category": "cat-1", "name": "Taco", "description": "d",
            "price": 100.0, "unit": "u",
        }}),
        ("POST", "/api/v1/inventory", {"json": {
            "id": "inv-1", "name": "Maíz", "category": "c", "stock": 10.0,
            "unit": "kg", "min": 1.0, "supplier": "s",
            "updated": "2026-05-28T20:00:00",
        }}),
        ("POST", "/api/v1/orders", {"json": {
            "channel": "table", "customer": "Mesa 1",
            "items": [{"id": "menu-1", "qty": 1, "subtotal": 100.0}],
        }}),
        # reservations POST is public, so exercise the gated DELETE instead.
        ("DELETE", "/api/v1/reservations/{reservation_id}", {}),
        ("POST", "/api/v1/customers", {"json": {"name": "Ana", "phone": "099111222"}}),
        ("POST", "/api/v1/uploads/image", {"files": {
            "file": ("pic.png", b"\x89PNG\r\n\x1a\n", "image/png"),
        }}),
    ]
    for method, path, kwargs in representative:
        resp = as_employee.request(method, _fill(path), **kwargs)
        assert resp.status_code not in (401, 403), (
            f"{method} {path} blocked for employee -> {resp.status_code}: {resp.text}"
        )


# ---- T-A4: public booking still works anonymously --------------------------

def test_anonymous_can_create_reservation(as_anonymous):
    body = {
        "name": "Visitante",
        "party": 2,
        "time": "2026-06-01T20:00:00",
        "phone": "099333444",
    }
    resp = as_anonymous.request("POST", "/api/v1/reservations", json=body)
    assert resp.status_code in (200, 201), resp.text


# ---- T-A5: reads stay open anonymously -------------------------------------

def test_anonymous_can_read_listings(as_anonymous):
    for path in (
        "/api/v1/categories",
        "/api/v1/menu",
        "/api/v1/inventory",
        "/api/v1/orders",
        "/api/v1/reservations",
        "/api/v1/customers",
    ):
        resp = as_anonymous.get(path)
        assert resp.status_code == 200, f"GET {path} -> {resp.status_code}"


# ---- T-A6: policy guard ----------------------------------------------------

def test_public_write_is_the_only_ungated_mutation(as_anonymous):
    """The set of mutating routes that 401 anonymously must be EXACTLY all
    mutating business routes minus PUBLIC_WRITE. Adding a new mutating endpoint
    without the gate makes this fail loudly."""
    all_mutating = _mutating_business_routes()
    blocked = set()
    for method, path in all_mutating:
        resp = as_anonymous.request(method, _fill(path), json={})
        if resp.status_code == 401:
            blocked.add((method, path))
    assert blocked == (all_mutating - PUBLIC_WRITE)
