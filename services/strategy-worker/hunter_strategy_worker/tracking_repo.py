"""Reading and writing the trackings the outcome engine owns.

The strategy-worker is the **single writer** of ``signal_outcomes`` for the
Shadow Lab (SHADOW-LAB.md §10); a future transfer to the analytics worker is
recorded in ``docs/PIPELINE.md`` and would move this module, not duplicate it.

The tracking plan is rebuilt from the *stored* values — ``virtual_stop``,
``virtual_targets`` and ``meta`` — never from the strategy code or from memory.
That is what makes "the level used after a restart is the level that was
written" true: the columns are ``NUMERIC(28,10)`` and the levels were put at
that scale before the insert (:mod:`.levels`).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update

from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import ShadowTrackingState, Timeframe
from hunter_core.domain.types import to_money
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.walker import Progress, TrackingPlan

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_OPEN_STATES = (ShadowTrackingState.PENDING_ENTRY, ShadowTrackingState.ACTIVE)


def _jsonable(value: Any) -> Any:
    """``meta`` in the canonical ``params_format = 1`` shape.

    JSONB cannot take a ``Decimal`` and must never take a float, so every number
    is written as its normalised decimal string and every timestamp as ISO-8601
    ``Z`` — the same spelling the envelope uses, so a value read back is the
    value written.
    """
    parsed: Any = json.loads(canonical_json(value))
    return parsed


SWEEP_LIMIT = 500
"""How many open trackings one sweep may advance.

A bound is required — an unbounded sweep would hold one session open across
however many trackings exist, and every one of them takes its own locking
transaction. 500 covers the Lab's own ceiling by a wide margin (two versions ×
one open tracking per market × the monitored universe), so in normal operation
the limit is never reached.

It is not silent, though: rows past it simply do not advance that pass, which
would look exactly like a quiet market. :func:`count_open_trackings` reports the
true total and ``hunter_shadow_trackings_unswept`` publishes the difference.
"""

__all__ = [
    "SWEEP_LIMIT",
    "OpenTracking",
    "count_open_trackings",
    "load_open_trackings",
    "load_tracking",
    "save_tracking",
]


@dataclass(frozen=True, slots=True)
class OpenTracking:
    """One ``pending_entry``/``active`` outcome with everything to advance it."""

    signal_id: uuid.UUID
    strategy_version_id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    tracking_state: ShadowTrackingState
    virtual_stop: Decimal
    virtual_targets: list[Any]
    meta: dict[str, Any]

    @property
    def progress(self) -> Progress:
        return Progress.from_jsonable(self.meta["progress"])

    @property
    def plan(self) -> TrackingPlan:
        meta = self.meta
        invalidation: dict[str, Any] = meta.get("invalidation") or {}
        costs = AssumedCosts.model_validate(meta["assumed_costs"])
        entry_plan = meta["entry_plan"]
        return TrackingPlan(
            entry_bar_open=datetime.fromisoformat(entry_plan["entry_bar_open"]),
            stop=self.virtual_stop,
            target1=to_money(self.virtual_targets[0]),
            horizon_s=int(meta["horizon_s"]),
            costs=costs,
            reference_price=(
                None if meta.get("reference_price") is None else to_money(meta["reference_price"])
            ),
            invalidation_level=(None if not invalidation else to_money(invalidation["level"])),
            invalidation_timeframe=(
                None if not invalidation else Timeframe(invalidation["timeframe"])
            ),
        )


_COLUMNS = (
    SignalOutcome.signal_id,
    SignalOutcome.tracking_state,
    SignalOutcome.virtual_stop,
    SignalOutcome.virtual_targets,
    SignalOutcome.meta,
    AgentSignal.strategy_version_id,
    AgentSignal.market_id,
    Market.symbol,
    Exchange.code,
)


def _row_to_tracking(row: Any) -> OpenTracking:
    return OpenTracking(
        signal_id=row.signal_id,
        strategy_version_id=row.strategy_version_id,
        market_id=row.market_id,
        exchange=row.code,
        symbol=row.symbol,
        tracking_state=row.tracking_state,
        virtual_stop=row.virtual_stop,
        virtual_targets=list(row.virtual_targets or []),
        meta=dict(row.meta or {}),
    )


def _base_query() -> Any:
    return (
        select(*_COLUMNS)
        .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
        .join(Market, Market.id == AgentSignal.market_id)
        .join(Exchange, Exchange.id == Market.exchange_id)
    )


async def load_open_trackings(
    session: AsyncSession, *, limit: int = SWEEP_LIMIT, market_id: uuid.UUID | None = None
) -> list[OpenTracking]:
    """At most ``limit`` trackings waiting for an entry or in the hypothetical
    market, oldest signal first.

    Ordered by ``signal_id`` (a ``uuid5``, so effectively arbitrary but stable):
    a stable order means a backlog is worked through deterministically instead
    of a random half being starved every pass.
    """
    query = _base_query().where(SignalOutcome.tracking_state.in_(_OPEN_STATES))
    if market_id is not None:
        query = query.where(AgentSignal.market_id == market_id)
    rows = (await session.execute(query.order_by(SignalOutcome.signal_id).limit(limit))).all()
    return [_row_to_tracking(row) for row in rows]


async def count_open_trackings(session: AsyncSession) -> int:
    """How many trackings are open in total, limit or no limit."""
    total = await session.scalar(
        select(func.count())
        .select_from(SignalOutcome)
        .where(SignalOutcome.tracking_state.in_(_OPEN_STATES))
    )
    return int(total or 0)


async def load_tracking(session: AsyncSession, signal_id: uuid.UUID) -> OpenTracking | None:
    """One tracking by signal id, in any state (``None`` if there is no outcome)."""
    row = (await session.execute(_base_query().where(SignalOutcome.signal_id == signal_id))).first()
    return None if row is None else _row_to_tracking(row)


async def save_tracking(
    session: AsyncSession,
    signal_id: uuid.UUID,
    *,
    progress: Progress,
    meta: dict[str, Any],
    exit_price: Decimal | None,
    r_multiple: Decimal | None,
    excursions: dict[str, Any],
    tracked_until: datetime | None,
) -> None:
    """Persist one advance. The row is matched on its *open* states only.

    ``terminal``, ``no_entry`` and ``censored`` never reopen (SHADOW-LAB.md §4),
    so the ``WHERE`` clause — not a Python check — is what guarantees a late
    duplicate worker cannot resurrect a finished tracking.
    """
    await session.execute(
        update(SignalOutcome)
        .where(
            SignalOutcome.signal_id == signal_id,
            SignalOutcome.tracking_state.in_(_OPEN_STATES),
        )
        .values(
            tracking_state=progress.tracking_state,
            result=progress.result,
            no_entry_reason=progress.no_entry_reason,
            censored_reason=progress.censored_reason,
            virtual_entry=progress.entry,
            entry_ts=progress.entry_ts,
            exit_price=exit_price,
            exit_ts=progress.exit_ts,
            r_multiple=r_multiple,
            mfe=excursions.get("mfe"),
            mae=excursions.get("mae"),
            mfe_ts=excursions.get("mfe_ts"),
            mae_ts=excursions.get("mae_ts"),
            tracked_until=tracked_until,
            meta=_jsonable(meta),
        )
    )


def merged_meta(meta: dict[str, Any], **updates: Any) -> dict[str, Any]:
    """``meta`` with ``updates`` applied — the envelope is elsewhere and untouched."""
    merged = dict(meta)
    merged.update(updates)
    return merged
