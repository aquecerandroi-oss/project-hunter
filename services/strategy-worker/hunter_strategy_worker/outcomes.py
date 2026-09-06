"""The outcome engine: advancing open trackings over closed 1-minute bars.

Driven by **Postgres**, not by the stream. The market-worker publishes
``market.candles.closed`` before its persistence batch flushes, so the stream
proves a candle exists, not that it is durable; and a stream cannot replay the
minute an instance missed while it was down. Reading the durable series lets the
engine advance strictly contiguously, which is what makes a restart a no-op and
an unrecoverable hole a *censored* outcome instead of a fabricated one.

Every advance is a read-modify-write under the slot's lock, so the decision loop
and this loop can never interleave on the same tracking, and a finished tracking
is released from its slot in the same transaction that finishes it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.enums import MarketStatus, ShadowTrackingState
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_strategy_worker import slots
from hunter_strategy_worker.gaps import censor_reason, covering_gap
from hunter_strategy_worker.metrics import shadow_outcomes_total
from hunter_strategy_worker.plan import LateReason
from hunter_strategy_worker.repo import MarketRow, load_candles
from hunter_strategy_worker.settle import settle
from hunter_strategy_worker.tracking_repo import OpenTracking, merged_meta, save_tracking
from hunter_strategy_worker.walker import Bar, Progress, TrackingPlan, walk

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.config import ShadowConfig

logger = get_logger(__name__)
MINUTE = timedelta(minutes=1)

__all__ = ["AdvanceResult", "advance_tracking", "last_closed_minute"]


@dataclass(frozen=True, slots=True)
class AdvanceResult:
    """What one advance did."""

    state: ShadowTrackingState
    bars: int
    finished: bool


def last_closed_minute(now: datetime) -> datetime:
    """``open_time`` of the newest 1m bar that has certainly closed."""
    return now.replace(second=0, microsecond=0) - MINUTE


def _contiguous(candles: Sequence[Bar], start: datetime) -> list[Bar]:
    """The prefix of ``candles`` that starts at ``start`` with no hole."""
    expected = start
    prefix: list[Bar] = []
    for candle in candles:
        if candle.open_time != expected:
            break
        prefix.append(candle)
        expected += MINUTE
    return prefix


async def _bars(
    session: AsyncSession, tracking: OpenTracking, *, start: datetime, end: datetime
) -> list[Bar]:
    market = MarketRow(
        id=tracking.market_id,
        symbol=tracking.symbol,
        exchange=tracking.exchange,
        is_monitored=True,
        status=MarketStatus.ACTIVE,
    )
    candles = await load_candles(session, market=market, start=start, end=end + MINUTE)
    return [
        Bar(
            open_time=c.open_time,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
        )
        for c in candles
    ]


async def _finish(
    session: AsyncSession,
    tracking: OpenTracking,
    plan: TrackingPlan,
    progress: Progress,
    meta: dict[str, Any],
) -> None:
    """Persist a finished tracking and release the slot it occupied."""
    exit_price = None
    r_multiple = None
    if progress.tracking_state is ShadowTrackingState.TERMINAL:
        settlement = await settle(
            session, market_id=tracking.market_id, plan=plan, progress=progress
        )
        exit_price, r_multiple = settlement.exit_price, settlement.r_multiple
        meta = merged_meta(meta, **settlement.meta)
    ended_at = progress.exit_ts or utcnow()
    excursions = progress.excursions(plan)
    meta = merged_meta(meta, progress=progress.to_jsonable(), excursions=excursions)
    await save_tracking(
        session,
        tracking.signal_id,
        progress=progress,
        meta=meta,
        exit_price=exit_price,
        r_multiple=r_multiple,
        excursions=excursions,
        tracked_until=ended_at,
    )
    await slots.release_tracking(session, signal_id=tracking.signal_id, ended_at=ended_at)
    shadow_outcomes_total.labels(
        tracking_state=progress.tracking_state.value, result=progress.result.value
    ).inc()


async def _save_open(
    session: AsyncSession,
    tracking: OpenTracking,
    plan: TrackingPlan,
    progress: Progress,
    meta: dict[str, Any],
) -> None:
    excursions = progress.excursions(plan)
    await save_tracking(
        session,
        tracking.signal_id,
        progress=progress,
        meta=merged_meta(meta, progress=progress.to_jsonable(), excursions=excursions),
        exit_price=None,
        r_multiple=None,
        excursions=excursions,
        tracked_until=(
            progress.last_bar_open + MINUTE if progress.last_bar_open is not None else None
        ),
    )


def _gap_wait(meta: dict[str, Any], minute: datetime, now: datetime) -> datetime:
    """When this exact missing minute was first noticed — durable across restarts."""
    recorded: Any = meta.get("gap_wait")
    if not isinstance(recorded, dict):
        return now
    wait: dict[str, Any] = cast("dict[str, Any]", recorded)
    if wait.get("minute") != minute.isoformat():
        return now
    return datetime.fromisoformat(str(wait["since"]))


async def advance_tracking(
    session: AsyncSession,
    tracking: OpenTracking,
    *,
    config: ShadowConfig,
    now: datetime | None = None,
    blocked: frozenset[str] = frozenset(),
) -> AdvanceResult:
    """Advance one tracking as far as the durable candles allow.

    Must be called inside a transaction that already locked the tracking's slot.
    """
    clock = now or utcnow()
    plan, progress, meta = tracking.plan, tracking.progress, dict(tracking.meta)
    if progress.finished:
        return AdvanceResult(progress.tracking_state, 0, True)

    if progress.tracking_state is ShadowTrackingState.PENDING_ENTRY:
        entry_plan = dict(meta.get("entry_plan") or {})
        if not entry_plan.get("confirmed_at"):
            if clock < plan.entry_bar_open:
                return AdvanceResult(progress.tracking_state, 0, False)
            # Durable, but nothing proves it was durable *before* the open it
            # chose: conservative no_entry, never a retroactive entry.
            unconfirmed = Progress(
                tracking_state=ShadowTrackingState.NO_ENTRY,
                result=progress.result,
                no_entry_reason=LateReason.UNCONFIRMED.value,
            )
            await _finish(session, tracking, plan, unconfirmed, meta)
            return AdvanceResult(ShadowTrackingState.NO_ENTRY, 0, True)

    start = progress.next_expected_open(plan)
    limit = min(plan.horizon_open, last_closed_minute(clock))
    if start > limit:
        return AdvanceResult(progress.tracking_state, 0, False)

    candles = await _bars(session, tracking, start=start, end=limit)
    prefix = _contiguous(candles, start)
    advanced = walk(plan, progress, prefix) if prefix else progress
    if advanced.finished:
        meta.pop("gap_wait", None)
        await _finish(session, tracking, plan, advanced, meta)
        return AdvanceResult(advanced.tracking_state, len(prefix), True)

    # Whatever was contiguous has been folded in; if the *next* minute this
    # outcome needs is already due and simply is not there, that is a hole, and
    # a hole is either waited out or censored — never stepped over.
    missing = advanced.next_expected_open(plan)
    if missing <= limit:
        return await _handle_gap(
            session, tracking, plan, advanced, meta, missing, clock, blocked, config
        )
    meta.pop("gap_wait", None)
    await _save_open(session, tracking, plan, advanced, meta)
    return AdvanceResult(advanced.tracking_state, len(prefix), False)


async def _handle_gap(
    session: AsyncSession,
    tracking: OpenTracking,
    plan: TrackingPlan,
    progress: Progress,
    meta: dict[str, Any],
    minute: datetime,
    clock: datetime,
    blocked: frozenset[str],
    config: ShadowConfig,
) -> AdvanceResult:
    """A minute this outcome needs is not there yet.

    The collector's own record decides, not a stopwatch: :mod:`.gaps` reads the
    ``ingestion_gaps`` row covering the minute and says whether waiting is still
    justified (MUST-FIX 2). The verdict becomes the suffix of the censored
    reason, because ``failed``, ``unregistered`` and ``stalled`` are three
    different populations for S3's coverage counts.
    """
    if tracking.symbol in blocked:
        censored = progress.censor(f"blocked:{tracking.symbol}")
        await _finish(session, tracking, plan, censored, meta)
        return AdvanceResult(ShadowTrackingState.CENSORED, 0, True)
    since = _gap_wait(meta, minute, clock)
    gap = await covering_gap(session, market_id=tracking.market_id, minute=minute)
    reason = censor_reason(
        gap,
        waited_s=(clock - since).total_seconds(),
        gap_age_s=None if gap is None else (clock - ensure_utc(gap.detected_at)).total_seconds(),
        config=config,
    )
    if reason is not None:
        censored = progress.censor(f"gap:{minute.isoformat()}:{reason}")
        logger.warning(
            "shadow_outcome_censored",
            signal_id=str(tracking.signal_id),
            minute=minute.isoformat(),
            reason=reason,
        )
        await _finish(session, tracking, plan, censored, meta)
        return AdvanceResult(ShadowTrackingState.CENSORED, 0, True)
    meta = merged_meta(
        meta,
        gap_wait={
            "minute": minute.isoformat(),
            "since": since.isoformat(),
            "gap_status": None if gap is None else gap.status,
        },
    )
    await _save_open(session, tracking, plan, progress, meta)
    return AdvanceResult(progress.tracking_state, 0, False)


def tracking_market(tracking: OpenTracking) -> uuid.UUID:
    return tracking.market_id
