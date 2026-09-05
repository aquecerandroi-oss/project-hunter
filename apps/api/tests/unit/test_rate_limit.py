"""Redis sliding-window rate limiting: 429 past the limit, exempt paths,
fail-open when Redis errors.

Uses tiny in-memory fakes for the handful of Redis commands the middleware
calls (no ``fakeredis`` dependency declared for this package) rather than a
real Redis — this suite never needs Docker.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from starlette.requests import Request

from hunter_api.app import create_app
from hunter_api.auth.clerk import StaticKeyAuthProvider
from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.errors import register_error_handlers
from hunter_api.middleware import rate_limit as rate_limit_module
from hunter_api.middleware.rate_limit import (
    EXEMPT_PATHS,
    _client_keys,  # pyright: ignore[reportPrivateUsage]
)
from hunter_api.settings import ApiSettings

from .jwt_keys import FAKE_ISSUER, generate_keypair, jwks_for, sign

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from hunter_api.auth.clerk import TokenClaims

pytestmark = pytest.mark.unit

PRINCIPAL = uuid.uuid4()


class _FakeRedis:
    """In-memory sorted sets — just enough of the Redis API for the sliding window."""

    def __init__(self) -> None:
        self._sets: dict[str, dict[str, float]] = defaultdict(dict)

    async def zremrangebyscore(self, name: str, min_: float, max_: float) -> None:
        self._sets[name] = {
            member: score
            for member, score in self._sets[name].items()
            if not (min_ <= score <= max_)
        }

    async def zadd(self, name: str, mapping: dict[str, float]) -> None:
        self._sets[name].update(mapping)

    async def zcard(self, name: str) -> int:
        return len(self._sets[name])

    async def expire(self, name: str, seconds: int) -> bool:
        return True

    def keys(self) -> list[str]:
        return list(self._sets)


class _BrokenRedis:
    """Every command raises — simulates Redis being unreachable."""

    async def zremrangebyscore(self, *args: object, **kwargs: object) -> None:
        raise ConnectionError("redis unreachable")

    async def zadd(self, *args: object, **kwargs: object) -> None:
        raise ConnectionError("redis unreachable")

    async def zcard(self, *args: object, **kwargs: object) -> int:
        raise ConnectionError("redis unreachable")

    async def expire(self, *args: object, **kwargs: object) -> bool:
        raise ConnectionError("redis unreachable")


def test_ready_and_metrics_are_declared_exempt() -> None:
    assert {"/health", "/ready", "/metrics"} == set(EXEMPT_PATHS)


async def test_returns_429_after_the_configured_limit(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 3})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _FakeRedis()
        for _ in range(3):
            assert (await test_client.get("/api/v1/system/info")).status_code == 200
        response = await test_client.get("/api/v1/system/info")

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "Retry-After" in response.headers


async def test_exempts_health_and_metrics_from_the_limit(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 1})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _FakeRedis()
        assert (await test_client.get("/health")).status_code == 200
        assert (await test_client.get("/health")).status_code == 200
        # Starlette's Mount 307-redirects "/metrics" -> "/metrics/"; the
        # exemption is checked against the pre-redirect path either way.
        assert (await test_client.get("/metrics/")).status_code == 200


async def test_fails_open_when_redis_is_unavailable(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 1})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _BrokenRedis()
        for _ in range(5):
            assert (await test_client.get("/api/v1/system/info")).status_code == 200


async def test_spoofed_x_forwarded_for_does_not_change_the_rate_limit_key(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    """The rate-limit key comes from ``request.client.host`` only. A test
    client's ``request.client`` is fixed for the life of the transport, so if
    a spoofed ``X-Forwarded-For`` changed the key, these two requests would
    land in different buckets and neither would be limited; keying on the
    real peer means they share one bucket and the second one is limited.
    """
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 1})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _FakeRedis()
        first = await test_client.get("/api/v1/system/info", headers={"X-Forwarded-For": "1.2.3.4"})
        second = await test_client.get(
            "/api/v1/system/info", headers={"X-Forwarded-For": "9.9.9.9"}
        )

    assert first.status_code == 200
    assert second.status_code == 429


async def test_fail_open_warning_is_logged_at_most_once_per_interval(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(api_settings)
    warnings: list[str] = []

    def _record_warning(event: str, **_kwargs: object) -> None:
        warnings.append(event)

    monkeypatch.setattr(rate_limit_module.logger, "warning", _record_warning)

    async with client_factory(app) as test_client:
        app.state.redis = _BrokenRedis()
        for _ in range(5):
            assert (await test_client.get("/api/v1/system/info")).status_code == 200

    assert warnings.count("rate_limit_redis_unavailable") == 1


async def test_requests_in_the_same_clock_tick_are_counted_separately(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sliding window is a sorted set, and a set collapses equal members.

    With the timestamp alone as the member, two requests landing on the same
    ``time.time()`` value are one entry — so on a fast machine (or a coarse
    clock, which is what Windows has) a burst counts as a single request and
    the limit stops meaning anything.
    """
    frozen = 1_700_000_000.0
    monkeypatch.setattr(rate_limit_module.time, "time", lambda: frozen)
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 2})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _FakeRedis()
        first = await test_client.get("/api/v1/system/info")
        second = await test_client.get("/api/v1/system/info")
        third = await test_client.get("/api/v1/system/info")

    assert (first.status_code, second.status_code) == (200, 200)
    assert third.status_code == 429


async def test_a_webhook_flood_from_one_source_is_limited_despite_rotating_delivery_ids(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    """``svix-id`` is chosen by the caller, so it cannot be the only bucket.

    Keying on it alone bounds a retry storm for one delivery and nothing else:
    anyone who can reach the public webhook URL mints a fresh id per request
    and every one of them lands in an empty bucket. The client address is the
    part the caller does not choose, so both are counted.
    """
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 2})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _FakeRedis()
        statuses = [
            (
                await test_client.post(
                    "/api/webhooks/clerk",
                    content=b"{}",
                    headers={"svix-id": f"msg_FAKE_{index}"},
                )
            ).status_code
            for index in range(3)
        ]

    assert statuses[-1] == 429
    assert 429 not in statuses[:-1]


async def test_two_deliveries_of_different_events_share_the_source_bucket_only(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    """A retry storm for one delivery must not spend another delivery's budget
    beyond the shared source limit — the per-delivery bucket is what bounds
    the storm, and it is still keyed on ``svix-id`` alone.
    """
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 3})
    app = create_app(limited)
    redis = _FakeRedis()

    async with client_factory(app) as test_client:
        app.state.redis = redis
        for _ in range(2):
            await test_client.post(
                "/api/webhooks/clerk", content=b"{}", headers={"svix-id": "msg_FAKE_repeat"}
            )

    keys = list(redis.keys())
    assert any(key.endswith("svix:msg_FAKE_repeat") for key in keys), keys
    assert any(":ip:" in key for key in keys), keys


# ---- the second limit: per authenticated principal, applied after auth ----
#
# The middleware above cannot do this one. It runs before routing, so there is
# no principal yet — everything it sees is an address. A single account behind
# a phone network, a VPN or a botnet is many addresses and one identity, and
# only a limit keyed on the identity bounds it.


class _FixedResolver:
    """Resolves any verified claim to one principal — the DB path is the
    integration suite's job; the subject here is the bucket key."""

    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def resolve(self, claims: TokenClaims) -> Principal:
        return self.principal


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return generate_keypair()


def _probe_app(settings: ApiSettings, principal: Principal, key: rsa.RSAPrivateKey) -> FastAPI:
    """A one-route app whose only guard is ``get_principal``.

    Deliberately not ``create_app``: with the IP middleware also in the stack a
    429 would not say *which* limit produced it.
    """
    app = FastAPI()
    register_error_handlers(app)
    app.state.settings = settings
    app.state.auth_provider = StaticKeyAuthProvider(jwks_for(key), issuer=FAKE_ISSUER)
    app.state.principal_resolver = _FixedResolver(principal)

    @app.get("/probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        caller: CurrentPrincipal,
    ) -> dict[str, str]:
        return {"user_id": str(caller.user_id)}

    return app


async def _get_from(app: FastAPI, host: str, headers: dict[str, str]) -> httpx.Response:
    """One request from ``host`` — a fresh transport per call, because
    ``ASGITransport`` fixes ``scope["client"]`` for its whole lifetime."""
    transport = httpx.ASGITransport(app=app, client=(host, 44444))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/probe", headers=headers)


async def test_one_principal_from_many_addresses_shares_one_bucket(
    api_settings: ApiSettings, signing_key: rsa.RSAPrivateKey
) -> None:
    """Three addresses, one account, one budget.

    Without this the IP limit is the only limit, and it is exactly the one an
    attacker with a residential proxy pool pays nothing to defeat.
    """
    settings = api_settings.model_copy(update={"rate_limit_per_minute_principal": 2})
    principal = Principal(user_id=PRINCIPAL, external_auth_id="user_FAKE_clerk_id", memberships=())
    app = _probe_app(settings, principal, signing_key)
    redis = _FakeRedis()
    app.state.redis = redis
    headers = {"Authorization": f"Bearer {sign(signing_key)}"}

    responses = [await _get_from(app, host, headers) for host in ("1.1.1.1", "2.2.2.2", "3.3.3.3")]

    assert [response.status_code for response in responses] == [200, 200, 429]
    last = responses[-1]
    assert last.headers["content-type"].startswith("application/problem+json")
    assert last.headers["Retry-After"] == "60"
    assert last.json()["title"] == "Too Many Requests"
    assert redis.keys() == [f"hunter:rl:principal:{PRINCIPAL}"]


async def test_the_principal_limit_fails_open_when_redis_is_unreachable(
    api_settings: ApiSettings, signing_key: rsa.RSAPrivateKey
) -> None:
    """Same call as the middleware makes: availability over enforcement on a
    read path (ARCHITECTURE.md "degradacao segura")."""
    settings = api_settings.model_copy(update={"rate_limit_per_minute_principal": 1})
    principal = Principal(user_id=PRINCIPAL, external_auth_id="user_FAKE_clerk_id", memberships=())
    app = _probe_app(settings, principal, signing_key)
    app.state.redis = _BrokenRedis()
    headers = {"Authorization": f"Bearer {sign(signing_key)}"}

    for _ in range(4):
        assert (await _get_from(app, "1.1.1.1", headers)).status_code == 200


def test_the_middleware_never_keys_on_a_principal() -> None:
    """The IP limit and the principal limit are two different limits.

    ``_client_keys`` used to prefer ``request.state.principal_id`` — a value
    nothing had written yet, because the middleware runs before routing. The
    branch was dead, and it made the IP limit read as if it were narrower than
    it is. Even with the attribute present, the middleware's bucket is the
    address.
    """
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/me",
        "headers": [],
        "client": ("9.9.9.9", 1234),
        "state": {"principal_id": str(PRINCIPAL)},
    }

    assert _client_keys(Request(scope)) == ["hunter:rl:ip:9.9.9.9"]
