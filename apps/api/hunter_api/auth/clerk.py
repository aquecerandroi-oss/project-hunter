"""Clerk session-token verification — SECURITY.md §1.

The token flow is: browser holds a Clerk session (httpOnly cookie), Next.js
reads the session token and calls this API with ``Authorization: Bearer <jwt>``.
This module is the only place that turns that string into claims. It verifies
the RS256 signature against Clerk's published JWKS (cached in
:mod:`hunter_api.auth.jwks`, so a request costs no network call), plus ``exp``,
``nbf``, ``iss`` and — when the token carries one — ``azp``, which must be an
origin we serve.

Nothing here ever logs, echoes or embeds a token: :class:`InvalidTokenError`
carries a fixed reason, never the input. A bearer token is a live credential,
and a log line is a place credentials get read from.

``AuthProvider`` is the lock-in seam SECURITY.md §1 asks for: one Protocol,
two implementations (Clerk's JWKS over HTTP, and a static key document used by
the tests). Swapping identity providers is swapping the source, not the API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import httpx
import jwt
from pydantic import BaseModel

from hunter_api.auth.errors import AuthUnavailableError, InvalidTokenError
from hunter_api.auth.jwks import (
    DEFAULT_CACHE_TTL_S,
    DEFAULT_REFRESH_COOLDOWN_S,
    HttpJwksSource,
    JwksCache,
    JwksSource,
    StaticJwksSource,
)
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_api.settings import ApiSettings

__all__ = [
    "AuthProvider",
    "AuthUnavailableError",
    "ClerkAuthProvider",
    "HttpJwksSource",
    "InvalidTokenError",
    "JwksSource",
    "JwtAuthProvider",
    "StaticJwksSource",
    "StaticKeyAuthProvider",
    "TokenClaims",
]

logger = get_logger(__name__)

LEEWAY_S = 30
"""Clock skew tolerance for ``exp``/``nbf``. Half a minute is enough for two
machines whose clocks are NTP-disciplined and small enough that an expired
token is not usefully extended."""


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


class JwtAuthProvider:
    """Verifies RS256 tokens against a cached JWKS (:class:`JwksCache`)."""

    def __init__(
        self,
        source: JwksSource,
        *,
        issuer: str,
        allowed_azp: Sequence[str] = (),
        cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
        jwks_refresh_cooldown_s: float = DEFAULT_REFRESH_COOLDOWN_S,
    ) -> None:
        self._issuer = issuer
        self._allowed_azp = frozenset(allowed_azp)
        self._keys = JwksCache(
            source, cache_ttl_s=cache_ttl_s, refresh_cooldown_s=jwks_refresh_cooldown_s
        )

    async def verify(self, token: str) -> TokenClaims:
        key = await self._keys.key_for(_kid_of(token))
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
            jwks_refresh_cooldown_s=settings.jwks_refresh_cooldown_s,
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


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
