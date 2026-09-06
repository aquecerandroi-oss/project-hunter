"""Asking the market-worker for history. The scanner never calls an exchange.

The joint M2 decision is explicit: REST belongs to the market-worker, which owns
the rate limit, the gap table and the recovery loop
(``docs/plans/M2.md``, section "REST"). When the scanner finds that the persisted
candles do not reach far enough back for a baseline bootstrap or for the regime's
thirty-day reference, it does **not** fetch them -- it publishes
``market.backfill.requested`` and keeps running with the history it has, saying
what is missing.

The request is deliberately a *fact about a window*, not a command: it carries
the market, the timeframe and the interval, the identity is deterministic
(``market + interval``), and the market-worker turns it into an
``ingestion_gaps`` row that its existing recovery loop drains. Two scanners, or
one scanner asking twice, produce one gap.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.outbox import event_id_for
from hunter_core.events.produce import publish
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.logging import get_logger
from hunter_scanner_worker.metrics import scanner_backfill_requests_total

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    import redis.asyncio as redis_asyncio

    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

MIN_REQUEST_SPAN = timedelta(minutes=1)
"""A window narrower than one minute names no candle at all.

There used to be a five-minute floor here, and it was wrong twice. It refused the
gaps that hurt most — one missing minute costs ``relative_volume_1h`` a whole day
of observations, so "too small to bother with" is not a property of the hole's
length (Astra, T2.5b design review, must-fix 4) — and it measured the span with an
inclusive end, so the five missing minutes 10:00..10:04 spanned four and were
rejected. The interval is now **half-open**, ``[gap_start, gap_end)``, which is how
missing minutes are actually counted, and "this is just the minute still being
collected" is decided by the caller against the clock, not by a length."""

REQUEST_TTL_S = 3600.0
"""How long the same window is not asked for again. The market-worker's recovery
loop is bounded per cycle, so re-asking every minute would only grow a queue."""

__all__ = ["MIN_REQUEST_SPAN", "BackfillRequester", "request_gaps"]


class BackfillRequester:
    """Publishes candle backfill requests, de-duplicated per window."""

    def __init__(self, producer: str) -> None:
        self.producer = producer
        self._asked: dict[tuple[UUID, datetime, datetime], datetime] = {}

    def _recent(self, key: tuple[UUID, datetime, datetime], now: datetime) -> bool:
        asked_at = self._asked.get(key)
        return asked_at is not None and (now - asked_at).total_seconds() < REQUEST_TTL_S

    async def request(
        self,
        redis: redis_asyncio.Redis,
        *,
        market_id: UUID,
        exchange: str,
        symbol: str,
        gap_start: datetime,
        gap_end: datetime,
        reason: str,
        now: datetime | None = None,
    ) -> bool:
        """Ask for ``[gap_start, gap_end)``. ``False`` = empty, or asked recently."""
        moment = now or utcnow()
        if gap_end - gap_start < MIN_REQUEST_SPAN:
            return False
        key = (market_id, gap_start, gap_end)
        if self._recent(key, moment):
            return False
        payload = {
            "market_id": str(market_id),
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": Timeframe.M1.value,
            "gap_start": gap_start.isoformat(),
            "gap_end": gap_end.isoformat(),
            "reason": reason,
            "requested_by": self.producer,
        }
        envelope = EventEnvelope(
            event_id=event_id_for(Streams.MARKET_BACKFILL_REQUESTED, market_id, gap_start, gap_end),
            type=Streams.MARKET_BACKFILL_REQUESTED,
            producer=self.producer,
            key=f"{exchange}:{symbol}",
            payload=payload,
        )
        await publish(
            redis,
            Streams.MARKET_BACKFILL_REQUESTED,
            envelope,
            DEFAULT_MAXLEN[Streams.MARKET_BACKFILL_REQUESTED],
        )
        self._asked[key] = moment
        scanner_backfill_requests_total.inc()
        logger.info(
            "scanner_backfill_requested",
            symbol=symbol,
            reason=reason,
            gap_start=gap_start.isoformat(),
            gap_end=gap_end.isoformat(),
        )
        return True

    def forget(self, before: datetime) -> None:
        """Drop the de-duplication memory of windows asked long ago."""
        self._asked = {key: asked_at for key, asked_at in self._asked.items() if asked_at >= before}


async def request_gaps(
    redis: redis_asyncio.Redis,
    requester: BackfillRequester,
    ref: MarketRef,
    gaps: Sequence[tuple[datetime, datetime]],
    *,
    reason: str,
    now: datetime | None = None,
) -> int:
    """Ask for every hole found in one market's history. Returns how many were asked.

    Takes the intervals rather than the job that found them: this module knows
    how to ask for candles and nothing about replays, and the caller is free to
    be the bootstrap, the regime's thirty-day reference or anything else that
    discovers a hole.
    """
    asked = 0
    for gap_start, gap_end in gaps:
        if await requester.request(
            redis,
            market_id=ref.market_id,
            exchange=ref.exchange,
            symbol=ref.symbol,
            gap_start=gap_start,
            gap_end=gap_end,
            reason=reason,
            now=now,
        ):
            asked += 1
    return asked
