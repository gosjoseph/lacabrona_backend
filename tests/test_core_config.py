"""Tests for the pydantic-settings configuration."""

from __future__ import annotations

from app.core.config import Settings


def test_default_cors_origins_split_into_list():
    s = Settings()
    origins = s.cors_origins
    assert isinstance(origins, list)
    assert "http://localhost:5173" in origins
    assert all(o.strip() == o for o in origins)
    assert "" not in origins


def test_cors_origins_handles_extra_whitespace_and_blank_entries():
    s = Settings(CORS_ORIGINS=" http://a.com , , http://b.com ,")
    assert s.cors_origins == ["http://a.com", "http://b.com"]


def test_cors_origins_alias_accepts_env_name():
    s = Settings(CORS_ORIGINS="http://only.example")
    assert s.cors_origins == ["http://only.example"]


def test_default_supertokens_and_mongo_settings():
    s = Settings()
    assert s.mongo_url.startswith("mongodb://")
    assert s.mongo_db == "lacabrona"
    assert s.supertokens_app_name == "La Cabrona"
    assert s.environment in {"dev", "test", "prod"}
