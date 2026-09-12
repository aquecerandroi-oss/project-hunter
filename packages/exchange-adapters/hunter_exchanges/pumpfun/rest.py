"""``frontend-api-v3.pump.fun`` REST client — curve state by mint.

Undocumented-by-pump.fun endpoint the site's own frontend uses (T4.0 §2);
never the sole source of anything the scanner decides on
(T4-MEME-RADAR.md §2's "decisão proposta"). ``GET /coins/{mint}`` (a
by-mint variant of the ``/coins`` list endpoint, both confirmed live against
the real API on 2026-09-12) returns the token's current curve reserves as
raw integers (lamports / 6-decimal token subunits), same wire format the
Solana RPC gives (``rpc.py``).

Rate limit: measured live on the list endpoint at **60 requests / 60 s per
IP** via the ``x-ratelimit-*`` response headers (T4.0 §2); the by-mint
endpoint returned no such headers in this task's own live capture
(``tests/fixtures/pumpfun/frontend_api_v3_coin_by_mint_response_headers.txt``)
— rather than trust an absence of headers as "unlimited", this client
applies the same 60/60s budget to every call regardless of sub-path, one
token bucket per process (``rl:pumpfun:coins``), same discipline as
``docs/EXCHANGE_INTEGRATION.md`` §5.

``429``/``418`` -> :class:`~hunter_exchanges.base.RateLimited`, never a
silent retry loop — the caller is expected to turn that into a
``system_event`` (``EXCHANGE_INTEGRATION.md`` §5), exactly like
``hunter_exchanges.binance_spot.http.SpotHttp``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from urllib.parse import quote

import httpx

from hunter_core.domain.types import utcnow
from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.models import (
    NormalizedCurveState,
    NormalizedMayhemOverview,
    NormalizedSolPrice,
)
from hunter_exchanges.pumpfun.normalize import parse_curve_state_rest
from hunter_exchanges.pumpfun.quote import GlobalParams, parse_global_params
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

__all__ = [
    "BASE_URL",
    "REQUEST_BUCKET",
    "REQUEST_CAPACITY",
    "REQUEST_PERIOD_S",
    "PumpFunRestClient",
]

EXCHANGE = "pumpfun"
BASE_URL = "https://frontend-api-v3.pump.fun"
REQUEST_BUCKET = "coins"
REQUEST_CAPACITY = 60
REQUEST_PERIOD_S = 60.0


class PumpFunRestClient:
    """One rate-limited, retrying GET against ``frontend-api-v3.pump.fun``."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
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
            EXCHANGE, capacity=REQUEST_CAPACITY, refill_period_s=REQUEST_PERIOD_S
        )
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._sleep = sleep

    @property
    def rate_limiter(self) -> TokenBucketRateLimiter:
        return self._rate_limiter

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _backoff(self, attempt: int) -> None:
        import random

        delay = min(self._backoff_max_s, self._backoff_base_s * (2**attempt))
        await self._sleep(delay + random.uniform(0, delay * 0.1))

    async def _get(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            is_last_attempt = attempt == self._max_retries - 1
            await self._rate_limiter.acquire(REQUEST_BUCKET, 1)
            try:
                response = await self._client.get(path, params=params)
            except httpx.TransportError:
                last_exc = ExchangeUnavailable("pumpfun rest transport error", exchange=EXCHANGE)
                if not is_last_attempt:
                    await self._backoff(attempt)
                continue
            if response.status_code in (429, 418):
                retry_after = float(response.headers.get("Retry-After", "60"))
                await self._rate_limiter.cooldown(REQUEST_BUCKET, retry_after_s=retry_after)
                raise RateLimited(
                    f"pumpfun rest responded {response.status_code}",
                    exchange=EXCHANGE,
                    retry_after_s=retry_after,
                )
            if response.status_code == 404:
                raise ExchangeError(
                    "pumpfun rest resource not found", exchange=EXCHANGE, retryable=False
                )
            if response.status_code >= 500:
                last_exc = ExchangeUnavailable(
                    f"pumpfun rest {response.status_code}", exchange=EXCHANGE
                )
                if not is_last_attempt:
                    await self._backoff(attempt)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ExchangeError(
                    f"pumpfun rest {response.status_code}",
                    exchange=EXCHANGE,
                    retryable=False,
                ) from exc
            try:
                return json.loads(response.content, parse_float=Decimal)
            except (ValueError, UnicodeDecodeError) as exc:
                raise MalformedMessage("invalid REST JSON", exchange=EXCHANGE) from exc
        raise last_exc or ExchangeUnavailable(
            "pumpfun rest request failed after retries", exchange=EXCHANGE
        )

    async def get_curve_state(self, mint: str) -> NormalizedCurveState:
        """Current bonding curve reserves for ``mint``, best-effort (T4.0 §2:
        undocumented endpoint, no SLA)."""
        raw = await self._get(f"/coins/{quote(mint, safe='')}")
        if not isinstance(raw, dict):
            raise MalformedMessage("coin must be an object", exchange=EXCHANGE)
        raw = cast(dict[str, Any], raw)
        if raw.get("mint") != mint:
            raise MalformedMessage("REST returned a different mint", exchange=EXCHANGE)
        return parse_curve_state_rest(raw)

    async def list_mayhem(
        self, *, limit: int = 50, mayhem_state: str = "active"
    ) -> list[NormalizedCurveState]:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        raw = await self._get("/coins/mayhem-mode", {"limit": limit, "mayhemState": mayhem_state})
        if not isinstance(raw, list) or not all(
            isinstance(item, dict) for item in cast(list[Any], raw)
        ):
            raise MalformedMessage("mayhem listing must be an array of objects", exchange=EXCHANGE)
        return [parse_curve_state_rest(item) for item in cast(list[dict[str, Any]], raw)]

    async def get_global_params(self, created_at_ms: int) -> GlobalParams:
        """``GET /global-params/{created_timestamp_ms}`` — the curve parameters in
        force at that instant (``docs/PUMPFUN.md`` §1.1 #19, §4.2). The
        denominator of progress and the fill threshold are derived from this
        record (T4.2d); its own rate-limit group upstream is 50/60 s, charged
        here to the one bucket this client has, like ``get_sol_price``."""
        raw = await self._get(f"/global-params/{int(created_at_ms)}")
        if not isinstance(raw, dict):
            raise MalformedMessage("global params must be an object", exchange=EXCHANGE)
        try:
            return parse_global_params(cast(dict[str, Any], raw))
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedMessage(f"global params malformed: {exc}", exchange=EXCHANGE) from exc

    async def get_mayhem_overview(self) -> NormalizedMayhemOverview:
        raw = await self._get("/mayhem/overview")
        if not isinstance(raw, dict):
            raise MalformedMessage("mayhem overview must be an object", exchange=EXCHANGE)
        now = utcnow()
        return NormalizedMayhemOverview(
            metadata=cast(dict[str, Any], raw), observed_at=now, received_at=now
        )

    async def get_sol_price(self) -> NormalizedSolPrice:
        """``GET /sol-price`` — ``{solPrice, asOfTimestamp (ms), stale}``.

        Its own rate-limit group upstream (50/60 s, ``docs/PUMPFUN.md`` §1.4),
        but this client charges it to the one bucket it has: a caller that
        shares the instance with the curve poller spends curve budget on it,
        and a caller that wants the separate group builds a second client.
        """
        raw = await self._get("/sol-price")
        if not isinstance(raw, dict):
            raise MalformedMessage("sol price must be an object", exchange=EXCHANGE)
        payload = cast(dict[str, Any], raw)
        price, as_of_ms, stale = (
            payload.get("solPrice"),
            payload.get("asOfTimestamp"),
            payload.get("stale"),
        )
        if (
            not isinstance(price, Decimal | int)
            or not isinstance(as_of_ms, int)
            or isinstance(as_of_ms, bool)
        ):
            raise MalformedMessage("sol price fields have an unexpected shape", exchange=EXCHANGE)
        now = utcnow()
        return NormalizedSolPrice(
            price_usd=Decimal(price),
            as_of=datetime.fromtimestamp(as_of_ms / 1000, tz=UTC),
            stale=bool(stale),
            observed_at=now,
            received_at=now,
        )
