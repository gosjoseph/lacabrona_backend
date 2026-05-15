"""Integration tests for the SuperTokens sign-in/up override.

Drive `_attach_internal_claims` end-to-end against a mongomock database,
covering the new-customer creation path and the existing-customer linking
path. The override extracts `raw_user_info_from_provider` from the response
and routes it through the user resolver, so we build a minimal stand-in
response object and patch `app.core.database.get_db` to return the mongomock
fixture.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.auth import supertokens


def _make_response(
    *,
    email: str,
    user_id: str,
    from_user_info_api: dict | None,
    from_id_token_payload: dict | None = None,
) -> SimpleNamespace:
    """Build a stand-in for SuperTokens' SignInUpPostOkResult."""

    async def _merge_into_access_token_payload(_payload):
        return None

    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, emails=[email]),
        session=SimpleNamespace(
            merge_into_access_token_payload=_merge_into_access_token_payload,
        ),
        raw_user_info_from_provider=SimpleNamespace(
            from_user_info_api=from_user_info_api,
            from_id_token_payload=from_id_token_payload,
        ),
    )


@pytest.fixture
def patch_get_db(monkeypatch, mongo_test_db):
    """Route `app.core.database.get_db` to the in-memory mongomock database."""
    import app.core.database as db_module

    monkeypatch.setattr(db_module, "get_db", lambda: mongo_test_db)
    return mongo_test_db


async def test_new_customer_signinup_persists_name_from_google(patch_get_db):
    db = patch_get_db
    response = _make_response(
        email="lucia@ex.com",
        user_id="st-user-lucia",
        from_user_info_api={
            "given_name": "Lucía",
            "family_name": "Suárez",
            "name": "Lucía Suárez",
            "email": "lucia@ex.com",
        },
    )

    await supertokens._attach_internal_claims(response)

    stored = db.customers.find_one({"email": "lucia@ex.com"})
    assert stored is not None
    assert stored["full_name"] == "Lucía Suárez"
    assert stored["first_name"] == "Lucía"
    assert stored["last_name"] == "Suárez"
    assert stored["supertokens_user_id"] == "st-user-lucia"


async def test_existing_customer_signinup_does_not_overwrite_name(patch_get_db):
    db = patch_get_db
    db.customers.insert_one({
        "email": "adrian@ex.com",
        "full_name": "Adrián Gómez",
        "first_name": "Adrián",
        "last_name": "Gómez",
        "is_active": True,
    })

    response = _make_response(
        email="adrian@ex.com",
        user_id="st-user-adrian",
        from_user_info_api={
            "given_name": "Wrong",
            "family_name": "Name",
            "name": "Wrong Name",
        },
    )

    await supertokens._attach_internal_claims(response)

    stored = db.customers.find_one({"email": "adrian@ex.com"})
    assert stored is not None
    assert stored["full_name"] == "Adrián Gómez"
    assert stored["first_name"] == "Adrián"
    assert stored["last_name"] == "Gómez"
    assert stored["supertokens_user_id"] == "st-user-adrian"
