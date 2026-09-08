"""Replaying one version over persisted candles — the same code the live lane runs.

T3.19b. The engine's whole design is a refusal: **there is no second evaluation
path here.** One replayed bar is one call to
:func:`hunter_strategy_worker.decide.evaluate_slot` — the same function
``consumer.handle_candle`` calls when a candle closes — with the two seams of
:mod:`.environment` supplied (a clock at the bar, an empty hot state). Which
means, for free and not by re-statement:

- the context is cut at ``source_bar_close`` and holds only ``is_final`` 1m
  candles (``repo.load_candles`` + ``strategies.base.build_context``);
- the slot state machine, the re-arm barrier and the one-tracking-per-slot rule
  are the live ones (``episodes.next_slot`` under ``slots.lock_slot``);
- the entry bar, the assumed costs, the frozen levels, the envelope and the
  identity are the live ones (``plan_entry``, ``assumed_costs``,
  ``build_record``, ``identity.signal_id``);
- the exits are the live walker and the live settlement
  (``outcomes.advance_tracking`` -> ``walker.walk`` -> ``settle.settle``).

What the *run* supplies is the cohort — ``replay:<run_id>``, the 0002 grammar
kept by ``0012_replication`` — and the cohort is what keeps the population
apart: it is inside ``identity.signal_id``, it is the third column of the
episode slot, it is what ``persist.persist_decision`` reads to refuse to write
an outbox row (a replay is nobody's event), and it is what the execution bridge
refuses by name (``cohort_not_live``, T3.15e).

Two bars are never evaluated: one whose timeframe did not close
(``versions_for_bar``'s rule, applied here by construction — the loop only
visits aligned closes), and one outside the window.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowTrackingState, Timeframe
from hunter_core.domain.market import align_open_time, timeframe_seconds
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_strategy_worker import slots
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.outcomes import advance_tracking
from hunter_strategy_worker.replay.candles import load_window
from hunter_strategy_worker.replay.environment import (
    REPLAY_DECISION_LAG_S,
    ReplayClock,
    ReplayHotState,
    as_redis,
)
from hunter_strategy_worker.replay.explain import ExplainLedger
from hunter_strategy_worker.tracking_repo import load_open_trackings, load_tracking

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_strategy_worker.catalogue import ActiveVersion
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.repo import MarketRow

logger = get_logger(__name__)

MINUTE = timedelta(minutes=1)
DRAIN_MARGIN = timedelta(minutes=2)
"""How far past a tracking's horizon the drain's clock is placed.

``advance_tracking`` folds bars up to ``min(horizon_open, last_closed_minute(now))``,
so a clock exactly at the horizon open would stop one minute short of it."""

__all__ = [
    "DRAIN_MARGIN",
    "MINUTE",
    "MarketReplay",
    "Population",
    "ReplayWindow",
    "bar_closes",
    "count_population",
    "drain_cohort",
    "replay_market",
]


@dataclass(frozen=True, slots=True)
class ReplayWindow:
    """``[start, end)`` in *decision* time — which bar closes are visited.

    Half-open on purpose, so two adjacent slices of the same run
    (``--from``/``--to`` sliced) never evaluate the same bar twice. Evaluating it
    twice would not corrupt anything — the identity is a ``uuid5`` and the insert
    is ``ON CONFLICT DO NOTHING`` — but it would double the ledger's ``bars`` and
    the throughput number would be a lie.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if ensure_utc(self.end) <= ensure_utc(self.start):
            raise ValueError(
                f"empty replay window: {self.start.isoformat()}..{self.end.isoformat()}"
            )

    @property
    def days(self) -> float:
        return (ensure_utc(self.end) - ensure_utc(self.start)).total_seconds() / 86_400


def bar_closes(window: ReplayWindow, timeframe: Timeframe) -> Iterator[datetime]:
    """Every close of ``timeframe`` inside ``window``, oldest first.

    A *close* of the 5m bar opening at 12:00 is 12:05, and 12:05 is itself a
    bucket boundary, so the closes of a timeframe are exactly its aligned
    instants — which is what ``decide.versions_for_bar`` tests with
    ``is_aligned``. Deriving them instead of filtering candles is what makes the
    loop O(bars) rather than O(minutes), and it visits a bar whose candles are
    missing too: an unevaluable bar is a counted ``unavailable``, never a bar the
    run pretends did not exist.
    """
    step = timedelta(seconds=timeframe_seconds(timeframe))
    start, end = ensure_utc(window.start), ensure_utc(window.end)
    cursor = align_open_time(start, timeframe)
    if cursor < start:
        cursor += step
    while cursor < end:
        yield cursor
        cursor += step


@dataclass(slots=True)
class MarketReplay:
    """What replaying one (version, market, window) did."""

    bars: int = 0
    states: dict[str, int] = field(default_factory=lambda: {})
    errors: int = 0

    def record(self, state: str) -> None:
        self.states[state] = self.states.get(state, 0) + 1

    def merge(self, other: MarketReplay) -> None:
        self.bars += other.bars
        self.errors += other.errors
        for state, count in other.states.items():
            self.states[state] = self.states.get(state, 0) + count


async def replay_market(
    factory: async_sessionmaker[AsyncSession],
    *,
    version: ActiveVersion,
    market: MarketRow,
    window: ReplayWindow,
    config: ShadowConfig,
    lag_s: int = REPLAY_DECISION_LAG_S,
    explain: ExplainLedger | None = None,
) -> MarketReplay:
    """Evaluate every aligned bar of ``window`` for one version and one market.

    ``config.cohort`` must already be the run's ``replay:<run_id>``:
    ``ActiveVersion.cohort`` returns the process cohort unchanged for anything
    that is not ``prospective`` (``catalogue.py``), which is precisely the rule
    that keeps a replay of a replication sibling a *replay* and not the sibling's
    reserved forward population.

    The whole slice's candles are read **once** into a :class:`WindowCache` and
    handed to the live evaluation as its ``candles_reader``. That is a cost
    decision and not a content one: the cache answers exactly what
    ``repo.load_candles`` answers (``replay/candles.py``), and a request outside
    what it holds still goes to the database.
    """
    hot_state = as_redis(ReplayHotState())
    result = MarketReplay()
    async with role_session(factory, db_role="hunter_worker") as session:
        cache = await load_window(
            session,
            market=market,
            window_start=window.start,
            window_end=window.end,
            context_minutes=config.context_minutes,
        )
    for bar_close in bar_closes(window, version.timeframe):
        try:
            evaluation = await evaluate_slot(
                factory,
                hot_state,
                version=version,
                market=market,
                bar_close=bar_close,
                config=config,
                clock=ReplayClock(bar_close, lag_s),
                candles_reader=cache,
            )
        except Exception:
            result.errors += 1
            logger.exception(
                "replay_bar_failed",
                strategy=version.strategy_key,
                symbol=market.symbol,
                bar_close=bar_close.isoformat(),
            )
            continue
        result.bars += 1
        result.record(evaluation.state.value)
        if explain is not None:
            # Same object the counter above read: the ledger cannot disagree
            # with ``evaluations_by_state`` about what this bar answered.
            explain.record(bar_close, evaluation)
    return result


async def drain_cohort(
    factory: async_sessionmaker[AsyncSession],
    *,
    cohort: str,
    config: ShadowConfig,
    passes: int = 4,
) -> int:
    """Finish the trackings the bar loop left open. Returns how many are still open.

    The bar loop already advances the open tracking of each slot it touches
    (``decide.evaluate_slot`` does it first thing, under the slot's lock), so
    almost every outcome is resolved inline. What is left at the end of a window
    are the trackings whose horizon closes *after* the last evaluated bar. They
    are advanced with a clock at their own horizon — never past the wall clock,
    because a candle that has not happened yet cannot resolve anything — using
    the same :func:`advance_tracking` the live sweep uses, so a censored minute
    is censored here for the same reason and with the same wording.

    Reading candles that close after the window is **not** look-ahead: the
    decision was already taken and frozen at its own bar. It is the same thing
    the live lane does one minute at a time.
    """
    still_open = 0
    for _ in range(passes):
        async with role_session(factory, db_role="hunter_worker") as session:
            pending = await load_open_trackings(session, cohort=cohort, limit=10_000)
        if not pending:
            return 0
        still_open = 0
        for tracking in pending:
            async with role_session(factory, db_role="hunter_worker") as session:
                await slots.lock_slot(
                    session,
                    strategy_version_id=tracking.strategy_version_id,
                    market_id=tracking.market_id,
                    cohort=cohort,
                )
                fresh = await load_tracking(session, tracking.signal_id)
                if fresh is None:
                    continue
                horizon = ensure_utc(fresh.plan.horizon_open) + DRAIN_MARGIN
                now = min(horizon, utcnow())
                advanced = await advance_tracking(session, fresh, config=config, now=now)
                if not advanced.finished:
                    still_open += 1
        if still_open == 0:
            return 0
    return still_open


@dataclass(frozen=True, slots=True)
class Population:
    """The counts one replay cohort actually left in the database."""

    signals: int
    terminal: int
    no_entry: int
    censored: int
    open: int

    @property
    def outcomes(self) -> int:
        """Resolved outcomes: everything that will never move again."""
        return self.terminal + self.no_entry + self.censored


async def count_population(
    session: AsyncSession, *, cohort: str, strategy_version_id: uuid.UUID | None = None
) -> Population:
    """Count the cohort's signals and outcomes by state, from the rows themselves.

    Counted from the database rather than accumulated in memory: the run may be
    sliced across processes and restarts, and a number a process remembers is not
    evidence about what was written (SHADOW-LAB.md §8, coverage).
    """
    query = (
        select(SignalOutcome.tracking_state, func.count())
        .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
        .where(AgentSignal.supporting_features["cohort"].astext == cohort)
        .group_by(SignalOutcome.tracking_state)
    )
    if strategy_version_id is not None:
        query = query.where(AgentSignal.strategy_version_id == strategy_version_id)
    counts: dict[ShadowTrackingState, int] = {
        state: int(total) for state, total in (await session.execute(query)).all()
    }
    open_states = (ShadowTrackingState.PENDING_ENTRY, ShadowTrackingState.ACTIVE)
    return Population(
        signals=sum(counts.values()),
        terminal=counts.get(ShadowTrackingState.TERMINAL, 0),
        no_entry=counts.get(ShadowTrackingState.NO_ENTRY, 0),
        censored=counts.get(ShadowTrackingState.CENSORED, 0),
        open=sum(counts.get(state, 0) for state in open_states),
    )
