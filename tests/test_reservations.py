"""End-to-end tests for the reservations router (controller + service + repo)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.reservations.repository import ReservationRepository
from app.modules.reservations.service import ReservationService


def _payload(**overrides) -> dict:
    base = {
        "name": "Cliente",
        "party": 4,
        "time": datetime(2026, 5, 15, 20, 0, tzinfo=timezone.utc).isoformat(),
        "table": 7,
        "status": "pending",
        "phone": "099",
        "note": "",
    }
    base.update(overrides)
    return base


def test_create_assigns_first_id(api_client):
    client, _ = api_client
    response = client.post("/api/reservations", json=_payload())
    assert response.status_code == 201
    assert response.json()["id"] == "rs-2401"


def test_create_assigns_incrementing_ids(api_client):
    client, _ = api_client
    first = client.post("/api/reservations", json=_payload()).json()
    second = client.post(
        "/api/reservations",
        json=_payload(time=datetime(2026, 5, 16, 20, 0, tzinfo=timezone.utc).isoformat()),
    ).json()
    assert first["id"] == "rs-2401"
    assert second["id"] == "rs-2402"


def test_list_returns_today_field_and_sorted_reservations(api_client):
    client, _ = api_client
    client.post(
        "/api/reservations",
        json=_payload(time=datetime(2026, 6, 1, 21, 0, tzinfo=timezone.utc).isoformat()),
    )
    client.post(
        "/api/reservations",
        json=_payload(time=datetime(2026, 6, 1, 19, 0, tzinfo=timezone.utc).isoformat()),
    )
    response = client.get("/api/reservations")
    assert response.status_code == 200
    body = response.json()
    assert "today" in body
    times = [r["time"] for r in body["reservations"]]
    assert times == sorted(times)


def test_list_filters_by_date(api_client):
    client, _ = api_client
    client.post(
        "/api/reservations",
        json=_payload(time=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc).isoformat()),
    )
    client.post(
        "/api/reservations",
        json=_payload(time=datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc).isoformat()),
    )
    response = client.get("/api/reservations", params={"date": "2026-06-01"})
    assert response.status_code == 200
    items = response.json()["reservations"]
    assert len(items) == 1


def test_list_invalid_date_returns_400(api_client):
    client, _ = api_client
    response = client.get("/api/reservations", params={"date": "not-a-date"})
    assert response.status_code == 400


def test_get_existing_reservation(api_client):
    client, _ = api_client
    client.post("/api/reservations", json=_payload())
    response = client.get("/api/reservations/rs-2401")
    assert response.status_code == 200
    assert response.json()["name"] == "Cliente"


def test_get_missing_reservation_returns_404(api_client):
    client, _ = api_client
    assert client.get("/api/reservations/rs-0").status_code == 404


def test_update_partial_fields(api_client):
    client, _ = api_client
    client.post("/api/reservations", json=_payload())
    response = client.put("/api/reservations/rs-2401", json={"status": "confirmed"})
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_update_with_no_fields_returns_400(api_client):
    client, _ = api_client
    client.post("/api/reservations", json=_payload())
    response = client.put("/api/reservations/rs-2401", json={})
    assert response.status_code == 400


def test_update_missing_returns_404(api_client):
    client, _ = api_client
    response = client.put("/api/reservations/rs-0", json={"status": "confirmed"})
    assert response.status_code == 404


def test_delete_existing_returns_204(api_client):
    client, db = api_client
    client.post("/api/reservations", json=_payload())
    response = client.delete("/api/reservations/rs-2401")
    assert response.status_code == 204
    assert db.reservations.find_one({"id": "rs-2401"}) is None


def test_delete_missing_returns_404(api_client):
    client, _ = api_client
    assert client.delete("/api/reservations/rs-0").status_code == 404


def test_next_id_fallback_when_existing_id_unparseable(mongo_test_db):
    mongo_test_db.reservations.insert_one({
        "id": "no-numeric",
        "time": datetime(2026, 5, 1, tzinfo=timezone.utc),
    })
    svc = ReservationService(ReservationRepository(mongo_test_db))
    next_id = svc._next_id()
    assert next_id.startswith("rs-")
    assert next_id.split("-")[1].isdigit()
