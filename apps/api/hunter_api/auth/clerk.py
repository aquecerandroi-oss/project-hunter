"""Clerk session-token verification — SECURITY.md §1.

The token flow is: browser holds a Clerk session (httpOnly cookie), Next.js
reads the session token and calls this API with ``Authorization: Bearer <jwt>``.
This module is the only place that turns that string into claims. It verifies
the RS256 signature against Clerk's published JWKS (cached locally, so a
request costs no network call), plus ``exp``, ``nbf``, ``iss`` and — when the
token carries one — ``azp``, which must be an origin we serve.

Nothing here ever logs, echoes or embeds a token: :class:`InvalidTokenError`
carries a fixed reason, never the input. A bearer token is a live credential,
and a log line is a place credentials get read from.

``AuthProvider`` is the lock-in seam SECURITY.md §1 asks for: one Protocol,
two implementations (Clerk's JWKS over HTTP, and a static key document used by
the tests). Swapping identity providers is swapping the source, not the API.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Protocol

import httpx
import jwt
from fastapi import status
from pydantic import BaseModel

from hunter_api.errors import HunterError
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)

JWKS_TIMEOUT_S = 5.0
DEFAULT_CACHE_TTL_S = 3600
LEEWAY_S = 30
"""Clock skew tolerance for ``exp``/``nbf``. Half a minute is enough for two
machines whose clocks are NTP-disciplined and small enough that an expired
token is not usefully extended."""


class InvalidTokenError(HunterError):
    """401 for anything wrong with a bearer token — bad signature, expired,
    wrong issuer, unknown key. The reason is deliberately coarse: telling a
    caller *which* check failed helps an attacker tune the next attempt more
    than it helps a legitimate client, which can only do one thing either way
    (re-authenticate).
    """

    def __init__(self, detail: str = "The access token is missing or invalid.") -> None:
        super().__init__(
            type_slug="invalid-token",
            title="Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


class TokenClaims(BaseModel):
    """The handful of claims the rest of the API is allowed to care about."""

    subject: str
    """Clerk's user id (``sub``) — mirrored as ``users.external_auth_id``."""
    email: str | None = None
    azp: str | None = None
    session_id: str | None = None


class AuthProvider(Protocol):
    """Turns a bearer token into verified claims, or raises."""

    async def verify(self, token: str) -> TokenClaims: ...


class JwksSource(Protocol):
    """Where a JWKS document comes from."""

    async def fetch(self) -> dict[str, Any]: ...


class HttpJwksSource:
    """Clerk's published JWKS, over HTTPS."""

    def __init__(self, url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._url = url
        self._client = client

    async def fetch(self) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.get(self._url, timeout=JWKS_TIMEOUT_S)
        else:
            async with httpx.AsyncClient(timeout=JWKS_TIMEOUT_S) as client:
                response = await client.get(self._url)
        response.raise_for_status()
        document: dict[str, Any] = response.json()
        return document


class StaticJwksSource:
    """A fixed JWKS document — the tests' signing key, never a real one."""

    def __init__(self, document: dict[str, Any]) -> None:
        self._document = document

    async def fetch(self) -> dict[str, Any]:
        return self._document


class JwtAuthProvider:
    """Verifies RS256 tokens against a cached JWKS.

    The cache is keyed by ``kid`` and expires after ``cache_ttl_s``. An unknown
    ``kid`` triggers **one** refresh (Clerk rotates keys without warning, and a
    rotation must not sign every user out) and then fails: without that bound,
    a stream of tokens carrying invented ``kid`` values would turn into a
    stream of outbound requests, i.e. a free amplification vector.
    """

    def __init__(
        self,
        source: JwksSource,
        *,
        issuer: str,
        allowed_azp: Sequence[str] = (),
        cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
    ) -> None:
        self._source = source
        self._issuer = issuer
        self._allowed_azp = frozenset(allowed_azp)
        self._cache_ttl_s = cache_ttl_s
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def verify(self, token: str) -> TokenClaims:
        key = await self._key_for(_kid_of(token))
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,  # pyright: ignore[reportArgumentType]
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "sub"], "verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            logger.info("token_rejected", reason=type(exc).__name__)
            raise InvalidTokenError from None

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidTokenError
        azp = claims.get("azp")
        if isinstance(azp, str) and self._allowed_azp and azp not in self._allowed_azp:
            logger.info("token_rejected", reason="azp_not_allowed")
            raise InvalidTokenError
        return TokenClaims(
            subject=subject,
            email=_optional_str(claims.get("email")),
            azp=_optional_str(azp),
            session_id=_optional_str(claims.get("sid")),
        )

    async def _key_for(self, kid: str) -> jwt.PyJWK:
        async with self._lock:
            if self._is_stale() or kid not in self._keys:
                await self._refresh()
            key = self._keys.get(kid)
        if key is None:
            logger.info("token_rejected", reason="unknown_kid")
            raise InvalidTokenError
        return key

    def _is_stale(self) -> bool:
        if self._fetched_at is None:
            return True
        return (time.monotonic() - self._fetched_at) >= self._cache_ttl_s

    async def _refresh(self) -> None:
        try:
            document = await self._source.fetch()
        except Exception:
            logger.warning("jwks_fetch_failed")
            raise InvalidTokenError("Authentication is temporarily unavailable.") from None
        self._keys = _parse_jwks(document.get("keys"))
        self._fetched_at = time.monotonic()


class ClerkAuthProvider(JwtAuthProvider):
    """The production provider: Clerk's JWKS URL and issuer, from settings.

    ``allowed_azp`` is the CORS allowlist. Clerk stamps ``azp`` with the origin
    a token was minted for, so a token issued to some other application's
    frontend — even a legitimate one on the same Clerk instance — is refused
    here instead of being accepted as one of ours.
    """

    def __init__(self, settings: ApiSettings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(
            HttpJwksSource(settings.clerk_jwks_url.get_secret_value(), client=client),
            issuer=settings.clerk_issuer,
            allowed_azp=settings.cors_allowed_origins,
            cache_ttl_s=DEFAULT_CACHE_TTL_S,
        )


class StaticKeyAuthProvider(JwtAuthProvider):
    """A provider over a fixed JWKS document — for tests only, never wired in
    ``create_app``. Keeps the tests on the *real* verification path (signature,
    ``exp``, ``iss``, ``azp``) rather than a stub that trusts its input.
    """

    def __init__(
        self,
        document: dict[str, Any],
        *,
        issuer: str,
        allowed_azp: Sequence[str] = (),
    ) -> None:
        super().__init__(StaticJwksSource(document), issuer=issuer, allowed_azp=allowed_azp)


def _kid_of(token: str) -> str:
    try:
        header: dict[str, Any] = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise InvalidTokenError from None
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise InvalidTokenError
    return kid


def _parse_jwks(keys: object) -> dict[str, jwt.PyJWK]:
    if not isinstance(keys, list):
        return {}
    parsed: dict[str, jwt.PyJWK] = {}
    for entry in _dicts(keys):  # pyright: ignore[reportUnknownArgumentType]
        kid = entry.get("kid")
        if not isinstance(kid, str):
            continue
        try:
            parsed[kid] = jwt.PyJWK(entry)
        except jwt.PyJWTError:
            logger.warning("jwks_entry_unusable", kid=kid)
    return parsed


def _dicts(values: Iterable[object]) -> list[dict[str, Any]]:
    return [value for value in values if isinstance(value, dict)]


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
