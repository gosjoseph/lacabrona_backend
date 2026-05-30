"""Part 2 — customer identity convergence: merge, shared phone, email guard.

Exercises `CustomerService.resolve_identity` and its call sites against the
mongomock fixture. The rules under test:

  * EMAIL collision -> 409 when both records are distinct auth accounts, else
    MERGE.
  * PHONE collision -> SHARED PHONE when both records are distinct auth
    accounts (no merge, cross-linked), else MERGE.
  * MERGE: the auth-linked record survives; with neither linked the older one
    survives; survivor keeps its set fields and fills only its blanks from the
    loser; every order is re-pointed onto the survivor before the loser is
    deleted.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.core.utils import normalize_email, normalize_phone
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schema import CustomerUpdate
from app.modules.customers.service import CustomerService
from app.modules.reservations.model import Reservation


def _svc(db) -> CustomerService:
    return CustomerService(CustomerRepository(db))


def _seed(db, customer_id: str, **fields) -> str:
    """Insert a canonical customer row, normalizing email/phone like the app."""
    doc = {"_id": ObjectId(), "id": customer_id, "is_active": True, **fields}
    if doc.get("email") and "email_normalized" not in doc:
        doc["email_normalized"] = normalize_email(doc["email"])
    if doc.get("phone") and "phone_normalized" not in doc:
        doc["phone_normalized"] = normalize_phone(doc["phone"])
    db.customers.insert_one(doc)
    return customer_id


def _t(minute: int) -> datetime:
    return datetime(2026, 1, 1, 12, minute, tzinfo=timezone.utc)


def _update(svc, customer_id, **patch):
    return svc.update_customer(customer_id, CustomerUpdate(**patch))


# T-MG1 — email merge, survivor = the auth-linked record --------------------

def test_mg1_email_merge_survivor_is_auth_record(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    # A name-only "Janet" (no SuperTokens id) and an auth "Janet Montero".
    _seed(db, "cust-1001", name="Janet", created=_t(0))
    _seed(
        db,
        "cust-1002",
        name="Janet Montero",
        email="janet@ex.com",
        supertokens_user_id="st-janet",
        created=_t(5),
    )

    survivor = _update(svc, "cust-1001", email="janet@ex.com")

    # The auth row wins, keeping its id and SuperTokens id.
    assert survivor["id"] == "cust-1002"
    assert survivor["supertokens_user_id"] == "st-janet"
    assert survivor["name"] == "Janet Montero"
    # The name-only row was merged away.
    assert db.customers.find_one({"id": "cust-1001"}) is None
    assert db.customers.count_documents({"id": {"$regex": "^cust-"}}) == 1


# T-MG2 — field union: survivor keeps set fields, loser fills only blanks ----

def test_mg2_field_union_keeps_set_and_fills_blanks(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    # Survivor (auth) has a name but a BLANK notes; loser has notes set.
    _seed(
        db,
        "cust-1001",
        name="Survivor",
        notes="",
        email="shared@ex.com",
        supertokens_user_id="st-s",
        created=_t(0),
    )
    _seed(db, "cust-1002", name="Loser Name", notes="Nota del loser", created=_t(5))

    survivor = _update(svc, "cust-1002", email="shared@ex.com")

    assert survivor["id"] == "cust-1001"
    # A SET survivor field is unchanged...
    assert survivor["name"] == "Survivor"
    # ...and a BLANK survivor field takes the loser's value.
    assert survivor["notes"] == "Nota del loser"


# T-MG3 — order re-pointing --------------------------------------------------

def test_mg3_orders_repointed_to_survivor(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    _seed(
        db,
        "cust-1001",
        name="Auth",
        email="dup@ex.com",
        supertokens_user_id="st-a",
        created=_t(0),
    )
    _seed(db, "cust-1002", name="Dir", created=_t(5))
    db.orders.insert_many([
        {"id": "ord-1", "customer_id": "cust-1002", "customer": "Dir"},
        {"id": "ord-2", "customer_id": "cust-1002", "customer": "Dir"},
    ])

    survivor = _update(svc, "cust-1002", email="dup@ex.com")
    assert survivor["id"] == "cust-1001"

    # Both orders now point at the survivor; none point at the deleted loser.
    assert db.orders.count_documents({"customer_id": "cust-1001"}) == 2
    assert db.orders.count_documents({"customer_id": "cust-1002"}) == 0


# T-MG3b — reservations carry no customer_id (re-pointing is n/a) ------------

def test_mg3b_reservations_carry_no_customer_id(mongo_test_db):
    # Reservations have no customer_id in the schema, so there is nothing to
    # re-point — asserted explicitly per the spec.
    assert "customer_id" not in Reservation.model_fields

    db = mongo_test_db
    svc = _svc(db)
    _seed(
        db,
        "cust-1001",
        name="Auth",
        email="r@ex.com",
        supertokens_user_id="st-a",
        created=_t(0),
    )
    _seed(db, "cust-1002", name="Dir", created=_t(5))
    db.reservations.insert_one(
        {"id": "rs-1", "name": "Dir", "phone": "099111222", "party": 2}
    )

    _update(svc, "cust-1002", email="r@ex.com")

    # The reservation is untouched (no customer_id field appears).
    rs = db.reservations.find_one({"id": "rs-1"})
    assert "customer_id" not in rs


# T-MG4 — neither has stid -> older record survives --------------------------

def test_mg4_neither_auth_older_record_survives(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    _seed(db, "cust-1001", name="Older", email="x@ex.com", created=_t(0))
    _seed(db, "cust-1002", name="Newer", created=_t(5))

    survivor = _update(svc, "cust-1002", email="x@ex.com")

    # Neither is auth-linked, so the older row (cust-1001) wins.
    assert survivor["id"] == "cust-1001"
    assert survivor["name"] == "Older"
    assert db.customers.find_one({"id": "cust-1002"}) is None


# T-MG5 — shared phone: two distinct accounts, same phone, no merge ----------

def test_mg5_shared_phone_links_both_and_is_idempotent(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    _seed(
        db,
        "cust-1001",
        name="A",
        phone="099111222",
        supertokens_user_id="st-a",
        created=_t(0),
    )
    _seed(db, "cust-1002", name="B", supertokens_user_id="st-b", created=_t(5))

    result = _update(svc, "cust-1002", phone="099 111 222")

    # No merge: BOTH records still exist.
    a = db.customers.find_one({"id": "cust-1001"})
    b = db.customers.find_one({"id": "cust-1002"})
    assert a is not None and b is not None
    # Both are flagged and cross-linked.
    assert a["shared_phone"] is True and b["shared_phone"] is True
    assert a["shared_phone_with"] == ["cust-1002"]
    assert b["shared_phone_with"] == ["cust-1001"]
    assert result["id"] == "cust-1002"

    # Idempotent: re-applying the same phone does not duplicate the links.
    _update(svc, "cust-1002", phone="099111222")
    a2 = db.customers.find_one({"id": "cust-1001"})
    b2 = db.customers.find_one({"id": "cust-1002"})
    assert a2["shared_phone_with"] == ["cust-1002"]
    assert b2["shared_phone_with"] == ["cust-1001"]
    assert db.customers.count_documents({"id": {"$regex": "^cust-"}}) == 2


# T-MG6 — email conflict: two distinct accounts, same email -> 409, no change

def test_mg6_email_conflict_raises_409_and_changes_nothing(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    _seed(
        db,
        "cust-1001",
        name="A",
        email="shared@ex.com",
        supertokens_user_id="st-a",
        created=_t(0),
    )
    _seed(
        db,
        "cust-1002",
        name="B",
        email="other@ex.com",
        supertokens_user_id="st-b",
        created=_t(5),
    )

    with pytest.raises(HTTPException) as exc:
        _update(svc, "cust-1002", email="shared@ex.com")
    assert exc.value.status_code == 409

    # NO change to either record.
    a = db.customers.find_one({"id": "cust-1001"})
    b = db.customers.find_one({"id": "cust-1002"})
    assert a["email_normalized"] == "shared@ex.com"
    assert b["email_normalized"] == "other@ex.com"
    assert b["email"] == "other@ex.com"
    assert db.customers.count_documents({"id": {"$regex": "^cust-"}}) == 2


# T-MG7 — no-op: re-stating a record's own email/phone -----------------------

def test_mg7_setting_own_email_and_phone_is_a_noop(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    _seed(
        db,
        "cust-1001",
        name="Solo",
        email="solo@ex.com",
        phone="099111222",
        supertokens_user_id="st-solo",
        created=_t(0),
    )

    result = _update(svc, "cust-1001", email="solo@ex.com", phone="099111222")

    # Collides only with itself -> no merge, no error, record intact.
    assert result["id"] == "cust-1001"
    assert result["email_normalized"] == "solo@ex.com"
    assert result["phone_normalized"] == "099111222"
    assert result.get("shared_phone", False) is False
    assert db.customers.count_documents({"id": {"$regex": "^cust-"}}) == 1


# T-MG8 — get_or_create_for_auth email-link is consistent with a merge -------

def test_mg8_auth_email_link_lands_stid_without_duplicating(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    # A name-only directory row that already carries an email but no auth id.
    _seed(db, "cust-1001", name="Janet", email="janet@ex.com", created=_t(0))

    linked = svc.get_or_create_for_auth("st-new", "janet@ex.com", "Janet Google")

    # The id lands on the EXISTING row (same outcome as a merge whose survivor
    # is the auth row) — no duplicate, name untouched.
    assert linked["id"] == "cust-1001"
    assert linked["supertokens_user_id"] == "st-new"
    assert linked["name"] == "Janet"
    assert db.customers.count_documents({"id": {"$regex": "^cust-"}}) == 1


# T-MG9 — indexes: email sparse-unique, phone non-unique ---------------------

def test_mg9_index_shapes(mongo_test_db):
    db = mongo_test_db
    _svc(db)  # constructing the repository ensures the indexes
    info = db.customers.index_information()

    email_idx = info["email_normalized_unique"]
    assert email_idx.get("unique") is True
    assert email_idx.get("sparse") is True

    assert "phone_normalized_idx" in info
    assert not info["phone_normalized_idx"].get("unique")
    # The legacy sparse-unique phone index is gone.
    assert "phone_normalized_unique" not in info

    # Two shared-phone records with the SAME phone can coexist (non-unique).
    _seed(db, "cust-1001", name="A", phone="099111222", supertokens_user_id="st-a")
    _seed(db, "cust-1002", name="B", phone="099111222", supertokens_user_id="st-b")
    assert db.customers.count_documents({"phone_normalized": "099111222"}) == 2

    # Rows with NO email coexist (sparse), but a duplicate email is rejected.
    _seed(db, "cust-1003", name="C")
    _seed(db, "cust-1004", name="D")
    _seed(db, "cust-1005", name="E", email="e@ex.com")
    with pytest.raises(Exception):
        db.customers.insert_one(
            {"_id": ObjectId(), "id": "cust-1006", "email_normalized": "e@ex.com"}
        )


# T-MG10 — merge folds a loser's manual-path name-only order onto survivor ----

def test_mg10_manual_name_only_order_repoints_on_merge(mongo_test_db):
    db = mongo_test_db
    svc = _svc(db)
    # The manual order path: a typed unknown name creates a name-only customer
    # that an order points at.
    loser = svc.create_name_only("Cliente Mostrador")
    db.orders.insert_one(
        {"id": "ord-99", "customer": "Cliente Mostrador", "customer_id": loser["id"]}
    )
    # An auth customer later turns out to be the same person (shared email).
    _seed(
        db,
        "cust-2001",
        name="Cliente Real",
        email="real@ex.com",
        supertokens_user_id="st-real",
        created=_t(0),
    )

    survivor = _update(svc, loser["id"], email="real@ex.com")

    assert survivor["id"] == "cust-2001"
    # The manual-path order ends up on the survivor.
    stored = db.orders.find_one({"id": "ord-99"})
    assert stored["customer_id"] == "cust-2001"
    assert db.customers.find_one({"id": loser["id"]}) is None
