"""One evaluated bar: from a closed candle to a persisted shadow decision.

The order inside :func:`evaluate_slot` is deliberate and is the answer to a real
race (Astra, S2 design review): the open tracking is advanced **first**, up to
the bar being evaluated, and only then the slot transition is applied. Doing it
the other way round makes the result depend on which loop ran first — a bar that
should have re-armed the slot (because the tracking had already ended) would
instead be spent while the tracking still looked open.

Everything that mutates state happens in one transaction that holds the slot's
row lock, so two consumers handling the same bar produce one tracking.

The global regime in force at ``bar_close`` (:func:`hunter_strategy_worker.repo.load_regime_asof`)
is looked up under that same lock, right before the record is built, and is
stamped onto ``agent_signals.regime_id`` — never blocking the decision when
there is none yet (notes-S2.md, "o regime não chega ao sinal").
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.market import is_aligned
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.strategies.base import Evaluation, EvaluationState, assumed_costs
from hunter_strategy_worker import slots
from hunter_strategy_worker.confirm import confirm_or_lapse
from hunter_strategy_worker.context import build_market_context
from hunter_strategy_worker.eligibility import universe_changed_after
from hunter_strategy_worker.episodes import SlotState, next_slot
from hunter_strategy_worker.identity import signal_id
from hunter_strategy_worker.metrics import shadow_evaluations_total, shadow_signals_total
from hunter_strategy_worker.outcomes import advance_tracking
from hunter_strategy_worker.persist import persist_decision
from hunter_strategy_worker.plan import plan_entry
from hunter_strategy_worker.record import build_record
from hunter_strategy_worker.repo import load_regime_asof
from hunter_strategy_worker.tracking_repo import load_tracking

if TYPE_CHECKING:
    from collections.abc import Callable

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_strategy_worker.catalogue import ActiveVersion
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.record import ShadowRecord
    from hunter_strategy_worker.repo import MarketRow

logger = get_logger(__name__)

__all__ = ["evaluate_slot", "versions_for_bar"]


def versions_for_bar(versions: list[ActiveVersion], bar_close: datetime) -> list[ActiveVersion]:
    """The versions whose timeframe actually closed at ``bar_close``.

    New entries are only ever evaluated on distinct closes of the strategy's own
    timeframe (SHADOW-LAB.md §4): 15m for momentum, 5m for volume.
    """
    return [v for v in versions if is_aligned(bar_close, v.timeframe)]


async def _advance_open_tracking(
    session: AsyncSession, slot: slots.Slot, config: ShadowConfig, now: datetime
) -> None:
    if slot.open_outcome_signal_id is None:
        return
    tracking = await load_tracking(session, slot.open_outcome_signal_id)
    if tracking is None:
        return
    await advance_tracking(session, tracking, config=config, now=now)


async def evaluate_slot(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    *,
    version: ActiveVersion,
    market: MarketRow,
    bar_close: datetime,
    config: ShadowConfig,
    clock: Callable[[], datetime] = utcnow,
) -> Evaluation:
    """Evaluate one (version, market, bar) and apply whatever it implies.

    ``clock`` is injectable so a replay cohort (and a test) can place the bar
    relative to its own timeline instead of the wall clock. It never reaches the
    strategy: the observation is cut at ``bar_close``, which is what forbids
    look-ahead.
    """
    now = clock()
    lag_s = (now - bar_close).total_seconds()
    unprovable: str | None = None
    if lag_s > config.eligibility_max_lag_s:
        unprovable = "lag"
    elif await universe_changed_after(redis, exchange=market.exchange, instant=bar_close):
        # The monitored set changed after this bar closed, so the current
        # ``is_monitored`` is not the flag of that instant. Membership is
        # overwritten in place; only the absence of a change since proves it.
        unprovable = "universe_changed"
    if unprovable is not None:
        # Unavailable proves nothing: it neither decides nor re-arms.
        evaluation = Evaluation(
            None,
            EvaluationState.UNAVAILABLE,
            f"eligibility_unprovable:{unprovable}",
            {"lag_s": f"{lag_s:.0f}"},
        )
        shadow_evaluations_total.labels(
            strategy=version.strategy_key, state=evaluation.state.value
        ).inc()
        return evaluation

    async with role_session(factory, db_role="hunter_worker") as session:
        context, provenance = await build_market_context(
            session,
            redis,
            market=market,
            source_bar_close=bar_close,
            config=config,
            code_ref=version.code_ref,
        )
    evaluation = version.strategy.explain(context, version.params)
    shadow_evaluations_total.labels(
        strategy=version.strategy_key, state=evaluation.state.value
    ).inc()

    record: ShadowRecord | None = None
    async with role_session(factory, db_role="hunter_worker") as session:
        slot = await slots.lock_slot(
            session,
            strategy_version_id=version.id,
            market_id=market.id,
            cohort=config.cohort,
        )
        await _advance_open_tracking(session, slot, config, now)
        # Re-read under the same lock: the advance above may have released the
        # slot and pushed the re-arm barrier, and the transition must see that.
        slot = await slots.lock_slot(
            session,
            strategy_version_id=version.id,
            market_id=market.id,
            cohort=config.cohort,
        )
        if not slot.accepts(bar_close):
            logger.debug(
                "shadow_bar_behind_barrier",
                strategy=version.strategy_key,
                symbol=market.symbol,
                bar_close=bar_close.isoformat(),
            )
            return evaluation
        transition = next_slot(
            SlotState(armed=slot.armed, tracking_open=slot.tracking_open), evaluation.state
        )
        if not transition.decide:
            if transition.advance_checkpoint:
                await slots.advance(session, slot, bar_close=bar_close, armed=transition.armed)
            return evaluation
        if evaluation.decision is None:  # pragma: no cover - Evaluation enforces this
            raise RuntimeError("TRIGGERED evaluation without a decision")
        costs = assumed_costs(version.params)
        decision_at = clock()
        plan = plan_entry(
            source_bar_close=bar_close,
            decision_at=decision_at,
            costs=costs,
            now=decision_at,
        )
        regime_id, regime_reason = await load_regime_asof(session, cut=bar_close)
        record = build_record(
            signal_id=signal_id(
                strategy_version_id=version.id,
                market_id=market.id,
                params_hash=version.params_hash,
                source_bar_close=bar_close,
                cohort=config.cohort,
            ),
            version=version,
            market=market,
            decision=evaluation.decision,
            costs=costs,
            decision_at=decision_at,
            cohort=config.cohort,
            plan=plan,
            provenance=provenance,
            regime_id=regime_id,
            regime_reason=regime_reason,
        )
        written = await persist_decision(session, record)
        # A decision born ``no_entry`` (late) never occupies the slot — it would
        # hold the market's candles for a tracking nobody follows — and its
        # barrier is the decision instant, since that is when it ended.
        await slots.advance(
            session,
            slot,
            bar_close=bar_close if record.entered_slot else decision_at,
            armed=False,
            open_outcome_signal_id=record.signal_id if record.entered_slot else None,
            new_episode=True,
        )
        if written:
            shadow_signals_total.labels(
                strategy=version.strategy_key, tracking_state=record.tracking_state.value
            ).inc()
            logger.info(
                "shadow_signal_emitted",
                signal_id=str(record.signal_id),
                strategy=version.strategy_key,
                symbol=market.symbol,
                tracking_state=record.tracking_state.value,
            )
    if record.entered_slot:
        await confirm_or_lapse(factory, record, clock=clock)
    return evaluation
