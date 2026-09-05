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

from typing import TYPE_CHECKING, Any

import pytest

from hunter_api.auth.clerk import JwtAuthProvider

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
