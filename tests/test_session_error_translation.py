"""Regression tests for the SuperTokens session-error translation bug.

History: a blanket ``@app.exception_handler(SuperTokensError)`` returning HTTP
500 shadowed the SuperTokens middleware. Because session errors
(UnauthorisedError, TryRefreshTokenError, InvalidClaimsError,
ClaimValidationError) subclass SuperTokensError, an anonymous request to a
gated route returned 500 instead of the correct 401/403.

The default test suite runs under ENVIRONMENT=test, where both the middleware
and that handler are skipped, so it could never catch the regression. These
tests build the PROD-configured app in-process (without a live SuperTokens
core, by stubbing init) so the prod branch in ``app.main`` is actually
exercised.
"""

import importlib
import os

import pytest

from supertokens_python.exceptions import SuperTokensError
from supertokens_python.framework.fastapi import get_middleware
from supertokens_python.recipe.session.exceptions import (
    ClaimValidationError,
    InvalidClaimsError,
    TryRefreshTokenError,
    UnauthorisedError,
)

# The session-error classes whose translation we must NOT shadow with a handler.
SESSION_ERROR_CLASSES = (
    SuperTokensError,
    UnauthorisedError,
    TryRefreshTokenError,
    InvalidClaimsError,
    ClaimValidationError,
)


@pytest.fixture
def prod_app():
    """Yield the prod-configured ``app.main`` app without a live core.

    We flip ENVIRONMENT off "test" and stub ``init_supertokens`` at its source
    (``app.modules.auth.supertokens``) to a no-op so the real SDK is never
    initialised and no core connection is attempted. ``main.py`` binds the
    symbol via ``from app.modules.auth.supertokens import init_supertokens``, so
    reloading ``app.main`` re-reads the patched value and then runs the non-test
    branch that mounts the middleware. Teardown restores ENVIRONMENT and the
    stubbed symbol, then reloads back to a clean test-mode app so the rest of
    the suite is unaffected.
    """
    import app.main as main
    import app.modules.auth.supertokens as st_module

    original_env = os.environ.get("ENVIRONMENT")
    original_init = st_module.init_supertokens

    os.environ["ENVIRONMENT"] = "prod"
    # Patch at the source so the reload's `from ... import init_supertokens`
    # binds the no-op rather than the real (core-connecting) implementation.
    st_module.init_supertokens = lambda: None
    try:
        prod_main = importlib.reload(main)
        yield prod_main.app
    finally:
        # Restore environment and the source symbol, then reload back to a
        # clean test-mode app for the rest of the suite.
        if original_env is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = original_env
        st_module.init_supertokens = original_init
        importlib.reload(main)


def test_no_session_error_handler_registered(prod_app):
    """T-S1: the prod app registers no handler keyed on a session-error class."""
    handlers = prod_app.exception_handlers
    for exc_cls in SESSION_ERROR_CLASSES:
        assert exc_cls not in handlers, (
            f"{exc_cls.__name__} must NOT have an app-level exception handler — "
            "it would shadow SuperTokens' 401/403 translation."
        )


def test_supertokens_middleware_is_present(prod_app):
    """T-S2: the SuperTokens translator middleware is still mounted."""
    middleware_cls = get_middleware()
    target_name = middleware_cls.__name__
    present = any(
        mw.cls is middleware_cls or getattr(mw.cls, "__name__", None) == target_name
        for mw in prod_app.user_middleware
    )
    assert present, (
        "SuperTokens get_middleware() must remain in app.user_middleware — we "
        "removed only the shadowing handler, not the translator."
    )


def test_no_session_error_maps_to_5xx(prod_app):
    """T-S3: no app-level handler maps a SuperTokens session error to >= 500.

    Documents the regression so it fails loudly if reintroduced. A handler
    registered for a session-error class (or its SuperTokensError base) would
    intercept the middleware's 401/403 translation; we assert none exists.
    """
    handlers = prod_app.exception_handlers
    offending = [
        key.__name__
        for key in handlers
        if isinstance(key, type) and issubclass(key, SuperTokensError)
    ]
    assert not offending, (
        "App-level exception handler(s) found for SuperTokens session error "
        f"class(es) {offending}; these can map a session error to a 5xx and "
        "shadow the 401/403 translation. Do not register them."
    )
