"""Durable reads. The scanner writes in batches (``persist.py``) and reads here.

Everything in this module answers one of two questions: *what does an engine
need that the hot state does not carry* (derivative history, persisted candles),
or *what did the last process leave behind* (open anomalies, open episodes, the
open regime). Nothing here calls an exchange -- the scanner is not a REST client,
by contract (``docs/plans/M2.md``, section "REST").
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import and_, or_, select

from hunter_core.db.models.analysis import Anomaly, MarketRegimeRow, Opportunity
from hunter_core.db.models.market_data import Candle, OpenInterestHistory
from hunter_core.domain.enums import (
    AnomalyStatus,
    AnomalyType,
    RegimeScope,
    Timeframe,
)
from hunter_core.domain.market import NormalizedCandle
from hunter_core.domain.types import ensure_utc
from hunter_indicators.anomalies import AnomalyDirection, AnomalyState
from hunter_indicators.features import DerivObservation
from hunter_indicators.opportunity import EpisodeState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "OpenEpisode",
    "load_candles",
    "load_deriv_history",
    "load_open_anomalies",
    "load_open_episodes",
    "load_open_regime",
    "optional_ts",
]

_MINUTE = Timeframe.M1
_MINUTE_SPAN = timedelta(minutes=1)


def _id_list(value: Any) -> list[Any]:
    """The stored ``baseline_ids``, as a list of whatever JSONB gave back."""
    if not isinstance(value, list):
        return []
    return [item for item in cast("list[Any]", value)]


def optional_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    return ensure_utc(datetime.fromisoformat(str(value)))


async def load_deriv_history(
    session: AsyncSession, market_id: UUID, *, since: datetime
) -> list[DerivObservation]:
    """Past open-interest readings, oldest first.

    Without this the ``open_interest_change_*`` features are ``missing_input``
    forever: the ``deriv`` hash holds only the current value, and "change since
    the first value this process saw" would be a statement about the process
    (notes-T2.2 section 8). Funding is deliberately not joined in here --
    ``funding_rates`` records a *settlement*, not a sampled reading, and pairing
    the two series on one timestamp would invent readings that never existed.
    """
    statement = (
        select(OpenInterestHistory.ts, OpenInterestHistory.open_interest)
        .where(OpenInterestHistory.market_id == market_id, OpenInterestHistory.ts >= since)
        .order_by(OpenInterestHistory.ts)
    )
    rows = (await session.execute(statement)).all()
    return [DerivObservation(ts=ensure_utc(row[0]), open_interest=row[1]) for row in rows]


def _candle(row: Any, exchange: str, symbol: str) -> NormalizedCandle:
    open_time = ensure_utc(row.open_time)
    return NormalizedCandle(
        exchange=exchange,
        symbol=symbol,
        timeframe=_MINUTE,
        open_time=open_time,
        close_time=open_time + _MINUTE_SPAN,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        quote_volume=row.quote_volume,
        trade_count=row.trade_count,
        taker_buy_volume=row.taker_buy_volume,
        is_final=True,
        event_ts=None,
    )


async def load_candles(
    session: AsyncSession,
    market_id: UUID,
    *,
    exchange: str,
    symbol: str,
    since: datetime,
    until: datetime | None = None,
) -> list[NormalizedCandle]:
    """Persisted **final** 1-minute candles in the window, oldest first."""
    conditions = [
        Candle.market_id == market_id,
        Candle.timeframe == _MINUTE,
        Candle.is_final.is_(True),
        Candle.open_time >= since,
    ]
    if until is not None:
        conditions.append(Candle.open_time <= until)
    statement = select(Candle).where(and_(*conditions)).order_by(Candle.open_time)
    rows = (await session.execute(statement)).scalars().all()
    return [_candle(row, exchange, symbol) for row in rows]


def _anomaly_state(row: Anomaly) -> AnomalyState:
    """Rebuild the lifecycle state of one row.

    The columns are the truth the API reads; the ``metadata`` block carries the
    handful of fields the table has no column for (the proven-calm counters, the
    direction, the baseline ids). Both are written in the same statement, so a
    row cannot describe one state and its metadata another.
    """
    wire: dict[str, Any] = dict(row.meta.get("state") or {})
    observed = optional_ts(wire.get("observation_ts")) or ensure_utc(row.detected_at)
    return AnomalyState(
        market_id=row.market_id,
        type=row.type,
        status=row.status,
        evaluation_state=row.evaluation_state,
        detected_at=ensure_utc(row.detected_at),
        observation_ts=observed,
        severity=row.severity,
        confidence=row.confidence,
        baseline=row.baseline,
        current_value=row.current_value,
        deviation=row.deviation,
        direction=AnomalyDirection(wire.get("direction") or AnomalyDirection.FLAT.value),
        unit=row.unit,
        detector_version=row.detector_version,
        normalization_version=wire.get("normalization_version"),
        baseline_ids=tuple(UUID(str(item)) for item in _id_list(wire.get("baseline_ids"))),
        below_hold_since=optional_ts(wire.get("below_hold_since")),
        below_hold_readings=int(wire.get("below_hold_readings") or 0),
        resolved_at=ensure_utc(row.resolved_at) if row.resolved_at else None,
        reason=wire.get("reason"),
    )


async def load_open_anomalies(
    session: AsyncSession, market_ids: Sequence[UUID], *, since: datetime
) -> dict[UUID, dict[AnomalyType, tuple[UUID, AnomalyState]]]:
    """Active anomalies **and** recently closed ones.

    The closed ones matter: ``lifecycle.advance`` refuses an evaluation older
    than the state it holds, for any state -- so a process that reloaded only the
    active rows would let a redelivered evaluation from before the resolution
    reopen an anomaly that is over (Astra, T2.5 design review).
    """
    if not market_ids:
        return {}
    statement = select(Anomaly).where(
        Anomaly.market_id.in_(list(market_ids)),
        or_(Anomaly.status == AnomalyStatus.ACTIVE, Anomaly.detected_at >= since),
    )
    rows = (await session.execute(statement)).scalars().all()
    states: dict[UUID, dict[AnomalyType, tuple[UUID, AnomalyState]]] = {}
    for row in rows:
        state = _anomaly_state(row)
        bucket = states.setdefault(row.market_id, {})
        current = bucket.get(row.type)
        # One active row per (market, type) is a database invariant; among the
        # closed ones the newest observation is the one whose ordering guard
        # counts. The row id travels with the state so an update targets the row
        # the episode belongs to instead of inserting a second one.
        if current is None or state.observation_ts > current[1].observation_ts:
            bucket[row.type] = (row.id, state)
    return states


class OpenEpisode:
    """One open opportunity row, rehydrated."""

    __slots__ = ("episode", "history_wire", "market_id", "opportunity_id")

    def __init__(
        self,
        opportunity_id: UUID,
        market_id: UUID,
        episode: EpisodeState,
        history_wire: dict[str, Any],
    ) -> None:
        self.opportunity_id = opportunity_id
        self.market_id = market_id
        self.episode = episode
        self.history_wire = history_wire


async def load_open_episodes(
    session: AsyncSession, market_ids: Sequence[UUID]
) -> dict[UUID, OpenEpisode]:
    """Open episodes by market, rebuilt from the envelope they stored.

    ``feature_snapshot["state_out"]["status"]`` is where ``opportunity_envelope``
    puts the episode state, and ``EpisodeState.from_wire`` is its inverse. The
    columns alone would not do: ``below_floor_readings`` -- the count that proves
    the fifteen minutes were actually observed -- has no column.
    """
    if not market_ids:
        return {}
    statement = select(Opportunity).where(
        Opportunity.market_id.in_(list(market_ids)), Opportunity.expired_at.is_(None)
    )
    rows = (await session.execute(statement)).scalars().all()
    episodes: dict[UUID, OpenEpisode] = {}
    for row in rows:
        snapshot: dict[str, Any] = dict(row.feature_snapshot or {})
        state_out: dict[str, Any] = dict(snapshot.get("state_out") or {})
        wire: dict[str, Any] = dict(state_out.get("status") or {})
        episode = (
            EpisodeState.from_wire(wire)
            if wire
            else EpisodeState(
                status=row.status,
                first_seen_at=ensure_utc(row.first_seen_at),
                observation_ts=ensure_utc(row.last_updated_at),
                score=row.score,
                peak_score=row.peak_score if row.peak_score is not None else row.score,
                stage=row.stage,
                direction=row.direction,
                confidence=row.confidence,
                below_floor_since=optional_ts(row.below_40_since),
            )
        )
        episodes[row.market_id] = OpenEpisode(
            opportunity_id=row.id,
            market_id=row.market_id,
            episode=episode,
            history_wire=dict(snapshot.get("history_mark") or {}),
        )
    return episodes


async def load_open_regime(
    session: AsyncSession, scope: RegimeScope = RegimeScope.GLOBAL
) -> tuple[UUID, dict[str, Any]] | None:
    """The regime row in force and the classifier state it stored, if any."""
    statement = select(MarketRegimeRow).where(
        MarketRegimeRow.scope == scope, MarketRegimeRow.end_time.is_(None)
    )
    row = (await session.execute(statement)).scalars().first()
    if row is None:
        return None
    return (row.id, dict(row.supporting_features or {}))
