"""Tests for the lazy MongoDB client/database accessors."""

from __future__ import annotations

import mongomock

import app.core.database as db_module


def test_get_client_caches_singleton(monkeypatch):
    monkeypatch.setattr(db_module, "_client", None)
    monkeypatch.setattr(db_module, "MongoClient", lambda url: mongomock.MongoClient())

    first = db_module.get_client()
    second = db_module.get_client()
    assert first is second


def test_get_db_returns_database_with_configured_name(monkeypatch):
    monkeypatch.setattr(db_module, "_client", None)
    monkeypatch.setattr(db_module, "MongoClient", lambda url: mongomock.MongoClient())

    db = db_module.get_db()
    assert db.name == db_module.settings.mongo_db
