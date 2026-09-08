"""Funding-rate history backfill: one REST call, not a per-minute gap plan.

T3.7c: the replay engine (T3.19b) cannot price a shadow outcome's funding leg
without a settlement history that reaches back past its entry
(``hunter_strategy_worker.funding``, ``_CADENCE_LOOKBACK`` = 3 days), and
``funding_rates`` held only the live-collected period until this lane existed
(notes: two 31-day replays produced 23+2 evaluable outcomes out of 224+341,
the rest ``funding_schedule_unknown``).

**Why this is not the candle lane's ``ingestion_gaps``-plus-recovery machine.**
That design exists to spread thousands of REST calls (one per 4-hour chunk of
minute candles) across many cycles under a shared budget, with retry state
that survives a restart. A funding request needs at most one call:
``BinanceRestClient.fetch_realized_funding`` already paginates internally and
one page covers ~333 days at three settlements a day — the brief's own
sizing. So this lane fetches and persists inline, in the consumer that read
the request, under the funding-history REST bucket that
``hunter_market_worker.funding.poll_realized`` (live polling) already shares
it with -- backfill and live collection are naturally serialized by that one
token bucket, which is what keeps this lane's priority below live work
without any queue of its own.

**Never overwrites a live row.** ``persist_rows.upsert_funding`` inserts with
``ON CONFLICT (market_id, funding_time) DO NOTHING`` regardless of who calls
it — the row that landed first (live or backfill) survives, unconditionally.
Table has no ``source``/``received_at`` column to distinguish the two after
the fact (``docs/DATABASE.md`` §2); that is a schema question for the
database-architect, not something this lane can create de novo, and it isn't
needed for the idempotency and precedence guarantees above.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from prometheus_client import Counter

from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.domain.market import to_wire
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.observability import registry
from hunter_exchanges.base import RateLimited
from hunter_market_worker import backfill_request as requests
from hunter_market_worker.backfill_outcome import Outcome
from hunter_market_worker.funding_announce import enqueue_funding_backfilled
from hunter_market_worker.heartbeat_events import safe_record_system_event
from hunter_market_worker.persist_rows import upsert_funding
from hunter_market_worker.queues import RealizedFunding
from hunter_market_worker.recovery import server_now

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_market_worker.universe import MonitoredUniverse

logger = get_logger(__name__)

__all__ = ["MAX_FUNDING_REQUEST_DAYS", "Refused", "Window", "normalize_window", "serve"]

MAX_FUNDING_REQUEST_DAYS = 370
"""Comfortably above the ~333 days one Binance settlement page covers
(``BinanceRestClient.fetch_realized_funding``), so an in-bounds request is
always the single call the module docstring promises. A wider request is
truncated to its most recent days, mirroring the candle lane's policy
(``backfill_plan.MAX_REQUEST_MINUTES``): the recent end is what a replay's
cadence lookback needs first."""

market_funding_backfill_settlements_total = Counter(
    "market_funding_backfill_settlements_total",
    "Funding settlements newly inserted by a kind=funding backfill request.",
    registry=registry,
)


class Refused(Exception):
    """This funding request will not be served, and the reason is not transient."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Window:
    """The ``[start, end)`` span this lane accepted from one request."""

    start: datetime
    end: datetime
    truncated: bool


def normalize_window(gap_start: datetime, gap_end: datetime, *, now: datetime) -> Window:
    """Half-open ``[gap_start, gap_end)`` -> the span fetched, clamped to ``now``.

    No per-minute alignment (funding settles every few hours, not every
    minute) and no partition check (``funding_rates`` is not partitioned,
    ``docs/DATABASE.md`` line 127) -- the two concerns that make the candle
    window's arithmetic (``backfill_plan.normalize_window``) far larger than
    this one.
    """
    try:
        start, end = ensure_utc(gap_start), ensure_utc(gap_end)
    except ValueError as exc:
        raise Refused("naive_timestamp") from exc
    if start >= now:
        raise Refused("future_window")
    end = min(end, now)
    if end <= start:
        raise Refused("empty_window")
    truncated = False
    ceiling = timedelta(days=MAX_FUNDING_REQUEST_DAYS)
    if end - start > ceiling:
        start = end - ceiling
        truncated = True
    return Window(start=start, end=end, truncated=truncated)


def _refuse(reason: str, request: requests.Request, event_id: str) -> Outcome:
    logger.warning(
        "market_backfill_refused",
        reason=reason,
        symbol=request.symbol,
        event_id=event_id,
        exchange=request.exchange,
        kind="funding",
    )
    return Outcome("refused", reason)


async def serve(
    request: requests.Request,
    *,
    adapter: Any,
    universe: MonitoredUniverse,
    session_factory: async_sessionmaker[AsyncSession],
    event_id: str,
    now: datetime | None,
) -> Outcome:
    """Fetch and persist one ``kind: funding`` request's window, in full, now."""
    if request.symbol not in set(universe.symbols):
        return _refuse("market_not_monitored", request, event_id)
    fetch = getattr(adapter, "fetch_realized_funding", None)
    if not callable(fetch):
        return _refuse("funding_unsupported", request, event_id)
    moment = now if now is not None else await server_now(adapter)
    try:
        window = normalize_window(request.gap_start, request.gap_end, now=moment)
    except Refused as exc:
        return _refuse(exc.reason, request, event_id)

    try:
        records: list[Any] = await adapter.fetch_realized_funding(
            request.symbol, window.start, window.end
        )
    except RateLimited as exc:
        logger.warning(
            "market_funding_backfill_rate_limited",
            symbol=request.symbol,
            exchange=request.exchange,
            retry_after_s=exc.retry_after_s,
        )
        await safe_record_system_event(
            session_factory,
            "funding_backfill_rate_limited",
            f"funding history for {request.exchange}:{request.symbol} refused: {exc}",
            RiskEventSeverity.WARNING,
        )
        return _refuse("rate_limited", request, event_id)

    matching = [
        record
        for record in records
        if record.symbol == request.symbol
        and record.exchange == adapter.code
        and window.start <= record.ts < window.end
    ]
    realized = [RealizedFunding.model_validate(to_wire(record)) for record in matching]

    async with role_session(session_factory, db_role="hunter_worker") as session:
        market_id = await requests.market_id_for(session, request)
        if market_id is None:
            return _refuse("unknown_market", request, event_id)
        inserted = await upsert_funding(session, realized, {request.symbol: market_id})
        await enqueue_funding_backfilled(
            session,
            exchange=request.exchange,
            symbol=request.symbol,
            start=window.start,
            end=window.end,
            count=len(matching),
            reason=request.reason,
        )
    if inserted:
        market_funding_backfill_settlements_total.inc(inserted)
    logger.info(
        "market_funding_backfill_served",
        exchange=request.exchange,
        symbol=request.symbol,
        event_id=event_id,
        gap_start=window.start.isoformat(),
        gap_end=window.end.isoformat(),
        fetched=len(records),
        matched=len(matching),
        inserted=inserted,
        truncated=window.truncated,
    )
    return Outcome(
        "truncated" if window.truncated else ("accepted" if matching else "empty"),
        reason=request.reason,
        final=True,
    )
