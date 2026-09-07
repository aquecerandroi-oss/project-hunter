"""HTTP core for the Binance **SPOT** REST client: budget, 429/418, retries.

Deliberately a sibling of - not a change to -
:class:`hunter_exchanges.binance.rest.BinanceRestClient`'s own ``_get``
(T3.0a scope: the USDS-M adapter's behaviour must not move, and its suite
must stay green with no test edits). The semantics are the same contract
``docs/EXCHANGE_INTEGRATION.md`` §5 states, applied to the *spot* budget:

- every call is charged to the shared token bucket **before** the request,
  and on every retry too (a retry is a real request Binance counts);
- ``429``/``418`` -> :class:`~hunter_exchanges.base.RateLimited` straight
  from ``Retry-After``, plus a cooldown on the bucket and on the shared IP
  gate. Never a silent retry loop: the caller raises a ``system_event``;
- network error/``5xx`` -> retry with exponential backoff + jitter, then
  :class:`~hunter_exchanges.base.ExchangeUnavailable`. Any other ``4xx``
  (invalid/delisted symbol, bad parameter) -> a non-retryable
  :class:`~hunter_exchanges.base.ExchangeError`, because the same request
  will fail identically forever;
- ``X-MBX-USED-WEIGHT-1M`` reconciles the bucket with Binance's own count.

The bucket is ``rl:binance:spot_request_weight``: same exchange (one venue,
one ``exchanges`` row, one IP ban surface) but **never** the same key as the
USDS-M ``request_weight`` bucket - ``/api/v3`` and ``/fapi/v1`` have
independent budgets (6000/min vs 2400/min), and two limiters with different
capacities writing one key would corrupt both.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, RateLimited
from hunter_exchanges.binance_spot.identity import EXCHANGE
from hunter_exchanges.rate_limit import (
    REST_GATE_OK,
    REST_GATE_SUSPENDED,
    IpRateGate,
    TokenBucketRateLimiter,
)

__all__ = [
    "BASE_URL",
    "REQUEST_WEIGHT_BUCKET",
    "REQUEST_WEIGHT_CAPACITY",
    "REQUEST_WEIGHT_PERIOD_S",
    "SpotHttp",
]

BASE_URL = "https://api.binance.com"
REQUEST_WEIGHT_BUCKET = "spot_request_weight"
#: ``exchangeInfo.rateLimits`` on 2026-09-06: REQUEST_WEIGHT 6000 / 1 MINUTE.
#: Re-read from the exchange by ``BinanceSpotRestClient.refresh_request_weight_limit``.
REQUEST_WEIGHT_CAPACITY = 6000
REQUEST_WEIGHT_PERIOD_S = 60.0
_USED_WEIGHT_HEADER = "X-MBX-USED-WEIGHT-1M"


class SpotHttp:
    """One rate-limited, retrying GET against ``api.binance.com``.

    ``sleep``/``http_client``/``rate_limiter``/``ip_gate`` are injectable so
    tests never touch the network or wait real seconds, and so the caller can
    hand in the *same* :class:`IpRateGate` the USDS-M client uses: a 429 on
    either API is a block on the same IP.
    """

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        ip_gate: IpRateGate | None = None,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 10.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(10.0, connect=5.0)
        )
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(
            EXCHANGE,
            capacity=REQUEST_WEIGHT_CAPACITY,
            refill_period_s=REQUEST_WEIGHT_PERIOD_S,
        )
        self._ip_gate = ip_gate or IpRateGate()
        self._rate_limiter.ip_gate = self._ip_gate
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._sleep = sleep

    @property
    def rate_limiter(self) -> TokenBucketRateLimiter:
        return self._rate_limiter

    @property
    def ip_gate(self) -> IpRateGate:
        """Exposed so the USDS-M client on the same IP can share this gate."""
        return self._ip_gate

    def rest_gate_status(self) -> str:
        """``"ok"`` | ``"suspended"`` - whether REST calls are being admitted."""
        return REST_GATE_SUSPENDED if self._rate_limiter.suspended else REST_GATE_OK

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _backoff(self, attempt: int) -> None:
        delay = min(self._backoff_max_s, self._backoff_base_s * (2**attempt))
        await self._sleep(delay + random.uniform(0, delay * 0.1))

    async def get(self, path: str, params: dict[str, Any] | None = None, *, weight: int) -> Any:
        """GET ``path`` with ``weight`` charged to the spot bucket."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            is_last_attempt = attempt == self._max_retries - 1
            await self._rate_limiter.acquire(REQUEST_WEIGHT_BUCKET, weight)
            try:
                response = await self._client.get(path, params=params)
            except httpx.TransportError as exc:
                last_exc = ExchangeUnavailable(
                    f"binance spot transport error: {exc}", exchange=EXCHANGE
                )
                if not is_last_attempt:
                    await self._backoff(attempt)
                continue
            if response.status_code in (429, 418):
                retry_after = float(response.headers.get("Retry-After", "60"))
                await self._rate_limiter.cooldown(REQUEST_WEIGHT_BUCKET, retry_after_s=retry_after)
                raise RateLimited(
                    f"binance spot responded {response.status_code} for {path}",
                    exchange=EXCHANGE,
                    retry_after_s=retry_after,
                )
            used_weight = response.headers.get(_USED_WEIGHT_HEADER)
            if used_weight is not None:
                await self._rate_limiter.record_used_weight(REQUEST_WEIGHT_BUCKET, int(used_weight))
            if response.status_code >= 500:
                last_exc = ExchangeUnavailable(
                    f"binance spot {response.status_code} for {path}", exchange=EXCHANGE
                )
                if not is_last_attempt:
                    await self._backoff(attempt)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ExchangeError(
                    f"binance spot {response.status_code} for {path}: {response.text[:200]}",
                    exchange=EXCHANGE,
                    retryable=False,
                ) from exc
            return response.json()
        raise last_exc or ExchangeUnavailable(
            f"binance spot request failed after retries: {path}", exchange=EXCHANGE
        )
