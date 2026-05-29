"""Backfill canonicalization against the REAL legacy auth row shape.

The legacy `customers` collection holds SuperTokens auth rows shaped exactly
like::

    {email, full_name, first_name, last_name, supertokens_user_id,
     is_active, created_at, updated_at}

with NO canonical `id`, NO `name`, NO `phone_normalized` and timestamps named
`created_at`/`updated_at` (not `created`/`updated`). These tests pin the
backfill selector to that shape: a row is canonicalized iff it lacks an `id`,
`scanned` counts rows examined and `updated` counts rows actually rewritten.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _auth_row(**overrides) -> dict:
    """The EXACT real legacy auth row shape (no canonical `id`)."""
    created_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    base = {
        "email": "Lucia@Ex.com",
        "full_name": "Lucía Pérez",
        "first_name": "Lucía",
        "last_name": "Pérez",
        "supertokens_user_id": "st-lucia",
        "is_active": True,
        "created_at": created_at,
        "updated_at": created_at,
    }
    base.update(overrides)
    return base


# T-BF1 ---------------------------------------------------------------------

def test_bf1_legacy_auth_row_is_scanned_and_canonicalized(api_client):
    client, db = api_client
    db.customers.insert_one(_auth_row())

    resp = client.post("/api/v1/customers/backfill")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanned"] >= 1
    assert body["updated"] >= 1

    row = db.customers.find_one({"supertokens_user_id": "st-lucia"})
    assert str(row["id"]).startswith("cust-")
    assert row["name"] == "Lucía Pérez"  # name == full_name
    assert row["email_normalized"] == "lucia@ex.com"  # lower(email)
    assert row["supertokens_user_id"] == "st-lucia"  # preserved
    # Canonical timestamps copied from the auth fields, originals kept.
    assert row["created"] == row["created_at"]
    assert row["updated"] == row["updated_at"]


# T-BF2 ---------------------------------------------------------------------

def test_bf2_backfill_is_idempotent(api_client):
    client, db = api_client
    db.customers.insert_one(_auth_row())

    first = client.post("/api/v1/customers/backfill").json()
    assert first["updated"] >= 1
    row1 = db.customers.find_one({"supertokens_user_id": "st-lucia"})
    saved_id = row1["id"]

    second = client.post("/api/v1/customers/backfill").json()
    assert second["updated"] == 0  # nothing left to canonicalize

    row2 = db.customers.find_one({"supertokens_user_id": "st-lucia"})
    assert row2["id"] == saved_id  # unchanged
    assert row2["name"] == "Lucía Pérez"
    assert db.customers.count_documents({"supertokens_user_id": "st-lucia"}) == 1


# T-BF3 ---------------------------------------------------------------------

def test_bf3_already_canonical_row_is_not_touched(api_client):
    client, db = api_client
    created = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    db.customers.insert_one({
        "id": "cust-4242",
        "name": "Ya Canónica",
        "email": "ya@ex.com",
        "email_normalized": "ya@ex.com",
        "is_active": True,
        "created": created,
        "updated": created,
    })

    body = client.post("/api/v1/customers/backfill").json()
    # A row that already has an `id` may be scanned but is never rewritten.
    assert body["scanned"] >= 1
    assert body["updated"] == 0

    row = db.customers.find_one({"id": "cust-4242"})
    assert row["name"] == "Ya Canónica"  # untouched
    # The canonical timestamps are left exactly as they were (no `created_at`
    # was minted onto an already-canonical row).
    assert row["created"] == row["updated"]
    assert "created_at" not in row


# T-BF4 ---------------------------------------------------------------------

def test_bf4_name_falls_back_to_first_last_then_email_localpart(api_client):
    client, db = api_client
    # full_name empty -> "first last".
    db.customers.insert_one(_auth_row(
        full_name="",
        first_name="Mara",
        last_name="Gómez",
        email="mara@ex.com",
        supertokens_user_id="st-mara",
    ))
    # full_name + first + last empty -> email local-part.
    db.customers.insert_one(_auth_row(
        full_name="",
        first_name="",
        last_name="",
        email="solo.email@ex.com",
        supertokens_user_id="st-solo",
    ))

    body = client.post("/api/v1/customers/backfill").json()
    assert body["updated"] >= 2

    by_first_last = db.customers.find_one({"supertokens_user_id": "st-mara"})
    assert by_first_last["name"] == "Mara Gómez"

    by_email = db.customers.find_one({"supertokens_user_id": "st-solo"})
    assert by_email["name"] == "solo.email"


# T-BF5 ---------------------------------------------------------------------

def test_bf5_mixed_collection_updates_only_the_legacy_row(api_client):
    client, db = api_client
    created = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    # 1 already-canonical row.
    db.customers.insert_one({
        "id": "cust-1001",
        "name": "Canónica",
        "is_active": True,
        "created": created,
        "updated": created,
    })
    # 1 legacy auth row (no id).
    db.customers.insert_one(_auth_row(supertokens_user_id="st-mixed"))

    body = client.post("/api/v1/customers/backfill").json()
    assert body["scanned"] >= 2  # both rows examined
    assert body["updated"] == 1  # exactly the legacy one rewritten

    legacy = db.customers.find_one({"supertokens_user_id": "st-mixed"})
    assert str(legacy["id"]).startswith("cust-")
    assert legacy["id"] != "cust-1001"  # no id collision with the canonical row

    canonical = db.customers.find_one({"id": "cust-1001"})
    assert canonical["name"] == "Canónica"  # untouched
