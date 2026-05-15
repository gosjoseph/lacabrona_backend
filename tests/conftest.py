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
        orders_ctrl.get_service: lambda: OrderService(OrderRepository(mongo_test_db)),
        reservations_ctrl.get_service: lambda: ReservationService(
            ReservationRepository(mongo_test_db)
        ),
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client, mongo_test_db
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)
