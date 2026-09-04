"""Where signing keys come from, and how long we believe them.

Split out of :mod:`hunter_api.auth.clerk` because "fetch and cache a JWKS" is a
different job from "verify a token", and this one carries all the adversarial
detail: ``kid`` is chosen by whoever sends the token, so every branch here is
about what an unauthenticated caller can make this process do.

Three properties, each answering a specific failure:

- **An unknown ``kid`` refetches at most once per cooldown.** Clerk rotates
  keys without warning and a rotation must not sign every user out, so an
  unknown ``kid`` does earn a refetch — but without a cooldown a stream of
  invented ones is a stream of outbound requests to our own identity provider,
  which is an amplifier pointed at the thing every request depends on.
- **Unknown ``kid`` values are remembered as unknown** for that same window, in
  a bounded set, so the flood does not even reach the lock.
- **A reader whose ``kid`` is cached never waits on the lock.** The fast path
  reads the mapping outside it and only a refetch is serialized; otherwise one
  slow JWKS request stalls every signed-in user behind it.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Protocol

import httpx
import jwt

from hunter_api.auth.errors import AuthUnavailableError, InvalidTokenError
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = get_logger(__name__)

JWKS_TIMEOUT_S = 5.0
DEFAULT_CACHE_TTL_S = 3600
DEFAULT_REFRESH_COOLDOWN_S = 60.0
"""How long an unknown ``kid`` is remembered as unknown, and the minimum gap
between two refetches triggered by one. Both are the same number on purpose:
the window in which we have already asked Clerk and been told no."""

MAX_UNKNOWN_KIDS = 512
"""Bound on the negative cache. ``kid`` is attacker-chosen, so an unbounded set
of them is an unbounded allocation driven from outside."""


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


class JwksCache:
    """The signing keys this process will accept, and when it will ask again."""

    def __init__(
        self,
        source: JwksSource,
        *,
        cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
        refresh_cooldown_s: float = DEFAULT_REFRESH_COOLDOWN_S,
    ) -> None:
        self._source = source
        self._cache_ttl_s = cache_ttl_s
        self._cooldown_s = refresh_cooldown_s
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._failed_at: float | None = None
        self._unknown_kids: dict[str, float] = {}
        self._last_unknown_refresh_at: float | None = None
        self._lock = asyncio.Lock()

    async def key_for(self, kid: str) -> jwt.PyJWK:
        """The key for ``kid``, or :class:`InvalidTokenError` if there is none
        (and :class:`AuthUnavailableError` if we cannot currently tell).
        """
        fresh = self._fresh_key(kid)
        if fresh is not None:
            return fresh
        if self._recently_unknown(kid):
            raise self._unknown_kid()
        async with self._lock:
            return await self._key_under_lock(kid)

    async def _key_under_lock(self, kid: str) -> jwt.PyJWK:
        """The slow path: everything that may talk to the network.

        Re-checks the cache first, because the request that held the lock may
        have fetched exactly the document this one was waiting for.
        """
        fresh = self._fresh_key(kid)
        if fresh is not None:
            return fresh
        if self._recently_unknown(kid):
            raise self._unknown_kid()

        refreshed = False
        if self._is_stale():
            if self._may_retry_after_failure():
                await self._refresh(kid_in_cache=kid in self._keys)
                refreshed = True
            elif not self._keys:
                # the source is down and the cache is empty: there is no key to
                # verify with and no point asking again yet
                raise AuthUnavailableError
        key = self._keys.get(kid)
        if key is not None:
            return key

        if not refreshed and self._may_refetch_for_unknown():
            # a rotation: Clerk published a key we have never seen. Stamped
            # before the await, so a fetch that fails still spends the window
            self._last_unknown_refresh_at = time.monotonic()
            await self._refresh(kid_in_cache=False)
            key = self._keys.get(kid)
            if key is not None:
                return key
        self._remember_unknown(kid)
        raise self._unknown_kid()

    def _fresh_key(self, kid: str) -> jwt.PyJWK | None:
        """The lock-free fast path: a cached key from a document still inside
        its TTL. Reading the mapping needs no lock — a refresh replaces it
        wholesale rather than mutating it in place.
        """
        if self._is_stale():
            return None
        return self._keys.get(kid)

    def _is_stale(self) -> bool:
        if self._fetched_at is None:
            return True
        return (time.monotonic() - self._fetched_at) >= self._cache_ttl_s

    def _may_refetch_for_unknown(self) -> bool:
        if self._last_unknown_refresh_at is None:
            return True
        return (time.monotonic() - self._last_unknown_refresh_at) >= self._cooldown_s

    def _may_retry_after_failure(self) -> bool:
        """A failed fetch also spends the cooldown: an unreachable JWKS URL
        would otherwise be retried once per inbound request, turning a provider
        outage into our own outbound flood.
        """
        if self._failed_at is None:
            return True
        return (time.monotonic() - self._failed_at) >= self._cooldown_s

    def _recently_unknown(self, kid: str) -> bool:
        expires_at = self._unknown_kids.get(kid)
        if expires_at is None:
            return False
        if time.monotonic() >= expires_at:
            self._unknown_kids.pop(kid, None)
            return False
        return True

    def _remember_unknown(self, kid: str) -> None:
        if len(self._unknown_kids) >= MAX_UNKNOWN_KIDS:
            # insertion-ordered: drop the oldest entry rather than growing
            self._unknown_kids.pop(next(iter(self._unknown_kids)), None)
        self._unknown_kids[kid] = time.monotonic() + self._cooldown_s

    def _unknown_kid(self) -> InvalidTokenError:
        logger.info("token_rejected", reason="unknown_kid")
        return InvalidTokenError()

    async def _refresh(self, *, kid_in_cache: bool) -> None:
        """Re-read the JWKS document. Raises :class:`AuthUnavailableError` when
        the fetch fails and nothing usable is cached.

        ``kid_in_cache`` is the "usable" test: with the caller's key still in
        the last document we serve it and log, rather than 503-ing an entire
        deployment over a refresh a stale-but-valid cache could have covered.
        Without it there is nothing to fall back to.
        """
        try:
            document = await self._source.fetch()
        except Exception:
            self._failed_at = time.monotonic()
            logger.warning("jwks_fetch_failed", serving_cached=kid_in_cache)
            if not kid_in_cache:
                raise AuthUnavailableError from None
            return
        self._keys = parse_jwks(document.get("keys"))
        self._fetched_at = time.monotonic()
        self._failed_at = None
        self._unknown_kids.clear()


def parse_jwks(keys: object) -> dict[str, jwt.PyJWK]:
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
