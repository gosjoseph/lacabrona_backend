"""Unit tests for `extract_profile_from_raw_info`.

Cover the precedence rules between `user_info_api` and `id_token_payload`,
splitting a single `name`, whitespace handling, and the email local-part
fallback.
"""

from __future__ import annotations

from app.auth.profile import extract_profile_from_raw_info


def test_uses_given_and_family_name_when_both_present():
    result = extract_profile_from_raw_info(
        user_info_api={
            "given_name": "María",
            "family_name": "López Hernández",
            "name": "ignored",
        },
        id_token_payload=None,
        email="x@y.com",
    )
    assert result == {
        "full_name": "María López Hernández",
        "first_name": "María",
        "last_name": "López Hernández",
    }


def test_splits_full_name_when_no_given_family():
    result = extract_profile_from_raw_info(
        user_info_api={"name": "María López Hernández"},
        id_token_payload=None,
        email="x@y.com",
    )
    assert result["first_name"] == "María"
    assert result["last_name"] == "López Hernández"
    assert result["full_name"] == "María López Hernández"


def test_single_word_name_yields_empty_last_name():
    result = extract_profile_from_raw_info(
        user_info_api={"name": "María"},
        id_token_payload=None,
        email="x@y.com",
    )
    assert result["first_name"] == "María"
    assert result["last_name"] == ""
    assert result["full_name"] == "María"


def test_falls_back_from_user_info_api_to_id_token_payload():
    result = extract_profile_from_raw_info(
        user_info_api={},
        id_token_payload={"given_name": "Juan", "family_name": "Pérez"},
        email="x@y.com",
    )
    assert result["full_name"] == "Juan Pérez"
    assert result["first_name"] == "Juan"
    assert result["last_name"] == "Pérez"


def test_prefers_user_info_api_over_id_token_payload():
    result = extract_profile_from_raw_info(
        user_info_api={"given_name": "A", "family_name": "B"},
        id_token_payload={"given_name": "X", "family_name": "Y"},
        email="x@y.com",
    )
    assert result["first_name"] == "A"
    assert result["last_name"] == "B"


def test_email_local_part_fallback_when_nothing_useful():
    result = extract_profile_from_raw_info(
        user_info_api=None,
        id_token_payload=None,
        email="juan.perez@ex.com",
    )
    assert result["full_name"] == "juan.perez"
    assert result["first_name"] == "juan.perez"
    assert result["last_name"] == ""


def test_strips_whitespace():
    result = extract_profile_from_raw_info(
        user_info_api={"name": "  María   "},
        id_token_payload=None,
        email="x@y.com",
    )
    assert result["first_name"] == "María"
    assert result["last_name"] == ""
    assert result["full_name"] == "María"


def test_empty_string_treated_as_absent():
    result = extract_profile_from_raw_info(
        user_info_api={
            "given_name": "",
            "family_name": "",
            "name": "Fallback Name",
        },
        id_token_payload=None,
        email="x@y.com",
    )
    assert result["full_name"] == "Fallback Name"
    assert result["first_name"] == "Fallback"
    assert result["last_name"] == "Name"
