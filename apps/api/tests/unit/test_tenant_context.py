"""``TenantContextMiddleware`` clears the tenant slots and keys the webhook.

The ordering assertion is the point: the rate limiter reads its key off
``request.state`` *before* the route runs, so the middleware that writes the
key has to wrap the limiter. Getting that backwards is silent — the limiter
just falls back to the client IP — which is why it is asserted here rather
than left to a comment in ``app.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from starlette.requests import Request

from hunter_api.middleware.tenant_context import (
    MAX_DELIVERY_ID_LENGTH,
    webhook_rate_limit_key,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

pytestmark = pytest.mark.unit


def _request(path: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": headers or [],
        "state": {},
    }
    return Request(scope)


def test_tenant_context_wraps_the_rate_limiter(app: FastAPI) -> None:
    # user_middleware is outermost-first, so a smaller index means "wraps"
    stack: list[str] = [
        cast("type[object]", middleware.cls).__name__ for middleware in app.user_middleware
    ]

    assert stack.index("TenantContextMiddleware") < stack.index("RateLimitMiddleware"), (
        "TenantContextMiddleware must be outside RateLimitMiddleware, or the "
        f"limiter reads request.state before anything writes it: {stack}"
    )


def test_a_webhook_delivery_is_keyed_by_its_svix_id() -> None:
    request = _request("/api/webhooks/clerk", [(b"svix-id", b"msg_FAKE_1")])

    assert webhook_rate_limit_key(request) == "svix:msg_FAKE_1"


def test_the_key_is_namespaced_away_from_real_principal_ids() -> None:
    request = _request("/api/webhooks/clerk", [(b"svix-id", b"msg_FAKE_1")])

    key = webhook_rate_limit_key(request)

    # the limiter keys on request.state.principal_id, which otherwise holds a
    # users.id; the prefix keeps a delivery id from ever colliding with one
    assert key is not None
    assert key.startswith("svix:")


def test_an_oversized_svix_id_is_ignored() -> None:
    # the header is attacker-controlled and becomes part of a Redis key
    huge = b"m" * (MAX_DELIVERY_ID_LENGTH + 1)
    request = _request("/api/webhooks/clerk", [(b"svix-id", huge)])

    assert webhook_rate_limit_key(request) is None


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/api/v1/me", [(b"svix-id", b"msg_FAKE_1")]),
        ("/api/webhooks/clerk", []),
        ("/api/webhooks/clerk", [(b"svix-id", b"")]),
    ],
)
def test_everything_else_keys_on_the_client(path: str, headers: list[tuple[bytes, bytes]]) -> None:
    # a svix-id header on an ordinary route must not let a caller pick their
    # own rate-limit bucket
    assert webhook_rate_limit_key(_request(path, headers)) is None
