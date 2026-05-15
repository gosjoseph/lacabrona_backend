"""Additional unit tests for `AuthService.resolve_user_type`.

The customer/employee/empty-email branches are covered in
`test_supertokens.py`. Here we cover:
  - new-customer creation when neither side matches,
  - "ensure_linked_to_supertokens" no-op when the customer already has a stamped id,
  - employee already linked is returned without re-stamping,
  - `from_db` factory wires repositories correctly.
"""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.modules.auth.exceptions import UnknownUserError
from app.modules.auth.service import AuthService


def test_resolve_creates_new_customer_when_no_match(mongo_test_db):
    service = AuthService.from_db(mongo_test_db)
    result = service.resolve_user_type(
        email="newbie@ex.com",
        supertokens_user_id="st-newbie",
        profile={"full_name": "New Bie", "first_name": "New", "last_name": "Bie"},
    )
    assert result["user_type"] == "customer"
    assert result["internal_id"]

    stored = mongo_test_db.customers.find_one({"email": "newbie@ex.com"})
    assert stored is not None
    assert stored["full_name"] == "New Bie"
    assert stored["first_name"] == "New"
    assert stored["last_name"] == "Bie"
    assert stored["supertokens_user_id"] == "st-newbie"
    assert stored["is_active"] is True


def test_resolve_creates_customer_with_empty_profile_defaults(mongo_test_db):
    service = AuthService.from_db(mongo_test_db)
    result = service.resolve_user_type(
        email="bare@ex.com",
        supertokens_user_id="st-bare",
        profile=None,
    )
    assert result["user_type"] == "customer"

    stored = mongo_test_db.customers.find_one({"email": "bare@ex.com"})
    assert stored["full_name"] == ""
    assert stored["first_name"] == ""
    assert stored["last_name"] == ""


def test_resolve_existing_customer_already_linked_does_not_overwrite(mongo_test_db):
    customer_id = ObjectId()
    mongo_test_db.customers.insert_one({
        "_id": customer_id,
        "email": "old@ex.com",
        "full_name": "Old Name",
        "supertokens_user_id": "original-st-id",
    })

    service = AuthService.from_db(mongo_test_db)
    result = service.resolve_user_type(
        email="old@ex.com",
        supertokens_user_id="new-st-id",
    )

    assert result["user_type"] == "customer"
    assert result["internal_id"] == str(customer_id)

    stored = mongo_test_db.customers.find_one({"_id": customer_id})
    # The id stays the original one (no clobber when a value is already set).
    assert stored["supertokens_user_id"] == "original-st-id"


def test_resolve_existing_employee_already_linked_does_not_overwrite(mongo_test_db):
    employee_id = ObjectId()
    mongo_test_db.employees.insert_one({
        "_id": employee_id,
        "email": "boss@ex.com",
        "role": "manager",
        "supertokens_user_id": "boss-st-existing",
    })

    service = AuthService.from_db(mongo_test_db)
    result = service.resolve_user_type(
        email="boss@ex.com",
        supertokens_user_id="boss-st-new",
    )

    assert result["user_type"] == "employee"
    assert result["internal_id"] == str(employee_id)
    assert result["role"] == "manager"

    stored = mongo_test_db.employees.find_one({"_id": employee_id})
    assert stored["supertokens_user_id"] == "boss-st-existing"


def test_resolve_employee_without_role_defaults_to_admin(mongo_test_db):
    mongo_test_db.employees.insert_one({
        "email": "noroleguy@ex.com",
    })

    service = AuthService.from_db(mongo_test_db)
    result = service.resolve_user_type(
        email="noroleguy@ex.com",
        supertokens_user_id="st-norole",
    )

    assert result["user_type"] == "employee"
    assert result["role"] == "admin"


def test_resolve_empty_email_raises_unknown_user_error(mongo_test_db):
    service = AuthService.from_db(mongo_test_db)
    with pytest.raises(UnknownUserError):
        service.resolve_user_type(email="", supertokens_user_id="anything")


def test_unknown_user_error_is_an_exception_subclass():
    err = UnknownUserError("bad email")
    assert isinstance(err, Exception)
    assert str(err) == "bad email"
