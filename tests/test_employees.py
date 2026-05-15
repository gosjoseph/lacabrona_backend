"""Tests for the employees module: model, repository, and service."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId

from app.modules.employees.model import Employee
from app.modules.employees.repository import EmployeeRepository
from app.modules.employees.service import EmployeeService


def _service(db):
    return EmployeeService(EmployeeRepository(db))


def test_repository_find_by_email_returns_none_when_missing(mongo_test_db):
    repo = EmployeeRepository(mongo_test_db)
    assert repo.find_by_email("missing@ex.com") is None


def test_repository_stamp_supertokens_id_sets_field_and_updated_at(mongo_test_db):
    repo = EmployeeRepository(mongo_test_db)
    employee_id = ObjectId()
    mongo_test_db.employees.insert_one({"_id": employee_id, "email": "e@ex.com"})

    repo.stamp_supertokens_id(employee_id, "st-e")

    stored = mongo_test_db.employees.find_one({"_id": employee_id})
    assert stored["supertokens_user_id"] == "st-e"
    assert isinstance(stored["updated_at"], datetime)


def test_service_link_returns_none_when_email_unknown(mongo_test_db):
    svc = _service(mongo_test_db)
    assert svc.link_to_supertokens("none@ex.com", "anything") is None


def test_service_link_stamps_when_no_existing_id(mongo_test_db):
    employee_id = ObjectId()
    mongo_test_db.employees.insert_one({
        "_id": employee_id,
        "email": "linkme@ex.com",
        "role": "admin",
    })
    svc = _service(mongo_test_db)

    result = svc.link_to_supertokens("linkme@ex.com", "st-link")
    assert result is not None
    assert str(result["_id"]) == str(employee_id)

    stored = mongo_test_db.employees.find_one({"_id": employee_id})
    assert stored["supertokens_user_id"] == "st-link"


def test_service_link_does_not_overwrite_existing_id(mongo_test_db):
    employee_id = ObjectId()
    mongo_test_db.employees.insert_one({
        "_id": employee_id,
        "email": "alreadylinked@ex.com",
        "role": "admin",
        "supertokens_user_id": "old-id",
    })
    svc = _service(mongo_test_db)

    result = svc.link_to_supertokens("alreadylinked@ex.com", "new-id")
    assert result is not None
    stored = mongo_test_db.employees.find_one({"_id": employee_id})
    assert stored["supertokens_user_id"] == "old-id"


def test_employee_model_defaults():
    e = Employee()
    assert e.role == "admin"
    assert e.is_active is True
    assert e.created_at is not None
    assert e.updated_at is not None
