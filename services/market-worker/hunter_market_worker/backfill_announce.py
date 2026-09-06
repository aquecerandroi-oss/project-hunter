"""Aggregated announcement of one history-tier REST recovery (T2.9c).

Split out of ``durable.py`` along a real seam: everything there announces one
*minute* per event, mirroring the row it was derived from one-to-one; this
module announces one *chunk* — the whole batch a single history-tier gap
recovery actually inserted — because the market-worker's two-tier recovery
(``recovery.py``, PIPELINE.md §1b item 7) already tells "live collection"
apart from "history" by the age of the gap's window, and publishing history
one minute at a time was measured queuing up to 1,440 events/cycle ahead of
live candles in the dispatcher's ``(created_at, id)`` order (notes-T2.5.md
§28, §31; notes-T2.9.md T2.9c). ``market.candles.closed`` keeps announcing
every live-tier minute individually — this module changes nothing about that
path.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from hunter_core.events.outbox import build_envelope, enqueue_many, event_id_for
from hunter_core.events.streams import Streams
from hunter_market_worker.durable import PRODUCER

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.market import NormalizedCandle

_MINUTE = timedelta(minutes=1)

__all__ = ["candles_backfilled_event_id", "enqueue_candles_backfilled"]


def _key(exchange: str, symbol: str) -> str:
    return f"{exchange}:{symbol}"


def candles_backfilled_event_id(
    exchange: str, symbol: str, timeframe: str, start: datetime, end: datetime
) -> UUID:
    """Identity of one aggregated ``market.candles.backfilled`` announcement.

    Market + timeframe + the exact ``[start, end)`` span of *this*
    transaction's insertion, plus the literal ``"rest"`` — every producer of
    this stream is REST history recovery, so ``source`` is folded in as a
    constant rather than a caller-supplied string that could drift from what
    the stream actually carries.

    Deliberately over the span **this call actually inserted**, not the gap's
    own nominal ``[gap_start, gap_end]``: two committed batches for the same
    ``(market, timeframe)`` can never share a minimum, because
    ``persist_rows.upsert_candles``'s ``ON CONFLICT DO NOTHING`` never lets
    the same minute be inserted twice — their spans are disjoint by
    construction. Hashing the gap's nominal bounds instead would give a
    second pass over the same still-open gap the same identity as the first,
    and its newly recovered minutes would be silently dropped by the outbox's
    own conflict guard instead of being announced (Astra, T2.9c review).
    """
    return event_id_for(
        Streams.MARKET_CANDLES_BACKFILLED, exchange, symbol, timeframe, "rest", start, end
    )


async def enqueue_candles_backfilled(
    session: AsyncSession,
    candles: list[NormalizedCandle],
    *,
    reason: str,
    producer: str = PRODUCER,
) -> None:
    """Queue one aggregated ``market.candles.backfilled`` for the candles one
    history-tier gap recovery actually inserted, in this transaction.

    ``candles`` is the whole batch of one recovery unit and is assumed to
    share one ``(exchange, symbol, timeframe)`` — the caller is one gap's
    recovery, which is one market. Empty input is a no-op: an attempt that
    inserted nothing new (every minute already existed) has nothing to
    announce, and an event with ``count=0`` would describe an insertion that
    never happened.

    ``reason`` is a description of *why this is history*, never a claim about
    who asked for it: ``ingestion_gaps`` carries no origin, and a gap the live
    tier itself created can age into history without any
    ``market.backfill.requested`` ever existing
    (``recovery_queries.pending_gaps`` docstring; notes-T2.9.md T2.9c).
    Callers pass the fixed ``"historical_recovery"``.
    """
    if not candles:
        return
    exchange = candles[0].exchange
    symbol = candles[0].symbol
    timeframe = candles[0].timeframe.value
    start = min(c.open_time for c in candles)
    end = max(c.open_time for c in candles) + _MINUTE
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": timeframe,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "count": len(candles),
        "source": "rest",
        "reason": reason,
    }
    await enqueue_many(
        session,
        [
            build_envelope(
                Streams.MARKET_CANDLES_BACKFILLED,
                candles_backfilled_event_id(exchange, symbol, timeframe, start, end),
                payload,
                producer=producer,
                key=_key(exchange, symbol),
            )
        ],
    )
