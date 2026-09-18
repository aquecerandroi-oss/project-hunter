"""USD/BRL exchange rate for T4.57's "Carteira real" panel — cached in-process
so a page a viewer refreshes every few seconds never turns into a stream of
requests to a third party for a number that moves once in a while.

``https://api.frankfurter.dev/v1/latest?base=USD&symbols=BRL`` (frankfurter.dev,
no key, no secret to leak) is asked at most once an hour
(:data:`FX_CACHE_TTL_S`); every reader inside that hour — and every reader
while an outage is in progress — gets the last known-good quote back
immediately, so the wallet endpoint never waits on this call longer than
:data:`FX_TIMEOUT_S`. A quote nobody has ever actually read returns ``None``
with a named reason instead of inventing a rate (CLAUDE.md: unavailable never
becomes zero, or in this case, one).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import httpx

from hunter_core.logging import get_logger

__all__ = [
    "FRANKFURTER_URL",
    "FX_CACHE_TTL_S",
    "FX_TIMEOUT_S",
    "UsdBrlQuote",
    "UsdBrlRateCache",
    "usd_brl_cache",
]

logger = get_logger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=BRL"
FX_TIMEOUT_S = 3.0
FX_CACHE_TTL_S = 3600.0


@dataclass(frozen=True, slots=True)
class UsdBrlQuote:
    rate: Decimal
    observed_at: datetime
    source: str = "frankfurter.dev"


class UsdBrlRateCache:
    """One shared quote per process. ``get`` never raises — a fetch failure
    falls back to the last known quote (``reason="stale"``) or, before the
    first successful fetch ever, to ``None`` (``reason="no_fx_quote"``)."""

    def __init__(self, *, ttl_s: float = FX_CACHE_TTL_S, timeout_s: float = FX_TIMEOUT_S) -> None:
        self._ttl_s = ttl_s
        self._timeout_s = timeout_s
        self._quote: UsdBrlQuote | None = None
        self._fetched_monotonic: float | None = None

    async def get(
        self, *, client: httpx.AsyncClient | None = None
    ) -> tuple[UsdBrlQuote | None, str | None]:
        now = time.monotonic()
        if (
            self._quote is not None
            and self._fetched_monotonic is not None
            and now - self._fetched_monotonic < self._ttl_s
        ):
            return self._quote, None
        try:
            rate = await self._fetch(client)
        except (httpx.HTTPError, ValueError, KeyError, InvalidOperation) as exc:
            logger.warning("usd_brl_rate_fetch_failed", error_type=type(exc).__name__)
            if self._quote is not None:
                return self._quote, "stale"
            return None, "no_fx_quote"
        quote = UsdBrlQuote(rate=rate, observed_at=datetime.now(UTC))
        self._quote = quote
        self._fetched_monotonic = now
        return quote, None

    async def _fetch(self, client: httpx.AsyncClient | None) -> Decimal:
        if client is not None:
            response = await client.get(FRANKFURTER_URL, timeout=self._timeout_s)
        else:
            async with httpx.AsyncClient(timeout=self._timeout_s) as owned:
                response = await owned.get(FRANKFURTER_URL)
        response.raise_for_status()
        document: dict[str, Any] = response.json()
        rates = document.get("rates")
        if not isinstance(rates, dict) or "BRL" not in rates:
            raise KeyError("BRL")
        return Decimal(str(cast(dict[str, Any], rates)["BRL"]))


usd_brl_cache = UsdBrlRateCache()
"""The process-wide cache the router reads from — one instance so every
request shares the same hourly budget, same convention as
``hunter_api.auth.jwks``'s module-level JWKS cache."""
