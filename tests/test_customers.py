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
