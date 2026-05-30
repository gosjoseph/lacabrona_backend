"""Tests for the customers module: model, repository, and service."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId

from app.modules.customers.model import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.service import CustomerService


def _service(db):
    return CustomerService(CustomerRepository(db))


def test_repository_find_by_email_returns_none_when_missing(mongo_test_db):
    repo = CustomerRepository(mongo_test_db)
    assert repo.find_by_email("missing@ex.com") is None


def test_repository_insert_then_find(mongo_test_db):
    repo = CustomerRepository(mongo_test_db)
    inserted_id = repo.insert({"email": "a@ex.com", "full_name": "A"})
    assert isinstance(inserted_id, str)
    found = repo.find_by_email("a@ex.com")
    assert found is not None
    assert str(found["_id"]) == inserted_id


def test_repository_stamp_supertokens_id_sets_field_and_updated_at(mongo_test_db):
    repo = CustomerRepository(mongo_test_db)
    customer_id = ObjectId()
    mongo_test_db.customers.insert_one({"_id": customer_id, "email": "b@ex.com"})

    repo.stamp_supertokens_id(customer_id, "st-b")

    stored = mongo_test_db.customers.find_one({"_id": customer_id})
    assert stored["supertokens_user_id"] == "st-b"
    assert isinstance(stored["updated_at"], datetime)


def test_service_find_by_email_proxies_to_repository(mongo_test_db):
    mongo_test_db.customers.insert_one({"email": "x@ex.com", "full_name": "X"})
    svc = _service(mongo_test_db)
    found = svc.find_by_email("x@ex.com")
    assert found is not None
    assert found["full_name"] == "X"


def test_service_ensure_linked_stamps_when_missing(mongo_test_db):
    customer_id = ObjectId()
    mongo_test_db.customers.insert_one({"_id": customer_id, "email": "c@ex.com"})
    svc = _service(mongo_test_db)

    svc.ensure_linked_to_supertokens({"_id": customer_id}, "st-c")

    stored = mongo_test_db.customers.find_one({"_id": customer_id})
    assert stored["supertokens_user_id"] == "st-c"


def test_service_ensure_linked_is_noop_when_already_present(mongo_test_db):
    customer_id = ObjectId()
    mongo_test_db.customers.insert_one({
        "_id": customer_id,
        "email": "d@ex.com",
        "supertokens_user_id": "existing",
    })
    svc = _service(mongo_test_db)

    svc.ensure_linked_to_supertokens(
        {"_id": customer_id, "supertokens_user_id": "existing"}, "new"
    )

    stored = mongo_test_db.customers.find_one({"_id": customer_id})
    assert stored["supertokens_user_id"] == "existing"


def test_service_create_from_profile_persists_profile_fields(mongo_test_db):
    svc = _service(mongo_test_db)
    new_id = svc.create_from_profile(
        email="e@ex.com",
        supertokens_user_id="st-e",
        profile={"full_name": "E E", "first_name": "E", "last_name": "E"},
    )
    assert isinstance(new_id, str)

    stored = mongo_test_db.customers.find_one({"email": "e@ex.com"})
    assert stored is not None
    assert stored["full_name"] == "E E"
    assert stored["first_name"] == "E"
    assert stored["last_name"] == "E"
    assert stored["supertokens_user_id"] == "st-e"
    assert stored["is_active"] is True
    assert isinstance(stored["created_at"], datetime)
    assert isinstance(stored["updated_at"], datetime)


def test_service_create_from_profile_uses_empty_strings_for_missing_keys(mongo_test_db):
    svc = _service(mongo_test_db)
    svc.create_from_profile(
        email="f@ex.com", supertokens_user_id="st-f", profile={}
    )
    stored = mongo_test_db.customers.find_one({"email": "f@ex.com"})
    assert stored["full_name"] == ""
    assert stored["first_name"] == ""
    assert stored["last_name"] == ""


def test_customer_model_defaults_active_and_timestamps():
    c = Customer()
    assert c.is_active is True
    assert c.created_at is not None
    assert c.updated_at is not None


# ---------------------------------------------------------------------------
# Directory CRUD + upsert hooks
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402

from app.modules.customers.service import normalize_phone  # noqa: E402


def _reservation_payload(**overrides) -> dict:
    base = {
        "name": "Cliente",
        "party": 4,
        "time": datetime(2026, 5, 15, 20, 0, tzinfo=timezone.utc).isoformat(),
        "table": 7,
        "status": "pending",
        "phone": "099111222",
        "note": "",
    }
    base.update(overrides)
    return base


def _order_payload(**overrides) -> dict:
    base = {
        "channel": "delivery",
        "customer": "Pedro",
        "address": "Calle 1",
        "phone": "099333444",
        "items": [{"id": "taco-1", "qty": 1, "subtotal": 100.0}],
        "delivery": 50,
        "etaMinutes": 20,
    }
    base.update(overrides)
    return base


# B01 -----------------------------------------------------------------------

def test_create_customer_assigns_first_id_and_timestamps(api_client):
    client, _ = api_client
    response = client.post(
        "/api/v1/customers",
        json={"name": "Ana", "phone": "099 111 222"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "cust-1001"
    assert body["phone_normalized"] == "099111222"
    assert body["created"] == body["updated"]


# B02 -----------------------------------------------------------------------

def test_create_customer_with_colliding_phone_merges(api_client):
    # Part 2: a phone collision between two non-auth records is no longer a 409.
    # It CONVERGES — the second create folds into the existing (older) record.
    client, db = api_client
    client.post("/api/v1/customers", json={"name": "Ana", "phone": "099111222"})
    dup = client.post(
        "/api/v1/customers",
        json={"name": "Otra", "phone": "(099) 111-222"},
    )
    assert dup.status_code == 201
    # Survivor is the older record (cust-1001 / "Ana"); a set survivor field is
    # kept, so its name is unchanged.
    assert dup.json()["id"] == "cust-1001"
    assert dup.json()["name"] == "Ana"
    # Exactly one canonical customer remains, carrying the shared phone.
    rows = [c for c in db.customers.find({"id": {"$regex": "^cust-"}})]
    assert len(rows) == 1
    assert rows[0]["phone_normalized"] == "099111222"


# B03 -----------------------------------------------------------------------

def test_list_get_and_missing_customer(api_client):
    client, _ = api_client
    client.post("/api/v1/customers", json={"name": "Ana", "phone": "099111222"})
    client.post("/api/v1/customers", json={"name": "Bea", "phone": "099333444"})

    listing = client.get("/api/v1/customers")
    assert listing.status_code == 200
    ids = [c["id"] for c in listing.json()["customers"]]
    assert set(ids) == {"cust-1001", "cust-1002"}

    one = client.get("/api/v1/customers/cust-1001")
    assert one.status_code == 200
    assert one.json()["name"] == "Ana"

    missing = client.get("/api/v1/customers/cust-9999")
    assert missing.status_code == 404


# B04 -----------------------------------------------------------------------

def test_search_matches_name_case_insensitive_and_phone_substring(api_client):
    client, _ = api_client
    client.post("/api/v1/customers", json={"name": "Alicia", "phone": "099111222"})
    client.post("/api/v1/customers", json={"name": "Bruno", "phone": "098555666"})
    client.post("/api/v1/customers", json={"name": "Carla", "phone": "099777888"})

    by_name = client.get("/api/v1/customers", params={"q": "alic"}).json()["customers"]
    assert [c["name"] for c in by_name] == ["Alicia"]

    by_phone = client.get("/api/v1/customers", params={"q": "555"}).json()["customers"]
    assert [c["name"] for c in by_phone] == ["Bruno"]

    no_partial = client.get(
        "/api/v1/customers", params={"q": "xyz-not-in-anything"}
    ).json()["customers"]
    assert no_partial == []


# B05 -----------------------------------------------------------------------

def test_update_partial_fields_bumps_updated(api_client):
    client, _ = api_client
    created = client.post(
        "/api/v1/customers", json={"name": "Ana", "phone": "099111222"}
    ).json()
    original_updated = created["updated"]

    response = client.put(
        "/api/v1/customers/cust-1001", json={"notes": "VIP"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["notes"] == "VIP"
    assert body["name"] == "Ana"  # unchanged
    assert body["phone"] == "099111222"  # unchanged
    assert body["updated"] != original_updated


# B06 -----------------------------------------------------------------------

def test_update_phone_to_colliding_value_merges(api_client):
    # Part 2: editing a record's phone onto another non-auth record's number
    # CONVERGES the two instead of returning a 409.
    client, db = api_client
    client.post("/api/v1/customers", json={"name": "Ana", "phone": "099111222"})
    client.post("/api/v1/customers", json={"name": "Bea", "phone": "099333444"})

    response = client.put(
        "/api/v1/customers/cust-1002",
        json={"name": "Bea Edit", "phone": "099-111-222"},
    )
    assert response.status_code == 200
    # Survivor is the older record (Ana / cust-1001); a set survivor field
    # (its name) is kept, so the edited "Bea Edit" name is not adopted.
    assert response.json()["id"] == "cust-1001"
    assert response.json()["name"] == "Ana"
    # The edited record was merged away; only the survivor remains.
    assert db.customers.find_one({"id": "cust-1002"}) is None
    assert db.customers.count_documents({"id": {"$regex": "^cust-"}}) == 1


# B07 -----------------------------------------------------------------------

def test_delete_returns_204_then_404(api_client):
    client, _ = api_client
    client.post("/api/v1/customers", json={"name": "Ana", "phone": "099111222"})
    first = client.delete("/api/v1/customers/cust-1001")
    assert first.status_code == 204
    second = client.delete("/api/v1/customers/cust-1001")
    assert second.status_code == 404


# B08 -----------------------------------------------------------------------

def test_backfill_creates_unique_customers_and_is_idempotent(api_client):
    client, db = api_client
    db.reservations.insert_many([
        {"id": "rs-1", "name": "Ana", "phone": "099111222"},
        {"id": "rs-2", "name": "Bea", "phone": "099333444"},
        # Overlap with order below — same phone, same name -> dedup.
        {"id": "rs-3", "name": "Carlos", "phone": "099555666"},
    ])
    db.orders.insert_many([
        {"id": "ord-1", "customer": "Carlos", "phone": "099555666"},
        {"id": "ord-2", "customer": "Diego", "phone": "099777888"},
        {"id": "ord-3", "customer": "NoPhone"},  # no phone -> skipped
    ])

    first = client.post("/api/v1/customers/backfill")
    assert first.status_code == 200
    body = first.json()
    assert body["created"] == 4  # Ana, Bea, Carlos, Diego
    assert body["updated"] == 0

    listing = client.get("/api/v1/customers").json()["customers"]
    phones = sorted(c["phone_normalized"] for c in listing)
    assert phones == ["099111222", "099333444", "099555666", "099777888"]

    second = client.post("/api/v1/customers/backfill").json()
    assert second["created"] == 0
    assert second["updated"] == 0


# B09 -----------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+598 99 888 777", "+59899888777"),
        ("(099) 123-456", "099123456"),
        ("  099.123.456 ", "099123456"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


# B10 -----------------------------------------------------------------------

def test_reservation_create_triggers_customer_upsert_with_last_write_wins_name(
    api_client,
):
    client, _ = api_client
    client.post(
        "/api/v1/reservations", json=_reservation_payload(name="Ana", phone="099111222")
    )
    after_first = client.get("/api/v1/customers").json()["customers"]
    assert len(after_first) == 1
    assert after_first[0]["name"] == "Ana"
    assert after_first[0]["phone_normalized"] == "099111222"

    client.post(
        "/api/v1/reservations",
        json=_reservation_payload(name="Ana Updated", phone="(099) 111-222"),
    )
    after_second = client.get("/api/v1/customers").json()["customers"]
    assert len(after_second) == 1  # still one entry — same phone
    assert after_second[0]["name"] == "Ana Updated"


# B11 -----------------------------------------------------------------------

def test_reservation_update_with_new_phone_creates_new_customer(api_client):
    client, _ = api_client
    client.post(
        "/api/v1/reservations",
        json=_reservation_payload(name="Ana", phone="099111222"),
    )
    # rs id assigned by service (rs-2401 baseline).
    client.put(
        "/api/v1/reservations/rs-2401",
        json={"phone": "099999000"},
    )
    customers = client.get("/api/v1/customers").json()["customers"]
    phones = sorted(c["phone_normalized"] for c in customers)
    assert phones == ["099111222", "099999000"]


# B12 -----------------------------------------------------------------------

def test_order_create_with_phone_upserts_without_phone_does_not(api_client):
    client, _ = api_client
    with_phone = client.post("/api/v1/orders", json=_order_payload())
    assert with_phone.status_code == 201
    assert len(client.get("/api/v1/customers").json()["customers"]) == 1

    no_phone = client.post(
        "/api/v1/orders", json=_order_payload(channel="table", phone=None, address=None)
    )
    assert no_phone.status_code == 201
    # Still only the first customer.
    assert len(client.get("/api/v1/customers").json()["customers"]) == 1


# B13 -----------------------------------------------------------------------

def test_reservation_create_succeeds_even_when_upsert_raises(api_client, monkeypatch):
    client, _ = api_client
    from app.modules.customers.service import CustomerService

    def boom(self, *_, **__):
        raise RuntimeError("upstream broken")

    monkeypatch.setattr(CustomerService, "upsert", boom)

    response = client.post(
        "/api/v1/reservations",
        json=_reservation_payload(name="Ana", phone="099111222"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "rs-2401"
    assert body["name"] == "Ana"


# ---------------------------------------------------------------------------
# Canonical customers (Part 1): schema, backfill, auth get-or-create, search
# ---------------------------------------------------------------------------

from app.modules.customers.service import normalize_email  # noqa: E402


# T-CU1 ---------------------------------------------------------------------

def test_cu1_directory_create_has_canonical_fields(api_client):
    client, _ = api_client
    resp = client.post(
        "/api/v1/customers",
        json={"name": "Caro", "phone": "099 111 222", "email": "Caro@EX.com"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == "cust-1001"
    assert body["name"] == "Caro"
    assert body["phone_normalized"] == "099111222"
    assert body["email_normalized"] == "caro@ex.com"
    assert body["is_active"] is True


def test_cu1_directory_create_name_only_has_no_phone_index_field(api_client):
    client, db = api_client
    first = client.post("/api/v1/customers", json={"name": "Solo Nombre"})
    second = client.post("/api/v1/customers", json={"name": "Otro Nombre"})
    # Two name-only customers must coexist (no phone_normalized="" collision).
    assert first.status_code == 201
    assert second.status_code == 201
    stored = db.customers.find_one({"id": first.json()["id"]})
    assert "phone_normalized" not in stored
    assert stored["name"] == "Solo Nombre"


# T-CU2 ---------------------------------------------------------------------

def test_cu2_backfill_canonicalizes_legacy_auth_row_and_is_idempotent(api_client):
    client, db = api_client
    created_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    db.customers.insert_one({
        "email": "Lucia@Ex.com",
        "full_name": "Lucía Pérez",
        "first_name": "Lucía",
        "last_name": "Pérez",
        "supertokens_user_id": "st-lucia",
        "is_active": True,
        "created_at": created_at,
        "updated_at": created_at,
    })

    first = client.post("/api/v1/customers/backfill")
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["canonicalized"] == 1
    # The legacy auth row is examined and rewritten — surfaced as scanned/updated.
    assert first_body["scanned"] >= 1
    assert first_body["updated"] == 1

    row = db.customers.find_one({"supertokens_user_id": "st-lucia"})
    assert str(row["id"]).startswith("cust-")
    assert row["name"] == "Lucía Pérez"
    assert row["email_normalized"] == "lucia@ex.com"
    # `created`/`updated` are copied from the legacy auth timestamps.
    assert row["created"] == row["created_at"]
    assert row["updated"] == row["updated_at"]
    saved_id = row["id"]

    # Running it again changes nothing.
    second = client.post("/api/v1/customers/backfill")
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["canonicalized"] == 0
    assert second_body["updated"] == 0
    row2 = db.customers.find_one({"supertokens_user_id": "st-lucia"})
    assert row2["id"] == saved_id
    assert row2["name"] == "Lucía Pérez"
    assert db.customers.count_documents({"supertokens_user_id": "st-lucia"}) == 1


# T-CU3 ---------------------------------------------------------------------

def test_cu3_get_or_create_for_auth_no_duplicate_on_repeat(mongo_test_db):
    svc = _service(mongo_test_db)
    first = svc.get_or_create_for_auth("st-x", "x@ex.com", "X Name")
    assert first["supertokens_user_id"] == "st-x"
    assert str(first["id"]).startswith("cust-")
    assert first["name"] == "X Name"
    count = mongo_test_db.customers.count_documents({})

    second = svc.get_or_create_for_auth("st-x", "x@ex.com", "X Name")
    assert second["_id"] == first["_id"]
    assert mongo_test_db.customers.count_documents({}) == count


# T-CU4 ---------------------------------------------------------------------

def test_cu4_get_or_create_for_auth_links_existing_email_match(mongo_test_db):
    oid = ObjectId()
    mongo_test_db.customers.insert_one({
        "_id": oid,
        "id": "cust-1001",
        "name": "Existing",
        "email": "match@ex.com",
        "email_normalized": normalize_email("match@ex.com"),
    })
    svc = _service(mongo_test_db)

    # Different casing must still match via email_normalized.
    result = svc.get_or_create_for_auth("st-match", "MATCH@ex.com", "Ignored Name")

    assert result["_id"] == oid
    assert result["supertokens_user_id"] == "st-match"
    assert result["name"] == "Existing"  # link, never overwrite the name
    assert mongo_test_db.customers.count_documents({}) == 1  # no new row


# T-CU8 ---------------------------------------------------------------------

def test_cu8_directory_and_search_include_backfilled_auth_row(api_client):
    client, db = api_client
    # A legacy auth row (no id, no phone) — invisible until canonicalized.
    db.customers.insert_one({
        "email": "auth.user@ex.com",
        "full_name": "Auth User",
        "supertokens_user_id": "st-auth-8",
        "is_active": True,
    })
    # A directory customer with a phone backs the phone-search assertion.
    client.post("/api/v1/customers", json={"name": "Tel Person", "phone": "099888777"})

    client.post("/api/v1/customers/backfill")

    listing = client.get("/api/v1/customers").json()["customers"]
    names = {c["name"] for c in listing}
    assert "Auth User" in names  # backfilled auth row now appears in the directory
    assert "Tel Person" in names

    by_name = client.get("/api/v1/customers", params={"q": "auth"}).json()["customers"]
    assert [c["name"] for c in by_name] == ["Auth User"]

    by_email = client.get(
        "/api/v1/customers", params={"q": "auth.user@"}
    ).json()["customers"]
    assert [c["name"] for c in by_email] == ["Auth User"]

    by_phone = client.get("/api/v1/customers", params={"q": "888"}).json()["customers"]
    assert [c["name"] for c in by_phone] == ["Tel Person"]
