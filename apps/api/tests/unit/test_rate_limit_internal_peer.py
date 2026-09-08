"""T3.28a — the web service's SSR fetches all share one TCP peer.

``test_rate_limit.py`` covers the ordinary per-address bucket; this file
covers the widened bucket for a peer address the deployment lists as
internal (``ApiSettings.internal_peer_ips`` /
``rate_limit_per_minute_internal``) — the fix for the whole site's
server-rendered traffic sharing one 120/min budget (see the module
docstring of ``hunter_api.middleware.rate_limit`` for the full trust-chain
account). Same tiny in-memory Redis fake as ``test_rate_limit.py``, for the
same reason: this suite never needs Docker.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

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
from hunter_api.main import (
    _log_internal_peer_ips,  # pyright: ignore[reportPrivateUsage]
)
from hunter_api.metrics import rate_limit_internal_peer_total
from hunter_api.middleware.rate_limit import (
    _ip_rate_limit,  # pyright: ignore[reportPrivateUsage]
)
from hunter_api.settings import ApiSettings

from .jwt_keys import FAKE_ISSUER, generate_keypair, jwks_for, sign

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from hunter_api.auth.clerk import TokenClaims

pytestmark = pytest.mark.unit

PRINCIPAL = uuid.uuid4()
INTERNAL_IP = "10.0.0.5"
OUTSIDE_IP = "203.0.113.9"


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


async def _get(
    app: FastAPI,
    host: str,
    path: str = "/api/v1/system/info",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """One request from ``host`` — a fresh transport per call, because
    ``ASGITransport`` fixes ``scope["client"]`` for its whole lifetime."""
    transport = httpx.ASGITransport(app=app, client=(host, 44444))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, headers=headers or {})


def test_ip_rate_limit_widens_only_for_a_listed_peer(api_settings: ApiSettings) -> None:
    settings = api_settings.model_copy(
        update={"rate_limit_per_minute_internal": 6000, "internal_peer_ips": INTERNAL_IP}
    )
    listed = Request(
        {"type": "http", "method": "GET", "path": "/x", "headers": [], "client": (INTERNAL_IP, 1)}
    )
    unlisted = Request(
        {"type": "http", "method": "GET", "path": "/x", "headers": [], "client": (OUTSIDE_IP, 1)}
    )

    assert _ip_rate_limit(listed, settings) == 6000
    assert _ip_rate_limit(unlisted, settings) == settings.rate_limit_per_minute


def test_internal_peer_ips_is_empty_by_default(api_settings: ApiSettings) -> None:
    """A bare ``ApiSettings()`` (every existing test, and any deployment that
    never sets ``INTERNAL_PEER_IPS``) keeps the narrow limit for every
    address — this is opt-in, not a default carve-out."""
    listed = Request(
        {"type": "http", "method": "GET", "path": "/x", "headers": [], "client": (INTERNAL_IP, 1)}
    )
    assert _ip_rate_limit(listed, api_settings) == api_settings.rate_limit_per_minute


async def test_internal_peer_gets_the_wider_address_limit(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    """The bug measured in the design audit: every SSR fetch from ``web``
    lands on one peer, so a plain per-address limit is a limit on the whole
    site's server-rendered traffic. Listing that peer as internal (with a
    higher limit) is what stops five screens' worth of SSR fetches from
    exhausting a 120/min bucket meant for one abusive caller.
    """
    settings = api_settings.model_copy(
        update={
            "rate_limit_per_minute": 1,
            "rate_limit_per_minute_internal": 3,
            "internal_peer_ips": INTERNAL_IP,
        }
    )
    app = create_app(settings)

    async with client_factory(app):
        app.state.redis = _FakeRedis()
        for _ in range(3):
            assert (await _get(app, INTERNAL_IP)).status_code == 200
        assert (await _get(app, INTERNAL_IP)).status_code == 429


async def test_an_unlisted_peer_keeps_the_narrow_limit_alongside_the_internal_one(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    """Widening the bucket for the ``web`` peer must not widen it for anyone
    else — a real abusive address behind a plain address bucket is still
    limited at ``rate_limit_per_minute``."""
    settings = api_settings.model_copy(
        update={
            "rate_limit_per_minute": 1,
            "rate_limit_per_minute_internal": 6000,
            "internal_peer_ips": INTERNAL_IP,
        }
    )
    app = create_app(settings)

    async with client_factory(app):
        app.state.redis = _FakeRedis()
        assert (await _get(app, OUTSIDE_IP)).status_code == 200
        assert (await _get(app, OUTSIDE_IP)).status_code == 429


async def test_a_forged_forwarded_header_cannot_claim_the_internal_bucket(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    """``internal_peer_ips`` is checked against ``request.client.host``, the
    real TCP peer — never a header. A caller claiming to be the internal
    peer over ``X-Forwarded-For`` (uvicorn has not rewritten anything here,
    since this peer is not in ``forwarded_allow_ips``) still gets the narrow
    limit.
    """
    settings = api_settings.model_copy(
        update={
            "rate_limit_per_minute": 1,
            "rate_limit_per_minute_internal": 6000,
            "internal_peer_ips": INTERNAL_IP,
        }
    )
    app = create_app(settings)

    async with client_factory(app):
        app.state.redis = _FakeRedis()
        forged = {"X-Forwarded-For": INTERNAL_IP}
        assert (await _get(app, OUTSIDE_IP, headers=forged)).status_code == 200
        assert (await _get(app, OUTSIDE_IP, headers=forged)).status_code == 429


# ---- precedence: the principal limit is untouched by internal-peer status ----


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
    """A one-route app whose only guard is ``get_principal`` — no IP
    middleware, so a 429 here can only be the principal limit."""
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


async def test_internal_peer_status_does_not_widen_the_principal_limit(
    api_settings: ApiSettings, signing_key: rsa.RSAPrivateKey
) -> None:
    """Listing the ``web`` peer as internal only widens the address bucket in
    the middleware; ``enforce_principal_limit`` never reads
    ``internal_peer_ips``, so an authenticated caller behind that peer is
    still bound by its own account's limit."""
    settings = api_settings.model_copy(
        update={
            "rate_limit_per_minute_principal": 1,
            "internal_peer_ips": INTERNAL_IP,
            "rate_limit_per_minute_internal": 6000,
        }
    )
    principal = Principal(user_id=PRINCIPAL, external_auth_id="user_FAKE_clerk_id", memberships=())
    app = _probe_app(settings, principal, signing_key)
    app.state.redis = _FakeRedis()
    headers = {"Authorization": f"Bearer {sign(signing_key)}"}

    first = await _get(app, INTERNAL_IP, path="/probe", headers=headers)
    second = await _get(app, INTERNAL_IP, path="/probe", headers=headers)

    assert (first.status_code, second.status_code) == (200, 429)


# ---- T3.28d: boot-time validation of INTERNAL_PEER_IPS ----


@pytest.mark.parametrize(
    "bad_entry",
    [
        "10.0.0.0/24",  # CIDR, not a single address
        "web",  # hostname -- request.client.host is never a hostname
        "172.29.0.10.1",  # typo: one octet too many
        "not-an-ip",
    ],
)
def test_internal_peer_ips_rejects_anything_that_is_not_a_single_ip(
    api_settings: ApiSettings, bad_entry: str
) -> None:
    """A CIDR, a hostname or a typo would never match ``request.client.host``
    in ``_ip_rate_limit``, silently keeping that peer on the narrow bucket
    forever -- boot must fail loudly instead (security-reviewer finding 2).
    Goes through the real constructor (not ``model_copy``, which skips
    validators) so this is exactly what a bad ``INTERNAL_PEER_IPS`` does at
    process boot.
    """
    data = api_settings.model_dump()
    data["internal_peer_ips"] = bad_entry
    with pytest.raises(ValueError, match="INTERNAL_PEER_IPS"):
        ApiSettings(**data)


@pytest.mark.parametrize("good_entries", ["10.0.0.5", "10.0.0.5,172.29.0.10", "::1"])
def test_internal_peer_ips_accepts_valid_addresses(
    api_settings: ApiSettings, good_entries: str
) -> None:
    """IPv4, IPv6, and a comma-separated list of them all boot cleanly."""
    settings = api_settings.model_copy(update={"internal_peer_ips": good_entries})
    assert settings.internal_peer_ip_set == frozenset(
        entry.strip() for entry in good_entries.split(",")
    )


# ---- T3.28d: one INFO line at boot with the resolved set ----


def test_internal_peer_ips_loaded_logs_the_resolved_set(
    api_settings: ApiSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """``_log_internal_peer_ips`` (called once at process boot, right after
    ``create_app`` in ``main.py``) makes ``INTERNAL_PEER_IPS`` visible
    without grepping env vars or a compose file -- see
    ``test_markets_quality.py`` for why this suite uses stdlib ``caplog``
    rather than ``structlog.testing.capture_logs()``.
    """
    settings = api_settings.model_copy(update={"internal_peer_ips": f"{INTERNAL_IP},::1"})
    with caplog.at_level(logging.INFO, logger="hunter_api.main"):
        _log_internal_peer_ips(settings)

    assert "internal_peer_ips_loaded" in caplog.text
    assert INTERNAL_IP in caplog.text
    assert "::1" in caplog.text


def test_internal_peer_ips_loaded_logs_an_empty_set_by_default(
    api_settings: ApiSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """The common case (no ``INTERNAL_PEER_IPS`` set) logs an empty set, not
    silence -- "never matches" and "not configured" must be distinguishable
    from the log alone."""
    with caplog.at_level(logging.INFO, logger="hunter_api.main"):
        _log_internal_peer_ips(api_settings)

    assert "internal_peer_ips_loaded" in caplog.text


# ---- T3.28d: hunter_rate_limit_internal_peer_total ----


def test_internal_peer_counter_increments_only_for_a_listed_peer(
    api_settings: ApiSettings,
) -> None:
    """security-reviewer finding 3: "never matches" must be visible on the
    dashboard, not just inferred from a wall of 429s -- so the counter must
    move for a listed peer and stay put for anyone else."""
    settings = api_settings.model_copy(
        update={"rate_limit_per_minute_internal": 6000, "internal_peer_ips": INTERNAL_IP}
    )
    listed = Request(
        {"type": "http", "method": "GET", "path": "/x", "headers": [], "client": (INTERNAL_IP, 1)}
    )
    unlisted = Request(
        {"type": "http", "method": "GET", "path": "/x", "headers": [], "client": (OUTSIDE_IP, 1)}
    )
    metric = rate_limit_internal_peer_total
    before = float(cast(Any, metric)._value.get())  # pyright: ignore[reportPrivateUsage]

    _ip_rate_limit(unlisted, settings)
    assert float(cast(Any, metric)._value.get()) == before  # pyright: ignore[reportPrivateUsage]

    _ip_rate_limit(listed, settings)
    after = float(cast(Any, metric)._value.get())  # pyright: ignore[reportPrivateUsage]
    assert after == before + 1
