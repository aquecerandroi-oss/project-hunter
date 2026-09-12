"""The one budgeted GET the three pump.fun HTTP clients of T4.2c share.

``rest.py`` (``frontend-api-v3``) carries its own copy of this loop from T4.1;
``indexer_rest.py`` and ``swap_api.py`` were written after it and use this
function instead of a third and fourth copy. Same contract as ``rest.py``:

- the token bucket is charged **before** the request, once per attempt;
- ``429``/``418`` cool the bucket down for ``Retry-After`` and raise
  :class:`RateLimited` — never a silent retry loop (``EXCHANGE_INTEGRATION.md``
  §5; the caller turns it into a system event / a counted error);
- ``404`` is a non-retryable :class:`ExchangeError`; ``5xx`` and transport
  errors retry a bounded number of times with capped exponential backoff and
  end in :class:`ExchangeUnavailable`;
- the body is decoded with ``parse_float=Decimal`` so no price ever becomes a
  float on its way in.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import httpx

from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage, RateLimited
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

BACKOFF_BASE_S = 0.5
BACKOFF_MAX_S = 10.0


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
            retry_after = float(response.headers.get("Retry-After", "60"))
            await limiter.cooldown(bucket, retry_after_s=retry_after)
            raise RateLimited(
                f"{exchange} responded {response.status_code}",
                exchange=exchange,
                retry_after_s=retry_after,
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


__all__ = ["get_json_with_budget"]
