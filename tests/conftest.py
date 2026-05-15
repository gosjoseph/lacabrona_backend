"""Pytest fixtures for the La Cabrona backend.

Sets ENVIRONMENT=test before any app import so SuperTokens init is a no-op,
and exposes a mongomock-backed `mongo_test_db` fixture for the override
resolver tests.
"""

import os

# CRITICAL: set ENVIRONMENT before any app module is imported.
os.environ.setdefault("ENVIRONMENT", "test")

import mongomock
import pytest


@pytest.fixture
def mongo_test_db():
    """An in-memory mongomock database with empty customers/employees collections."""
    client = mongomock.MongoClient()
    db = client["lacabrona_test"]
    # Ensure the collections exist (mongomock creates them lazily; explicit drop
    # guarantees a clean slate per test).
    db.customers.drop()
    db.employees.drop()
    yield db
    client.close()
