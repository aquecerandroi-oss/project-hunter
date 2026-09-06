"""Authentication edge cases that only show up against the real app stack.

The straightforward cases (bad signature, wrong issuer, ``azp`` mismatch, JIT
provisioning conflicts) are covered in ``test_signup.py`` and, at the unit
level, in ``tests/unit/test_auth_clerk.py``. What is missing there is proof
that the *whole* application — not a bare probe app — behaves the same way
when the JWKS source misbehaves: a flood of invented key ids must not turn
into a flood of outbound fetches, and a legitimate, already-cached caller must
keep working while that flood is in progress.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy.exc import OperationalError

from hunter_api.auth.clerk import JwtAuthProvider
from hunter_api.auth.clerk_api import StaticProfileSource, UserProfile
from hunter_api.auth.principal import PrincipalResolver

from ..unit.jwt_keys import FAKE_ISSUER, jwks_for, sign
from .conftest import WEB_ORIGIN, auth_header

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI

    from .conftest import Actor

pytestmark = pytest.mark.integration


class _CountingJwksSource:
    """A fixed JWKS document that counts how many times it was fetched."""

    def __init__(self, document: dict[str, Any]) -> None:
        self._document = document
        self.fetches = 0

    async def fetch(self) -> dict[str, Any]:
        self.fetches += 1
        return self._document


class _BrokenJwksSource:
    """A JWKS source standing in for Clerk being unreachable."""

    async def fetch(self) -> dict[str, Any]:
        raise ConnectionError("jwks unreachable")


async def test_an_expired_token_is_401_with_the_generic_reason(
    client: httpx.AsyncClient, signing_key: rsa.RSAPrivateKey
) -> None:
    """An expired token fails the same ``exp`` check unit-tested in
    ``test_auth_clerk.py``; here it is asserted end to end, through the real
    dependency chain, and that the reason given is the same one every other
    rejected token gets — nothing about the response distinguishes "expired"
    from "forged" or "wrong issuer".
    """
    expired = sign(signing_key, expires_in_s=-120)

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "https://hunter.dev/problems/invalid-token"
    assert body["detail"] == "The access token is missing or invalid."


async def test_a_flood_of_unknown_kids_does_not_block_a_cached_kid_at_the_api(
    app: FastAPI,
    client: httpx.AsyncClient,
    signing_key: rsa.RSAPrivateKey,
    make_actor: Callable[[str], Actor],
) -> None:
    """``tests/unit/test_auth_clerk.py`` proves the cache collapses a 50-kid
    flood to one refetch. What it cannot prove is that the fast path — a
    reader whose ``kid`` is already cached never touches the lock — actually
    holds through the full FastAPI dependency chain and a real request/response
    cycle, with the flood and the legitimate caller interleaved rather than
    run one after the other.
    """
    source = _CountingJwksSource(jwks_for(signing_key))
    app.state.auth_provider = JwtAuthProvider(source, issuer=FAKE_ISSUER, allowed_azp=[WEB_ORIGIN])
    survivor = make_actor("cached-kid-survivor")
    # ``make_actor``'s token carries ``sign()``'s default 300s lifetime, fine
    # for a single request but not for the 100 real request/response round
    # trips (with a real Postgres lookup behind each) this loop makes — under
    # full-suite load, sharing the database and Redis containers with every
    # other integration test, that can take long enough for the default to
    # expire mid-loop, failing this test on an unrelated 401 (expired token,
    # not an evicted cache entry). A long-lived token keeps the assertion
    # about caching instead of about how fast the whole suite ran.
    survivor.headers = {
        "Authorization": f"Bearer {sign(signing_key, subject=survivor.subject, expires_in_s=3600)}"
    }

    warm = await client.get("/api/v1/me", headers=survivor.headers)
    assert warm.status_code == 200
    fetches_after_warm = source.fetches

    for index in range(50):
        bogus = sign(signing_key, kid=f"unknown-kid-{index}")
        rejected = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {bogus}"})
        assert rejected.status_code == 401

        still_cached = await client.get("/api/v1/me", headers=survivor.headers)
        assert still_cached.status_code == 200, (
            f"a cached-kid request must not be blocked by unknown kid #{index}"
        )

    assert source.fetches == fetches_after_warm + 1, (
        "50 distinct invented kids must cost exactly one extra outbound fetch, "
        "the same bound tests/unit/test_auth_clerk.py proves at the cache level"
    )


async def test_the_jwks_source_being_unreachable_is_503_with_retry_after(
    app: FastAPI,
    client: httpx.AsyncClient,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """A JWKS outage must never read as "your session is invalid" (401), which
    would send every signed-in user back through the very provider that is
    down. It reads as 503 with ``Retry-After`` instead (SECURITY.md §1,
    ``auth/errors.py``).
    """
    app.state.auth_provider = JwtAuthProvider(
        _BrokenJwksSource(), issuer=FAKE_ISSUER, allowed_azp=[WEB_ORIGIN]
    )

    response = await client.get(
        "/api/v1/me", headers=auth_header(signing_key, "user_FAKE_during_outage")
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "Retry-After" in response.headers
    assert response.json()["type"] == "https://hunter.dev/problems/auth-unavailable"


async def test_principal_resolution_postgres_outage_is_503_not_a_generic_500(
    client: httpx.AsyncClient,
    signing_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Postgres outage that hits *before* a router's own dependency chain
    even starts — inside ``CurrentPrincipal`` resolution itself
    (``PrincipalResolver._load``, which every authenticated request runs
    through) — used to escape every route's error handling and fall through
    to ``ProblemDetailsMiddleware``'s generic 500, because nothing upstream of
    ``get_principal`` ever turned an ``OperationalError`` into a problem+json
    response. It must come back as the same ``503`` shape every other
    Postgres-outage path in this API already uses, on any authenticated
    route — ``/api/v1/lab/shadow/versions`` (whose own ``lab_session``
    dependency has an unrelated ``try`` that only runs *after* the principal
    already resolved) stands in for "any".
    """

    async def _boom(self: object, external_auth_id: str) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(PrincipalResolver, "_load", _boom)

    response = await client.get(
        "/api/v1/lab/shadow/versions",
        headers=auth_header(signing_key, f"user_FAKE_pg_outage_{uuid.uuid4().hex[:8]}"),
    )

    assert response.status_code == 503, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "https://hunter.dev/problems/service-unavailable"
    assert "connection refused" not in body["detail"]
    assert "OperationalError" not in body["detail"]


async def test_principal_resolution_os_error_from_role_session_is_also_503(
    client: httpx.AsyncClient,
    signing_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The task calls out ``OperationalError``/``OSError``/
    ``ConnectionRefusedError`` explicitly; the first is exercised above, and
    ``ConnectionRefusedError`` is an ``OSError`` subclass, so raising it here
    covers all three with one guard clause
    (``PrincipalResolver.resolve``'s ``except (OperationalError, OSError)``).
    """

    async def _boom(self: object, external_auth_id: str) -> None:
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(PrincipalResolver, "_load", _boom)

    response = await client.get(
        "/api/v1/lab/shadow/versions",
        headers=auth_header(signing_key, f"user_FAKE_conn_refused_{uuid.uuid4().hex[:8]}"),
    )

    assert response.status_code == 503, response.text
    assert response.json()["type"] == "https://hunter.dev/problems/service-unavailable"


async def test_principal_resolution_authorization_errors_keep_their_own_type(
    client: httpx.AsyncClient,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    """A guard against an overly broad ``except`` in
    ``PrincipalResolver.resolve``: an unverified Clerk account is a real,
    distinct failure (``UnverifiedEmailError``, 503 ``email-not-verified``)
    that must keep its own ``type`` and detail, not be reclassified as the
    generic "Postgres is down" ``service-unavailable`` the new
    ``(OperationalError, OSError)`` guard produces. Neither is a 401/403, but
    the principle is the same one the task states for authorization/validation
    errors: this ``except`` must never widen to swallow a different failure.
    """
    subject = f"user_FAKE_unverified_lab_{uuid.uuid4().hex[:8]}"
    profiles.add(UserProfile(external_auth_id=subject, email=None))

    response = await client.get(
        "/api/v1/lab/shadow/versions", headers=auth_header(signing_key, subject)
    )

    assert response.status_code == 503, response.text
    assert response.json()["type"] == "https://hunter.dev/problems/email-not-verified"


async def test_principal_resolution_postgres_outage_during_jit_provisioning_is_also_503(
    client: httpx.AsyncClient,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra's second-opinion review of this fix (nice-to-have): the same
    guard must also hold for the *insert* path — a brand-new account (no
    local ``users`` row yet) whose provisioning insert hits a dead Postgres,
    not just the read path exercised above.
    """
    subject = f"user_FAKE_pg_outage_during_provisioning_{uuid.uuid4().hex[:8]}"
    profiles.add(UserProfile(external_auth_id=subject, email=f"{subject}@example.test"))

    async def _boom(self: object, user_id: object, subject_arg: object, profile: object) -> bool:
        raise OperationalError("INSERT", {}, Exception("connection refused"))

    monkeypatch.setattr(PrincipalResolver, "_insert_user", _boom)

    response = await client.get(
        "/api/v1/lab/shadow/versions", headers=auth_header(signing_key, subject)
    )

    assert response.status_code == 503, response.text
    assert response.json()["type"] == "https://hunter.dev/problems/service-unavailable"
