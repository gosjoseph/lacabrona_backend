"""Tests for `app.core.utils` helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.utils import strip_mongo_id, utcnow


def test_utcnow_returns_timezone_aware_utc_datetime():
    now = utcnow()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.utcoffset() == timezone.utc.utcoffset(now)


def test_strip_mongo_id_removes_id_field():
    doc = {"_id": "abc123", "name": "thing"}
    result = strip_mongo_id(doc)
    assert "_id" not in result
    assert result == {"name": "thing"}


def test_strip_mongo_id_when_field_missing_is_noop():
    doc = {"name": "thing"}
    assert strip_mongo_id(doc) == {"name": "thing"}


def test_strip_mongo_id_mutates_in_place_and_returns_same_doc():
    doc = {"_id": 1, "x": 2}
    result = strip_mongo_id(doc)
    assert result is doc
