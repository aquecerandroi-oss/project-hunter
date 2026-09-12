"""``--kind funding`` for ``request_backfill.py`` (T3.7c) — split out to keep
that script under the 350-line budget. Imported by it, never the reverse.

The replay engine cannot price a shadow outcome's funding leg without
settlement history reaching back past its entry
(``hunter_strategy_worker.funding``, 3-day cadence lookback), and
``funding_rates`` held only the live-collected period. Unlike candles, one
Binance settlement page covers ~333 days at three fundings a day
(``BinanceRestClient.fetch_realized_funding``), so this publishes **one**
request per market instead of slicing into seven-day windows, and the
event's identity folds in the literal ``"funding"`` so it can never collide
with a candles request naming the same market and window.
``funding_rates`` is not partitioned (``docs/DATABASE.md`` line 127), so
there is no partition check here, unlike the candle path.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from hunter_core.events.outbox import build_envelope, event_id_for
from hunter_core.events.streams import Streams

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_core.events.envelope import EventEnvelope

__all__ = ["MAX_REQUEST_DAYS", "REASON", "envelope_for", "envelopes_for", "window_for"]

MAX_REQUEST_DAYS = 370
"""The funding lane's own ceiling (``funding_backfill.MAX_FUNDING_REQUEST_DAYS``),
duplicated for the same reason ``request_backfill.MAX_REQUEST_MINUTES`` is:
this is the published contract, and the collector still truncates safely if
the two ever diverge."""

REASON = "funding_history"


def window_for(now: datetime, days: int) -> tuple[datetime, datetime]:
    """``[start, end)``: ``days`` back, clamped to the request ceiling.

    No anchor bar (funding settles every few hours, not every minute) and no
    settled-grace clamp: the collector's own ``funding_backfill.normalize_window``
    already clamps ``end`` to its own ``now`` the instant the request is served.
    """
    end = now.replace(second=0, microsecond=0)
    start = end - timedelta(days=days)
    ceiling = end - timedelta(days=MAX_REQUEST_DAYS)
    return max(start, ceiling), end


def envelope_for(
    market_id: UUID,
    symbol: str,
    exchange: str,
    start: datetime,
    end: datetime,
    *,
    producer: str,
    reason: str = REASON,
) -> EventEnvelope:
    """One market's funding-history request: one request covers the whole span."""
    payload: dict[str, Any] = {
        "market_id": str(market_id),
        "exchange": exchange,
        "symbol": symbol,
        "kind": "funding",
        "gap_start": start.isoformat(),
        "gap_end": end.isoformat(),
        "reason": reason,
        "requested_by": producer,
    }
    return build_envelope(
        Streams.MARKET_BACKFILL_REQUESTED,
        event_id_for(Streams.MARKET_BACKFILL_REQUESTED, market_id, "funding", start, end),
        payload,
        producer=producer,
        key=f"{exchange}:{symbol}",
    )


def envelopes_for(chunks: Sequence[Any], exchange: str, *, producer: str) -> list[EventEnvelope]:
    """One envelope per chunk. ``chunks`` duck-types ``request_backfill.Chunk``
    (``.target.market_id``, ``.target.symbol``, ``.gap_start``, ``.gap_end``) --
    not imported by name, or this module would import the one that imports it."""
    return [
        envelope_for(
            chunk.target.market_id,
            chunk.target.symbol,
            exchange,
            chunk.gap_start,
            chunk.gap_end,
            producer=producer,
        )
        for chunk in chunks
    ]
