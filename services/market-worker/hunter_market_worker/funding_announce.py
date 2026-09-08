"""Completion announcement for one funding-history backfill request (T3.7c).

Mirrors ``backfill_announce.py``'s aggregate-per-batch shape, but the batch
here is never large enough to need it for throughput: one Binance settlement
page covers ~333 days at three fundings a day (``BinanceRestClient.
fetch_realized_funding``), so one request is one REST call and at most a few
hundred rows -- nowhere near the 1,440-events/cycle problem T2.9c solved for
candles. This event exists for a different reason: ``market.derivatives``
already announces every inserted settlement individually (``persist_rows.
upsert_funding`` -> ``durable.enqueue_realized_funding``, unchanged by this
module), but nothing on that stream says "this window is now covered" --
which is the fact a future consumer (or an operator reading the outbox) needs
to know a backfill request finished, as opposed to watching settlements
trickle in one at a time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from hunter_core.events.outbox import build_envelope, enqueue_many, event_id_for
from hunter_core.events.streams import Streams
from hunter_market_worker.durable import PRODUCER

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["enqueue_funding_backfilled", "funding_backfilled_event_id"]


def funding_backfilled_event_id(
    exchange: str, symbol: str, start: datetime, end: datetime
) -> UUID:
    """Identity of one funding-backfill completion announcement.

    Hashed over the **requested** window, not the rows actually inserted:
    unlike candles (whose ``ON CONFLICT DO NOTHING`` makes every recovered
    span disjoint by construction, T2.9c), a funding backfill that finds
    nothing new (every settlement already realized-live) still completed the
    request and that is worth saying once per window, not zero times.
    """
    return event_id_for(Streams.MARKET_FUNDING_BACKFILLED, exchange, symbol, start, end)


async def enqueue_funding_backfilled(
    session: AsyncSession,
    *,
    exchange: str,
    symbol: str,
    start: datetime,
    end: datetime,
    count: int,
    reason: str,
    producer: str = PRODUCER,
) -> None:
    """Queue one ``market.funding.backfilled`` for a served ``kind: funding`` request."""
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "count": count,
        "source": "rest",
        "reason": reason,
    }
    await enqueue_many(
        session,
        [
            build_envelope(
                Streams.MARKET_FUNDING_BACKFILLED,
                funding_backfilled_event_id(exchange, symbol, start, end),
                payload,
                producer=producer,
                key=f"{exchange}:{symbol}",
            )
        ],
    )
