"""Clerk token verification — SECURITY.md §1.

Every assertion here uses a keypair generated in-process (``jwt_keys``); no
real Clerk key, token or secret exists anywhere in this suite.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from hunter_api.auth.clerk import (
    AuthUnavailableError,
    InvalidTokenError,
    JwtAuthProvider,
    StaticKeyAuthProvider,
)

from .jwt_keys import FAKE_AZP, FAKE_ISSUER, generate_keypair, jwks_for, sign

pytestmark = pytest.mark.unit


class _CountingJwksSource:
    """A JWKS source that counts fetches, so "refresh once" is provable."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.fetches = 0

    async def fetch(self) -> dict[str, Any]:
        self.fetches += 1
        return self.document


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return generate_keypair()


@pytest.fixture
def provider(private_key: rsa.RSAPrivateKey) -> JwtAuthProvider:
    return StaticKeyAuthProvider(jwks_for(private_key), issuer=FAKE_ISSUER, allowed_azp=(FAKE_AZP,))


async def test_a_valid_token_yields_its_subject(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    claims = await provider.verify(sign(private_key, subject="user_FAKE_1", email="a@example.test"))

    assert claims.subject == "user_FAKE_1"
    assert claims.email == "a@example.test"
    assert claims.azp == FAKE_AZP


async def test_an_expired_token_is_rejected(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    long_ago = datetime.now(UTC) - timedelta(hours=2)
    token = sign(private_key, issued_at=long_ago, expires_in_s=60)

    with pytest.raises(InvalidTokenError):
        await provider.verify(token)


async def test_a_not_yet_valid_token_is_rejected(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    future = datetime.now(UTC) + timedelta(hours=1)

    with pytest.raises(InvalidTokenError):
        await provider.verify(sign(private_key, issued_at=future))


async def test_a_token_from_another_issuer_is_rejected(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    with pytest.raises(InvalidTokenError):
        await provider.verify(sign(private_key, issuer="https://evil.test"))


async def test_an_azp_outside_the_allowlist_is_rejected(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    # azp is the origin the token was minted for; a token minted for an
    # attacker's own Clerk-authorized origin must not be replayable at our API
    with pytest.raises(InvalidTokenError):
        await provider.verify(sign(private_key, azp="http://attacker.test"))


async def test_a_token_without_azp_is_accepted(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    claims = await provider.verify(sign(private_key, azp=None))

    assert claims.azp is None


async def test_a_token_signed_by_a_different_key_is_rejected(
    provider: JwtAuthProvider,
) -> None:
    other_key = generate_keypair()

    with pytest.raises(InvalidTokenError):
        await provider.verify(sign(other_key))


@pytest.mark.parametrize(
    "token",
    ["", "not.a.token", "a.b", "Bearer something", "eyJhbGciOiJub25lIn0..", "x" * 40],
)
async def test_a_malformed_token_is_rejected(provider: JwtAuthProvider, token: str) -> None:
    with pytest.raises(InvalidTokenError):
        await provider.verify(token)


async def test_an_unsigned_token_is_rejected(private_key: rsa.RSAPrivateKey) -> None:
    import jwt as pyjwt

    provider = StaticKeyAuthProvider(jwks_for(private_key), issuer=FAKE_ISSUER)
    unsigned = pyjwt.encode({"sub": "user_FAKE_1", "iss": FAKE_ISSUER}, key="", algorithm="none")

    with pytest.raises(InvalidTokenError):
        await provider.verify(unsigned)


async def test_an_unknown_kid_refreshes_the_jwks_exactly_once(
    private_key: rsa.RSAPrivateKey,
) -> None:
    source = _CountingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER)

    await provider.verify(sign(private_key))
    assert source.fetches == 1

    with pytest.raises(InvalidTokenError):
        await provider.verify(sign(private_key, kid="FAKE-rotated-key"))

    # exactly one extra fetch: the unknown kid triggers a single refresh, so a
    # flood of bogus kids cannot turn into a flood of requests to Clerk
    assert source.fetches == 2


async def test_a_rotated_key_is_picked_up_by_the_refresh(
    private_key: rsa.RSAPrivateKey,
) -> None:
    source = _CountingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER)
    await provider.verify(sign(private_key))

    rotated = generate_keypair()
    source.document = jwks_for(rotated, kid="FAKE-rotated-key")

    claims = await provider.verify(sign(rotated, kid="FAKE-rotated-key", subject="user_FAKE_2"))

    assert claims.subject == "user_FAKE_2"


async def test_a_cached_key_is_reused_within_the_ttl(private_key: rsa.RSAPrivateKey) -> None:
    source = _CountingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER, cache_ttl_s=3600)

    for _ in range(3):
        await provider.verify(sign(private_key))

    assert source.fetches == 1


async def test_an_expired_cache_is_refetched(private_key: rsa.RSAPrivateKey) -> None:
    source = _CountingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER, cache_ttl_s=0)

    await provider.verify(sign(private_key))
    await provider.verify(sign(private_key))

    assert source.fetches == 2


async def test_a_token_without_a_subject_is_rejected(private_key: rsa.RSAPrivateKey) -> None:
    provider = StaticKeyAuthProvider(jwks_for(private_key), issuer=FAKE_ISSUER)

    with pytest.raises(InvalidTokenError):
        await provider.verify(sign(private_key, subject=""))


async def test_the_error_never_carries_the_token(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    token = sign(private_key, issuer="https://evil.test")

    with pytest.raises(InvalidTokenError) as exc_info:
        await provider.verify(token)

    rendered = f"{exc_info.value} {exc_info.value.detail}"
    assert token not in rendered
    assert token.split(".")[1] not in rendered


class _HangingJwksSource:
    """A source whose fetch blocks until the test releases it.

    The point is the fast path: a reader whose ``kid`` is already cached must
    not queue behind an in-flight refresh, or one slow JWKS request turns into
    a stalled request queue for every signed-in user.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.fetches = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch(self) -> dict[str, Any]:
        self.fetches += 1
        self.started.set()
        await self.release.wait()
        return self.document


class _FailingJwksSource:
    """Clerk unreachable."""

    def __init__(self) -> None:
        self.fetches = 0

    async def fetch(self) -> dict[str, Any]:
        self.fetches += 1
        raise ConnectionError("jwks unreachable")


async def test_a_flood_of_unknown_kids_refetches_once_per_cooldown(
    private_key: rsa.RSAPrivateKey,
) -> None:
    """50 tokens, 50 invented ``kid`` values, one outbound request.

    Without the cooldown each bogus ``kid`` is a free request to Clerk's JWKS
    endpoint from an unauthenticated caller — an amplifier pointed at our own
    identity provider, and the fastest way to get rate limited by it.
    """
    source = _CountingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER, jwks_refresh_cooldown_s=60)
    await provider.verify(sign(private_key))
    assert source.fetches == 1

    for index in range(50):
        with pytest.raises(InvalidTokenError):
            await provider.verify(sign(private_key, kid=f"FAKE-unknown-{index}"))

    assert source.fetches == 2


async def test_an_unknown_kid_is_negative_cached_within_the_window(
    private_key: rsa.RSAPrivateKey,
) -> None:
    source = _CountingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER, jwks_refresh_cooldown_s=60)
    await provider.verify(sign(private_key))

    for _ in range(5):
        with pytest.raises(InvalidTokenError):
            await provider.verify(sign(private_key, kid="FAKE-same-unknown"))

    assert source.fetches == 2


async def test_the_cooldown_expires_and_a_later_rotation_is_picked_up(
    private_key: rsa.RSAPrivateKey,
) -> None:
    source = _CountingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER, jwks_refresh_cooldown_s=0)
    await provider.verify(sign(private_key))

    rotated = generate_keypair()
    with pytest.raises(InvalidTokenError):
        await provider.verify(sign(rotated, kid="FAKE-rotated-key"))
    source.document = jwks_for(rotated, kid="FAKE-rotated-key")

    claims = await provider.verify(sign(rotated, kid="FAKE-rotated-key", subject="user_FAKE_3"))

    assert claims.subject == "user_FAKE_3"


async def test_a_cached_kid_verifies_while_a_refetch_is_in_flight(
    private_key: rsa.RSAPrivateKey,
) -> None:
    source = _HangingJwksSource(jwks_for(private_key))
    provider = JwtAuthProvider(source, issuer=FAKE_ISSUER, jwks_refresh_cooldown_s=0)
    source.release.set()
    await provider.verify(sign(private_key))  # warm the cache
    source.release.clear()

    unknown = asyncio.ensure_future(provider.verify(sign(private_key, kid="FAKE-unknown")))
    await asyncio.wait_for(source.started.wait(), timeout=1)

    # the refetch is hanging; a token whose kid is cached must not wait for it
    claims = await asyncio.wait_for(
        provider.verify(sign(private_key, subject="user_FAKE_fast")), timeout=1
    )
    assert claims.subject == "user_FAKE_fast"

    source.release.set()
    with pytest.raises(InvalidTokenError):
        await unknown


async def test_an_unreachable_jwks_is_503_not_401(private_key: rsa.RSAPrivateKey) -> None:
    """ "Cannot verify right now" is not "your token is invalid".

    A 401 tells a signed-in browser to throw its session away and send the
    user back to Clerk; during a JWKS outage that logs out every user of the
    platform for a problem on our side. 503 + Retry-After tells the client to
    come back.
    """
    provider = JwtAuthProvider(_FailingJwksSource(), issuer=FAKE_ISSUER)

    with pytest.raises(AuthUnavailableError) as exc_info:
        await provider.verify(sign(private_key))

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers["Retry-After"]
    assert not isinstance(exc_info.value, InvalidTokenError)


async def test_an_invalid_token_is_still_401_when_the_jwks_is_reachable(
    provider: JwtAuthProvider, private_key: rsa.RSAPrivateKey
) -> None:
    with pytest.raises(InvalidTokenError) as exc_info:
        await provider.verify(sign(private_key, issuer="https://evil.test"))

    assert exc_info.value.status_code == 401
