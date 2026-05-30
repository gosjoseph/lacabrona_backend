"""Pytest fixtures for the La Cabrona backend.

Sets ENVIRONMENT=test before any app import so SuperTokens init is a no-op,
and exposes a mongomock-backed `mongo_test_db` fixture plus an `api_client`
fixture that wires every controller's `get_service` dependency to that same
in-memory database.
"""

import os

# CRITICAL: set ENVIRONMENT before any app module is imported.
os.environ.setdefault("ENVIRONMENT", "test")

import mongomock
import pytest
from bson import ObjectId

# SuperTokens id for the employee seeded by the auth-enabled test fixtures.
# Mutating ops routes now require an employee session, so the shared clients
# authenticate as this employee.
EMPLOYEE_ST_ID = "st-employee-fixture"


class _FakeSession:
    """Minimal stand-in for a SuperTokens session container."""

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def get_user_id(self) -> str:
        return self._user_id


def employee_auth_overrides(db) -> dict:
    """Seed an employee in `db` and return dependency overrides that make a
    request authenticate as that employee (session + auth-service binding)."""
    from app.modules.auth import controller as auth_ctrl
    from app.modules.auth import dependencies as auth_deps
    from app.modules.auth.service import AuthService

    if db.employees.find_one({"supertokens_user_id": EMPLOYEE_ST_ID}) is None:
        db.employees.insert_one({
            "_id": ObjectId(),
            "email": "fixture-staff@lacabrona.uy",
            "name": "Fixture Staff",
            "role": "admin",
            "supertokens_user_id": EMPLOYEE_ST_ID,
        })

    return {
        auth_deps.get_auth_service: lambda: AuthService.from_db(db),
        auth_ctrl._session_dep: lambda: _FakeSession(EMPLOYEE_ST_ID),
    }


@pytest.fixture
def mongo_test_db():
    """An in-memory mongomock database with empty collections per test."""
    client = mongomock.MongoClient()
    db = client["lacabrona_test"]
    for name in (
        "customers",
        "employees",
        "categories",
        "menu",
        "inventory",
        "orders",
        "reservations",
        "meta",
        "settings",
        "content",
    ):
        db[name].drop()
    yield db
    client.close()


@pytest.fixture
def api_client(mongo_test_db):
    """A FastAPI TestClient with every router's `get_service` pointing at mongomock.

    Yields `(client, db)` so tests can both hit HTTP and inspect persisted state.
    """
    from fastapi.testclient import TestClient

    from app.main import app
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

    overrides = {
        categories_ctrl.get_service: lambda: CategoryService(
            CategoryRepository(mongo_test_db)
        ),
        menu_ctrl.get_service: lambda: MenuService(MenuRepository(mongo_test_db)),
        inventory_ctrl.get_service: lambda: InventoryService(
            InventoryRepository(mongo_test_db)
        ),
        orders_ctrl.get_service: lambda: OrderService(
            OrderRepository(mongo_test_db),
            menu_repository=MenuRepository(mongo_test_db),
            inventory_service=InventoryService(InventoryRepository(mongo_test_db)),
        ),
        reservations_ctrl.get_service: lambda: ReservationService(
            ReservationRepository(mongo_test_db)
        ),
        customers_ctrl.get_customers_service: lambda: CustomerService(
            CustomerRepository(mongo_test_db)
        ),
    }
    # Authenticate every request as an employee so the gated mutating routes
    # are reachable; the business-logic assertions are unchanged.
    overrides.update(employee_auth_overrides(mongo_test_db))
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client, mongo_test_db
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)
