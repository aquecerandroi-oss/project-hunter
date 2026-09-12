"""The one budgeted GET the three pump.fun HTTP clients of T4.2c share.

``rest.py`` (``frontend-api-v3``) carries its own copy of this loop from T4.1;
``indexer_rest.py`` and ``swap_api.py`` were written after it and use this
function instead of a third and fourth copy. Same contract as ``rest.py``:

- the token bucket is charged **before** the request, once per attempt;
- ``429``/``418`` cool the bucket down for ``Retry-After`` and raise
  :class:`HttpRateLimited` — a :class:`RateLimited` that carries the status and
  the limit headers the server sent, so a caller can tell a refusal **by the
  server** from one by our own bucket (T4.2f: ``tape_reason = rate_limited``
  only when there was a real 429) and can measure the limit it was refused at
  — never a silent retry loop (``EXCHANGE_INTEGRATION.md`` §5; the caller turns
  it into a system event / a counted error);
- ``404`` is a non-retryable :class:`ExchangeError`; ``5xx`` and transport
  errors retry a bounded number of times with capped exponential backoff and
  end in :class:`ExchangeUnavailable`;
- the body is decoded with ``parse_float=Decimal`` so no price ever becomes a
  float on its way in.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Any

import httpx

from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage, RateLimited
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

BACKOFF_BASE_S = 0.5
BACKOFF_MAX_S = 10.0
DEFAULT_RETRY_AFTER_S = 60.0
RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "retry-after",
    "server",
    "cf-ray",
)
"""What a 429 is allowed to teach: the backend's own window (``x-ratelimit-*``),
the wait it asks for, and who answered (``server: cloudflare`` with no
``x-ratelimit-*`` is the edge's rule, not the application's — the shape the
swap-api's real limit turned out to have, ``swap_api.py``)."""


class HttpRateLimited(RateLimited):
    """A ``429``/``418`` **from the server** — never from our own token bucket.

    ``headers`` holds the :data:`RATE_LIMIT_HEADERS` the response carried;
    :attr:`edge` says whether the refusal came from the CDN's rule rather than
    the application's limiter (the two answer with different headers and mean
    different ceilings).
    """

    def __init__(
        self,
        message: str,
        *,
        exchange: str,
        retry_after_s: float,
        status_code: int,
        headers: Mapping[str, str],
    ) -> None:
        super().__init__(message, exchange=exchange, retry_after_s=retry_after_s)
        self.status_code = status_code
        self.headers: dict[str, str] = dict(headers)

    @property
    def edge(self) -> bool:
        server = self.headers.get("server", "").lower()
        return "cloudflare" in server and "x-ratelimit-limit" not in self.headers


def retry_after_s(headers: Mapping[str, str]) -> float:
    """``Retry-After`` in seconds; an absent or non-numeric value (an HTTP date)
    is the default, never a crash on a header we did not write."""
    try:
        return max(1.0, float(headers.get("retry-after", DEFAULT_RETRY_AFTER_S)))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_S


async def get_json_with_budget(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, str | int] | None,
    exchange: str,
    limiter: TokenBucketRateLimiter,
    bucket: str,
    max_retries: int,
    sleep: Callable[[float], Awaitable[None]],
    rand: Callable[[float, float], float],
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(max(1, max_retries)):
        is_last = attempt == max(1, max_retries) - 1
        await limiter.acquire(bucket, 1)
        try:
            response = await client.get(path, params=params)
        except httpx.TransportError:
            last_exc = ExchangeUnavailable(f"{exchange} transport error", exchange=exchange)
            if not is_last:
                await _backoff(attempt, sleep, rand)
            continue
        if response.status_code in (429, 418):
            headers = {
                name: response.headers[name]
                for name in RATE_LIMIT_HEADERS
                if name in response.headers
            }
            retry_after = retry_after_s(headers)
            await limiter.cooldown(bucket, retry_after_s=retry_after)
            raise HttpRateLimited(
                f"{exchange} responded {response.status_code}",
                exchange=exchange,
                retry_after_s=retry_after,
                status_code=response.status_code,
                headers=headers,
            )
        if response.status_code == 404:
            raise ExchangeError(
                f"{exchange} resource not found", exchange=exchange, retryable=False
            )
        if response.status_code >= 500:
            last_exc = ExchangeUnavailable(f"{exchange} {response.status_code}", exchange=exchange)
            if not is_last:
                await _backoff(attempt, sleep, rand)
            continue
        if response.status_code >= 400:
            raise ExchangeError(
                f"{exchange} {response.status_code}", exchange=exchange, retryable=False
            )
        try:
            return json.loads(response.content, parse_float=Decimal)
        except (ValueError, UnicodeDecodeError) as exc:
            raise MalformedMessage(f"{exchange} invalid JSON", exchange=exchange) from exc
    raise last_exc or ExchangeUnavailable(f"{exchange} request failed", exchange=exchange)


async def _backoff(
    attempt: int,
    sleep: Callable[[float], Awaitable[None]],
    rand: Callable[[float, float], float],
) -> None:
    delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2**attempt))
    await sleep(delay + rand(0, delay * 0.1))


__all__ = ["RATE_LIMIT_HEADERS", "HttpRateLimited", "get_json_with_budget", "retry_after_s"]
