"""``avgPrice`` — the reference price a MARKET order's ``NOTIONAL`` filter is judged by.

**Why this endpoint, and not the two the brief offered.** Binance judges the
``NOTIONAL``/``MIN_NOTIONAL`` filter of a MARKET order against *its own* average
price over the market's ``avgPriceMins`` minutes, and the only public endpoint
that serves that exact number is ``GET /api/v3/avgPrice`` (weight 2,
``hunter_exchanges.binance_spot.rest``): the payload is literally
``{"mins": 5, "price": ...}``, the same ``mins`` the market's filter declares.
The alternatives are the wrong venue or the wrong number:

- ``GET /fapi/v1/ticker/price`` and ``GET /fapi/v1/premiumIndex`` are **USDS-M
  perpetual** endpoints. D1 of the M3 plan is "SPOT executes, the perpetual
  decides"; a perpetual last price or a funding/mark index has no authority over
  a spot filter, and Binance would still reject the order our simulation booked;
- ``GET /api/v3/ticker/price`` (spot) is the *last trade*, which is what
  ``avgPriceMins == 0`` means. For the 15 monitored markets measured on the VPS
  on 2026-09-08 every one declares ``avgPriceMins = 5``, so substituting the
  last trade would be judging the filter by the very print the average exists to
  smooth.

**The freshness bound is the caller's, and it is stamped, not assumed.** This
module publishes ``observed_at`` — when *we* received the number — and nothing
else; :func:`hunter_execution_worker.entry_inputs.missing_inputs`, which owns the
cycle's ``now``, is what refuses a quote older than
:data:`AVG_PRICE_MAX_AGE_S`. A reader that decided its own staleness would be a
second clock inside a path the contract keeps deterministic.

**Two ages, on purpose.** :data:`AVG_PRICE_REFRESH_S` is how long a cached quote
is reused before another request is made — a cost control over a shared 6000
weight/min IP budget, since the entry and protection cycles poll at 1 s.
:data:`AVG_PRICE_MAX_AGE_S` is the hard bound: past it the value is not a
reference any more and the entry is deferred with its reason, never judged by an
average from another minute. It is the reservation's own 30 s tenure
(PIPELINE.md §8) — a reference older than the whole life of the commitment it
would justify is not "now" by any reading.

A failed request never becomes a fabricated number: the last quote is reused
while it is inside the hard bound, and after that the reader reports **nothing**
and the entry defers (``avg_price_unavailable``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from decimal import Decimal

    from hunter_exchanges.binance_spot.normalize import AvgPrice
    from hunter_risk.inputs import MarketIdentity

__all__ = [
    "AVG_PRICE_MAX_AGE_S",
    "AVG_PRICE_MAX_SKEW_S",
    "AVG_PRICE_REFRESH_S",
    "AVG_PRICE_SOURCE",
    "AvgPriceExchange",
    "AvgPriceQuote",
    "AvgPriceReader",
    "ExchangeAvgPrice",
    "StaticAvgPrice",
]

logger = get_logger(__name__)

AVG_PRICE_SOURCE = "binance_spot_avg_price_v1"
"""The reader's own version, published next to every attempt it feeds."""

AVG_PRICE_REFRESH_S = 5.0
"""How long one quote is reused before another request is made."""

AVG_PRICE_MAX_AGE_S = 30.0
"""How old a quote may be and still judge a filter — the reservation's tenure."""

AVG_PRICE_MAX_SKEW_S = 2.0
"""How far **ahead** of the cycle's ``now`` a stamp may be and still be fresh.

Not a courtesy: it is the ordering the cycle itself creates.
:meth:`hunter_execution_worker.cycles.Cycles.entries` reads ``now`` and *then*
assembles the snapshot, so a quote fetched during that pass is stamped after the
instant the entry is judged against — a negative age of milliseconds on every
cache miss. Refusing it (the pre-T3.29b behaviour) threw away a price the reader
had just received, once per refresh window, and the entry deferred until its
reservation expired.

The tolerance is small on purpose and it is **not** open-ended: past it the
reference is refused as ``avg_price_clock_skew``, which is a different incident
from ``avg_price_stale`` and is counted separately
(``hunter_execution_avg_price_clock_skew_total``). Two seconds is an order of
magnitude below the 30 s hard bound and far above any in-pass scheduling delay,
so it can absorb the race without ever admitting a reference from another minute.
"""


@dataclass(frozen=True, slots=True)
class AvgPriceQuote:
    """One ``avgPrice``, with **our** receipt instant and where it came from."""

    price: Decimal
    mins: int
    observed_at: datetime
    source: str = AVG_PRICE_SOURCE


class AvgPriceExchange(Protocol):
    """The one method this reader needs of an exchange adapter."""

    async def fetch_avg_price(self, symbol: str) -> AvgPrice: ...


class AvgPriceReader(Protocol):
    """Where one cycle's ``avgPrice`` comes from — or ``None``, with a log line."""

    source: str

    async def read(self, market: MarketIdentity) -> AvgPriceQuote | None: ...


class StaticAvgPrice:
    """A **test double**: the quotes handed to it, and nothing else.

    Labelled as a double on purpose (CLAUDE.md). A market it was not given is
    absent, which is exactly what an entry deferring on a missing reference
    needs in order to be provable.
    """

    source = "static_fixture"

    def __init__(self, quotes: dict[tuple[str, str], AvgPriceQuote]) -> None:
        self._quotes = quotes

    async def read(self, market: MarketIdentity) -> AvgPriceQuote | None:
        return self._quotes.get((market.exchange, market.symbol))


class ExchangeAvgPrice:
    """The real reader: ``GET /api/v3/avgPrice``, cached and bounded."""

    source = AVG_PRICE_SOURCE

    def __init__(
        self,
        exchange: AvgPriceExchange,
        *,
        refresh_s: float = AVG_PRICE_REFRESH_S,
        max_age_s: float = AVG_PRICE_MAX_AGE_S,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._exchange = exchange
        self._refresh_s = refresh_s
        self._max_age_s = max_age_s
        self._clock = clock
        self._cache: dict[tuple[str, str], AvgPriceQuote] = {}

    async def read(self, market: MarketIdentity) -> AvgPriceQuote | None:
        """This market's ``avgPrice``, or ``None`` when there is honestly none."""
        key = (market.exchange, market.symbol)
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and 0 <= self._age(cached, now) <= self._refresh_s:
            return cached
        try:
            fresh = await self._exchange.fetch_avg_price(market.symbol)
        except Exception as exc:
            logger.warning("avg_price_fetch_failed", symbol=market.symbol, error=str(exc))
            return self._still_usable(cached, now)
        if fresh.price <= 0:
            # A non-positive average is not a price; it would divide the
            # notional check by something the exchange never quoted.
            logger.warning("avg_price_non_positive", symbol=market.symbol, price=str(fresh.price))
            return self._still_usable(cached, now)
        quote = AvgPriceQuote(price=fresh.price, mins=fresh.mins, observed_at=now)
        self._cache[key] = quote
        return quote

    def _age(self, quote: AvgPriceQuote, now: datetime) -> float:
        return (now - quote.observed_at).total_seconds()

    def _still_usable(self, cached: AvgPriceQuote | None, now: datetime) -> AvgPriceQuote | None:
        """The last quote while it is inside the hard bound — never past it.

        A negative age (a clock that stepped backwards) is treated exactly like
        an expired one: the contract's rule for a timestamp in the future is
        ``unavailable``, not "close enough".
        """
        if cached is None:
            return None
        age = self._age(cached, now)
        return cached if 0 <= age <= self._max_age_s else None
