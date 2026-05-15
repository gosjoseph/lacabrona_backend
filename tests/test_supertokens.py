"""SuperTokens auth wiring tests.

Cover: module import safety, override resolver behaviour for customer /
employee / unknown email, and the health endpoint reachability check.
"""

from __future__ import annotations

import httpx
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.auth import supertokens_init
from app.auth.user_resolver import UnknownUserError, resolve_user_type
from app.main import app


def test_supertokens_init_does_not_raise():
    """Importing the SuperTokens init module must not raise."""
    assert supertokens_init is not None
    # Calling init() is a no-op under ENVIRONMENT=test; it must also not raise.
    supertokens_init.init_supertokens()


def test_override_resolves_customer_by_email(mongo_test_db):
    """A customer email returns user_type='customer' and stamps the user id."""
    customer_id = ObjectId()
    mongo_test_db.customers.insert_one({
        "_id": customer_id,
        "email": "cliente@lacabrona.uy",
        "name": "Cliente Uno",
    })

    result = resolve_user_type(
        email="cliente@lacabrona.uy",
        supertokens_user_id="st-user-customer",
        db=mongo_test_db,
    )

    assert result["user_type"] == "customer"
    assert result["internal_id"] == str(customer_id)

    stored = mongo_test_db.customers.find_one({"_id": customer_id})
    assert stored["supertokens_user_id"] == "st-user-customer"


def test_override_resolves_employee_by_email(mongo_test_db):
    """An employee email returns user_type='employee' and stamps the user id."""
    employee_id = ObjectId()
    mongo_test_db.employees.insert_one({
        "_id": employee_id,
        "email": "staff@lacabrona.uy",
        "name": "Staff Uno",
        "role": "admin",
    })

    result = resolve_user_type(
        email="staff@lacabrona.uy",
        supertokens_user_id="st-user-employee",
        db=mongo_test_db,
    )

    assert result["user_type"] == "employee"
    assert result["internal_id"] == str(employee_id)
    assert result["role"] == "admin"

    stored = mongo_test_db.employees.find_one({"_id": employee_id})
    assert stored["supertokens_user_id"] == "st-user-employee"


def test_override_rejects_empty_email(mongo_test_db):
    """An empty/missing email must raise UnknownUserError."""
    with pytest.raises(UnknownUserError):
        resolve_user_type(
            email="",
            supertokens_user_id="st-user-unknown",
            db=mongo_test_db,
        )


def test_health_endpoint_200_when_supertokens_up(httpx_mock):
    """Health endpoint returns 200 when the SuperTokens core responds."""
    from app.config import settings

    httpx_mock.add_response(
        url=f"{settings.supertokens_core_url.rstrip('/')}/hello",
        status_code=200,
        text="Hello",
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health/supertokens")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_endpoint_503_when_supertokens_down(httpx_mock):
    """Health endpoint returns 503 when the SuperTokens core is unreachable."""
    from app.config import settings

    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url=f"{settings.supertokens_core_url.rstrip('/')}/hello",
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health/supertokens")

    assert response.status_code == 503
