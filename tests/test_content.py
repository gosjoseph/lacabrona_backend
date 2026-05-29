"""Tests for the free-form site-content store.

Covers the ungated read, the employee-gated per-key upsert write, the
read-never-writes guarantee, type validation and the open keyspace.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.content import controller as content_ctrl
from app.modules.content.repository import ContentRepository
from app.modules.content.service import ContentService
from tests.conftest import employee_auth_overrides


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def content_client(mongo_test_db):
    """Employee client with the content service bound to mongomock."""
    db = mongo_test_db
    overrides = {
        content_ctrl.get_service: lambda: ContentService(ContentRepository(db)),
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
def anon_content_client(mongo_test_db):
    """Anonymous client — no session override, so `_session_dep` returns 401."""
    from app.modules.auth import dependencies as auth_deps
    from app.modules.auth.service import AuthService

    db = mongo_test_db
    overrides = {
        content_ctrl.get_service: lambda: ContentService(ContentRepository(db)),
        auth_deps.get_auth_service: lambda: AuthService.from_db(db),
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


def _item(value: str, *, type: str = "text", group: str = "hero") -> dict:
    return {"type": type, "value": value, "group": group}


# ---- T-C1: empty DB read returns {} and does not write ---------------------


def test_get_content_empty_db_returns_empty_and_does_not_write(content_client):
    client, db = content_client
    resp = client.get("/api/v1/content")
    assert resp.status_code == 200
    assert resp.json() == {"items": {}}
    # The read must never create documents.
    assert db.content.count_documents({}) == 0


# ---- T-C2: PUT one key round-trips with type/value/group -------------------


def test_put_one_key_round_trips(content_client):
    client, _ = content_client
    body = {"items": {"hero.lede": _item("Hola mundo", type="richtext", group="hero")}}
    resp = client.put("/api/v1/content", json=body)
    assert resp.status_code == 200
    assert resp.json()["items"]["hero.lede"] == {
        "type": "richtext",
        "value": "Hola mundo",
        "group": "hero",
    }
    again = client.get("/api/v1/content").json()
    assert again["items"]["hero.lede"] == {
        "type": "richtext",
        "value": "Hola mundo",
        "group": "hero",
    }


# ---- T-C3: PUT is a per-key upsert -----------------------------------------


def test_put_is_per_key_upsert(content_client):
    client, _ = content_client
    client.put("/api/v1/content", json={"items": {"a": _item("A", group="hero")}})
    # A second PUT of a different key must leave key A untouched.
    client.put("/api/v1/content", json={"items": {"b": _item("B", group="menu")}})
    items = client.get("/api/v1/content").json()["items"]
    assert items["a"] == {"type": "text", "value": "A", "group": "hero"}
    assert items["b"] == {"type": "text", "value": "B", "group": "menu"}
    # Re-PUTting key A replaces only A.
    client.put("/api/v1/content", json={"items": {"a": _item("A2", group="hero")}})
    items = client.get("/api/v1/content").json()["items"]
    assert items["a"]["value"] == "A2"
    assert items["b"]["value"] == "B"


# ---- T-C4: invalid type -> 422 ---------------------------------------------


def test_invalid_type_rejected(content_client):
    client, _ = content_client
    resp = client.put(
        "/api/v1/content",
        json={"items": {"x": {"type": "html", "value": "v", "group": "hero"}}},
    )
    assert resp.status_code == 422


# ---- T-C5: free-form keyspace ----------------------------------------------


def test_free_form_key_round_trips(content_client):
    client, _ = content_client
    key = "brand.new.section.headline"
    client.put(
        "/api/v1/content",
        json={"items": {key: _item("línea1\nlínea2", type="richtext", group="about")}},
    )
    items = client.get("/api/v1/content").json()["items"]
    assert items[key] == {
        "type": "richtext",
        "value": "línea1\nlínea2",
        "group": "about",
    }


# ---- T-C6: anonymous PUT -> 401 --------------------------------------------


def test_anonymous_put_unauthorized(anon_content_client):
    resp = anon_content_client.put("/api/v1/content", json={"items": {}})
    assert resp.status_code == 401
