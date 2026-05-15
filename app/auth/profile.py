"""Pure helper that derives a customer profile from Google OAuth claims.

SuperTokens exposes the provider's raw user info on the sign_in_up response
as two dicts: `from_user_info_api` (Google `userinfo` endpoint) and
`from_id_token_payload` (decoded ID token). For the default
`email profile openid` scopes Google returns the user's real name on either
or both. We pick the best signal in a deterministic order and never raise.
"""

from __future__ import annotations

from typing import Optional


def _clean(value: object) -> str:
    """Return `value` as a stripped string, or "" if it isn't usable."""
    if not isinstance(value, str):
        return ""
    return value.strip()


def _from_given_family(source: dict) -> Optional[dict]:
    """Rule (a): both given_name and family_name present and non-empty."""
    given = _clean(source.get("given_name"))
    family = _clean(source.get("family_name"))
    if given and family:
        return {
            "full_name": f"{given} {family}",
            "first_name": given,
            "last_name": family,
        }
    return None


def _from_full_name(source: dict) -> Optional[dict]:
    """Rule (b): `name` present and non-empty; split on first whitespace."""
    name = _clean(source.get("name"))
    if not name:
        return None
    head, _, tail = name.partition(" ")
    # `partition` only handles the first space; any further leading whitespace
    # in `tail` is stripped so multi-space inputs collapse cleanly.
    return {
        "full_name": name,
        "first_name": head.strip(),
        "last_name": tail.strip(),
    }


def _extract_from(source: Optional[dict]) -> Optional[dict]:
    if not isinstance(source, dict):
        return None
    return _from_given_family(source) or _from_full_name(source)


def extract_profile_from_raw_info(
    user_info_api: dict | None,
    id_token_payload: dict | None,
    email: str,
) -> dict:
    """Return {"full_name", "first_name", "last_name"}.

    Pure, never raises, always returns sensible fallbacks. Precedence:
      1. user_info_api via given/family pair
      2. user_info_api via single `name`
      3. id_token_payload via given/family pair
      4. id_token_payload via single `name`
      5. local part of `email`
    """
    resolved = _extract_from(user_info_api) or _extract_from(id_token_payload)
    if resolved is not None:
        return resolved

    local_part = (email or "").split("@", 1)[0].strip()
    return {
        "full_name": local_part,
        "first_name": local_part,
        "last_name": "",
    }
