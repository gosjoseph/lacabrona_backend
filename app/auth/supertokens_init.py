"""SuperTokens SDK initialisation for the La Cabrona backend.

Mirrors the urbanoweb_backend pattern: ThirdParty (Google) + Session, with a
sign_in_up_post override that maps the email returned by Google to either a
customer or employee record in MongoDB and stamps the SuperTokens user id on
the matched document. If the email is in neither collection, the override
rejects the signin.

Init is a no-op when ENVIRONMENT=test so tests don't need a real core.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings
from app.auth.profile import extract_profile_from_raw_info
from app.auth.user_resolver import UnknownUserError, resolve_user_type

logger = logging.getLogger(__name__)


def init_supertokens() -> None:
    """Initialise the SuperTokens SDK. Idempotent: no-op when ENVIRONMENT=test."""
    if os.getenv("ENVIRONMENT") == "test":
        return

    from supertokens_python import InputAppInfo, SupertokensConfig, init
    from supertokens_python.recipe import session, thirdparty
    from supertokens_python.recipe.thirdparty.interfaces import APIInterface
    from supertokens_python.recipe.thirdparty.provider import (
        ProviderClientConfig,
        ProviderConfig,
        ProviderInput,
    )

    def _override_thirdparty_apis(original_implementation: APIInterface) -> APIInterface:
        original_sign_in_up_post = original_implementation.sign_in_up_post

        async def sign_in_up_post(
            provider,
            redirect_uri_info,
            oauth_tokens,
            session,
            should_try_linking_with_session_user,
            tenant_id,
            api_options,
            user_context,
        ):
            response = await original_sign_in_up_post(
                provider=provider,
                redirect_uri_info=redirect_uri_info,
                oauth_tokens=oauth_tokens,
                session=session,
                should_try_linking_with_session_user=should_try_linking_with_session_user,
                tenant_id=tenant_id,
                api_options=api_options,
                user_context=user_context,
            )

            if getattr(response, "status", None) == "OK":
                await _attach_internal_claims(response)

            return response

        original_implementation.sign_in_up_post = sign_in_up_post
        return original_implementation

    google_provider = ProviderInput(
        config=ProviderConfig(
            third_party_id="google",
            clients=[
                ProviderClientConfig(
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                ),
            ],
        ),
    )

    init(
        app_info=InputAppInfo(
            app_name=settings.supertokens_app_name,
            api_domain=settings.api_domain,
            website_domain=settings.app_url,
            api_base_path="/auth",
            website_base_path="/auth",
        ),
        supertokens_config=SupertokensConfig(
            connection_uri=settings.supertokens_core_url,
            api_key=settings.supertokens_api_key or None,
        ),
        framework="fastapi",
        recipe_list=[
            thirdparty.init(
                sign_in_and_up_feature=thirdparty.SignInAndUpFeature(
                    providers=[google_provider],
                ),
                override=thirdparty.InputOverrideConfig(apis=_override_thirdparty_apis),
            ),
            session.init(
                cookie_secure=settings.environment == "production",
                cookie_same_site="lax",
            ),
        ],
        mode="asgi",
    )

    logger.info("SuperTokens initialised")


async def _attach_internal_claims(response: Any) -> None:
    """Link the signed-in email to a customer/employee, merge session claims.

    For an unknown email a new customer is created using the real name
    returned by Google (extracted from `raw_user_info_from_provider`).
    """
    from app.db import get_db

    email = response.user.emails[0] if response.user.emails else None
    supertokens_user_id: str = response.user.id

    profile = _profile_from_response(response, email or "")

    db = get_db()
    try:
        result = resolve_user_type(email or "", supertokens_user_id, db, profile)
    except UnknownUserError as exc:
        logger.warning("Rejecting Google signin: %s", exc)
        raise

    payload = {
        "user_type": result["user_type"],
        "internal_id": result["internal_id"],
    }
    if "role" in result:
        payload["role"] = result["role"]

    await response.session.merge_into_access_token_payload(payload)


def _profile_from_response(response: Any, email: str) -> dict:
    """Pull Google's raw user-info dicts off the response and extract a profile.

    Defensive: the response, the `raw_user_info_from_provider` object, or its
    attributes may be absent depending on tenant/provider configuration.
    """
    raw = getattr(response, "raw_user_info_from_provider", None)
    user_info_api = getattr(raw, "from_user_info_api", None) if raw is not None else None
    id_token_payload = getattr(raw, "from_id_token_payload", None) if raw is not None else None
    return extract_profile_from_raw_info(user_info_api, id_token_payload, email)
