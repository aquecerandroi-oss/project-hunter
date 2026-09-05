"""Rate limiting against the real application — SECURITY.md §5.

``tests/unit/test_rate_limit.py`` and ``tests/unit/test_throttle.py`` exercise
the sliding window itself against in-memory fakes; this file is the same
properties through the real app stack and a real Redis container, where the
shared ``api_settings`` fixture deliberately sets ``rate_limit_per_minute`` to
100000 so no other integration test trips it. Each test here builds its own
tightened application (``conftest.build_custom_app``) rather than perturbing
that shared one.

The Redis container is session-scoped, so the sliding window persists across
every test in this file (``WINDOW_SECONDS`` is 60, comfortably longer than the
whole file takes to run). ``httpx.ASGITransport`` defaults every client to the
same peer address, so two IP-limited tests sharing that default would share a
bucket and see each other's counts — each test below therefore binds its own
``client_addr`` (a distinct address in the ``TEST-NET-3`` documentation range,
RFC 5737, guaranteed never to collide with a real one) via ``running()``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hunter_api.auth.clerk_api import UserProfile
from hunter_api.auth.principal import PrincipalResolver

from ..unit.jwt_keys import sign
from .conftest import Actor, build_custom_app, running

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import rsa

    from hunter_api.auth.clerk_api import StaticProfileSource

pytestmark = pytest.mark.integration


def _actor(signing_key: rsa.RSAPrivateKey, profiles: StaticProfileSource, name: str) -> Actor:
    subject = f"user_FAKE_{name}"
    email = f"{name}@example.test"
    profiles.add(UserProfile(external_auth_id=subject, email=email, display_name=name.title()))
    return Actor(signing_key, subject, email)


async def test_the_ip_limit_answers_429_with_retry_after(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        rate_limit_per_minute=3,
    )

    async with running(app, client_addr=("203.0.113.1", 44444)) as client:
        for _ in range(3):
            # unauthenticated, but the address limit runs in middleware before
            # routing — it never looks at whether the request would succeed
            assert (await client.get("/api/v1/me")).status_code == 401
        response = await client.get("/api/v1/me")

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "Retry-After" in response.headers


async def test_the_principal_limit_is_shared_across_two_addresses(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    """Three requests, two addresses, one account: the address limit alone
    would let each of the two addresses through, so this is what actually
    bounds one account spread over many addresses (SECURITY.md §5).
    """
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        rate_limit_per_minute_principal=2,
    )
    actor = _actor(signing_key, profiles, "principal-limit-shared")

    async with app.router.lifespan_context(app):
        app.state.principal_resolver = PrincipalResolver(
            app.state.session_factory, app.state.profiles
        )

        async def _get_from(host: str) -> httpx.Response:
            transport = httpx.ASGITransport(app=app, client=(host, 44444))
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                return await c.get("/api/v1/me", headers=actor.headers)

        first = await _get_from("10.0.0.1")
        second = await _get_from("10.0.0.2")
        third = await _get_from("10.0.0.3")

    assert [response.status_code for response in (first, second, third)] == [200, 200, 429]
    assert third.headers["content-type"].startswith("application/problem+json")
    assert third.headers["Retry-After"] == "60"


async def test_health_and_ready_are_exempt_from_the_ip_limit(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        rate_limit_per_minute=1,
    )

    async with running(app, client_addr=("203.0.113.2", 44444)) as client:
        results = [
            (await client.get("/health")).status_code,
            (await client.get("/health")).status_code,
            (await client.get("/ready")).status_code,
            (await client.get("/ready")).status_code,
        ]

    assert 429 not in results, results


async def test_a_webhook_flood_from_one_address_is_limited_despite_rotating_delivery_ids(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    """``svix-id`` is chosen by whoever calls the webhook, so a fresh one per
    request is a fresh empty bucket on its own; the address bucket is what
    still bounds the flood.
    """
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        rate_limit_per_minute=2,
    )

    async with running(app, client_addr=("203.0.113.3", 44444)) as client:
        statuses = [
            (
                await client.post(
                    "/api/webhooks/clerk",
                    content=b"{}",
                    headers={
                        "svix-id": f"msg_FAKE_flood_{index}",
                        "svix-timestamp": "0",
                        "svix-signature": "v1,not-a-real-signature",
                    },
                )
            ).status_code
            for index in range(3)
        ]

    assert statuses[-1] == 429
    assert 429 not in statuses[:-1], statuses


def test_the_ws_handshake_limit_answers_4429(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    """The handshake limit lives in ``realtime.endpoint`` and shares the same
    Redis window implementation the HTTP middleware uses, in its own ``ws``
    bucket (SECURITY.md §5).
    """
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        ws_handshakes_per_minute=2,
    )
    subject = "user_FAKE_ws_handshake_limit"
    profiles.add(UserProfile(external_auth_id=subject, email="ws-handshake@example.test"))
    token = sign(signing_key, subject=subject)

    # a dedicated TEST-NET-3 address (RFC 5737): TestClient's own default
    # peer, ("testclient", 50000), is the same literal string every
    # WebSocket test in this file and in test_websocket.py gets when they
    # don't override it, and the handshake limit's Redis bucket
    # (``hunter:rl:ws:<ip>``) is keyed on nothing else — sharing that
    # default would mean whichever of those tests runs first spends down
    # this test's budget of 2, or this test spends down theirs.
    with TestClient(app, client=("203.0.113.4", 44444)) as ws_client:
        app.state.principal_resolver = PrincipalResolver(
            app.state.session_factory, app.state.profiles
        )
        for _ in range(2):
            with ws_client.websocket_connect("/ws") as websocket:
                websocket.send_text(json.dumps({"type": "auth", "token": token}))
                assert json.loads(websocket.receive_text()) == {"type": "authenticated"}

        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            ws_client.websocket_connect("/ws"),
        ):
            pass  # the handshake is refused before accept(); nothing to do here

    assert exc_info.value.code == 4429
