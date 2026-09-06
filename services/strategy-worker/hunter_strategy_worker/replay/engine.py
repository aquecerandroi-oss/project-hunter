"""Folding one arm over one frozen entry with the production walker.

The loop is deliberately one bar at a time. :func:`~hunter_strategy_worker.walker.walk`
is a fold, so feeding it a single bar is the same computation as feeding it the
whole series — and it leaves a seam between bars where the two policies that are
not price levels (``INV-C``, ``EXIT-CHAN``) can observe the close that just
happened and mark the invalidation as *pending*. The walker still decides when a
pending invalidation is paid (the next eligible open) and with which priority
(stop > target > horizon > invalidation), so no exit rule is written twice.

Three refusals worth naming, because each of them would otherwise become an
invented number:

- a hole in the 1m series stops the fold; the arm is *unresolved* with the
  missing minute, never walked over;
- an entry whose horizon has not closed yet at ``as_of`` is *immature*, not
  "still open at the end";
- the channel needs its whole window of 15m closes; without it the observer
  answers ``None`` and the arm is unresolved, never "did not fire".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, Timeframe
from hunter_core.domain.market import is_aligned
from hunter_core.strategies.aggregate import aggregate
from hunter_indicators.replay.policies import ExitPolicy, check_target_unreachable
from hunter_strategy_worker.replay.arms import ArmNotBuildable, ArmSpec, build_arm
from hunter_strategy_worker.replay.series import Series, load_series
from hunter_strategy_worker.settle import settle
from hunter_strategy_worker.walker import Bar, Progress, walk

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.replay.load import ReplayCase

__all__ = ["ArmOutcome", "Series", "fold_arm", "load_series", "replay_arm", "replay_case"]

_UNSTARTED = Progress.start()
"""The immutable "decided, not entered" progress — frozen, so one is enough."""


@dataclass(frozen=True, slots=True)
class ArmOutcome:
    """What one policy would have done with one frozen entry."""

    signal_id: uuid.UUID
    policy_key: str
    tracking_state: ShadowTrackingState | None
    result: OutcomeResult | None
    reason: str | None
    entry: Decimal | None
    entry_ts: datetime | None
    exit_base: Decimal | None
    exit_price: Decimal | None
    exit_ts: datetime | None
    exit_at_open: bool | None
    exit_bar_open: datetime | None
    r_net: Decimal | None
    r_ex_funding: Decimal | None
    funding_reason: str | None
    trigger: str | None
    bars_folded: int
    inherited: bool = False
    """True when the base refused the entry and the arm inherited that refusal."""
    matured: bool = True
    """Whether the whole horizon of this entry had closed by ``as_of``.

    A contrast may only pair matured entries: an arm that exits early is always
    resolved while a slower one is still open, so pairing on "both resolved"
    would select trades by how fast they end (Astra, R1 fixes review)."""

    @property
    def resolved(self) -> bool:
        return self.tracking_state is ShadowTrackingState.TERMINAL


def _previous_closes(
    series: Series, close_time: datetime, *, timeframe: Timeframe, lookback: int
) -> list[Decimal] | None:
    """The ``lookback`` closes before ``close_time``, or ``None`` if incomplete."""
    window = aggregate(list(series.candles), timeframe, close_time, lookback + 1)
    if not window.available:
        return None
    return [bar.close for bar in window.bars[:-1]]


def _observe(
    spec: ArmSpec, series: Series, bar: Bar, streak: int
) -> tuple[int, str | None, str | None]:
    """``(streak, trigger, unavailable_reason)`` after this bar's close."""
    if spec.consecutive is not None:
        advanced, fired = spec.consecutive.step(streak, close_time=bar.close_time, close=bar.close)
        return advanced, ("two_closes" if fired else None), None
    if spec.channel is None or spec.channel_timeframe is None:
        return streak, None, None
    if not is_aligned(bar.close_time, spec.channel_timeframe):
        return streak, None, None
    previous = _previous_closes(
        series,
        bar.close_time,
        timeframe=spec.channel_timeframe,
        lookback=spec.channel.lookback,
    )
    if previous is None:
        return streak, None, "channel_window_unavailable"
    fired = spec.channel.fired(bar.close, previous)
    if fired is None:
        return streak, None, "channel_window_unavailable"
    return streak, ("channel" if fired else None), None


def fold_arm(spec: ArmSpec, series: Series) -> tuple[Progress, str | None, str | None, int]:
    """Fold the whole prefix. Returns progress, trigger, unavailable reason, bars."""
    progress = Progress.start()
    streak = 0
    trigger: str | None = None
    folded = 0
    for bar in series.bars:
        before = progress.pending_invalidation
        progress = walk(spec.plan, progress, [bar])
        folded += 1
        if progress.finished:
            break
        if progress.pending_invalidation and not before and trigger is None:
            trigger = "invalidation"
        if progress.tracking_state is not ShadowTrackingState.ACTIVE:
            continue
        if progress.pending_invalidation:
            continue
        streak, fired, unavailable = _observe(spec, series, bar, streak)
        if unavailable is not None:
            return progress, trigger, unavailable, folded
        if fired is not None:
            progress = replace(progress, pending_invalidation=True)
            trigger = fired
    return progress, trigger, None, folded


def _open_outcome(
    case: ReplayCase,
    policy_key: str,
    *,
    state: ShadowTrackingState | None,
    reason: str | None,
    progress: Progress = _UNSTARTED,
    folded: int = 0,
    inherited: bool = False,
) -> ArmOutcome:
    """An arm with no settlement: unresolved, refused, or inherited."""
    return ArmOutcome(
        signal_id=case.signal_id,
        policy_key=policy_key,
        tracking_state=state,
        result=None,
        reason=reason,
        entry=progress.entry,
        entry_ts=progress.entry_ts,
        exit_base=None,
        exit_price=None,
        exit_ts=None,
        exit_at_open=None,
        exit_bar_open=None,
        r_net=None,
        r_ex_funding=None,
        funding_reason=None,
        trigger=None,
        bars_folded=folded,
        inherited=inherited,
    )


def _unresolved(
    case: ReplayCase, policy_key: str, progress: Progress, reason: str, folded: int
) -> ArmOutcome:
    return _open_outcome(
        case,
        policy_key,
        state=progress.tracking_state,
        reason=reason,
        progress=progress,
        folded=folded,
    )


async def replay_arm(
    session: AsyncSession, case: ReplayCase, spec: ArmSpec, series: Series
) -> ArmOutcome:
    """Replay one arm over one entry, settling it with the production code."""
    if spec.sentinel is not None:
        check_target_unreachable(spec.sentinel, [bar.high for bar in series.bars])
    progress, trigger, unavailable, folded = fold_arm(spec, series)
    if unavailable is not None:
        return _unresolved(case, spec.policy.key, progress, unavailable, folded)
    if progress.tracking_state is ShadowTrackingState.NO_ENTRY:
        return _open_outcome(
            case,
            spec.policy.key,
            state=ShadowTrackingState.NO_ENTRY,
            reason=progress.no_entry_reason,
            folded=folded,
        )
    if not progress.finished:
        return _unresolved(
            case, spec.policy.key, progress, series.truncated or "open_at_as_of", folded
        )
    settlement = await settle(session, market_id=case.market.id, plan=spec.plan, progress=progress)
    ex_funding = settlement.meta.get("r_ex_funding")
    return ArmOutcome(
        signal_id=case.signal_id,
        policy_key=spec.policy.key,
        tracking_state=progress.tracking_state,
        result=progress.result,
        reason=None,
        entry=progress.entry,
        entry_ts=progress.entry_ts,
        exit_base=progress.exit_base,
        exit_price=settlement.exit_price,
        exit_ts=progress.exit_ts,
        exit_at_open=progress.exit_at_open,
        exit_bar_open=progress.exit_bar_open,
        r_net=settlement.r_multiple,
        r_ex_funding=None if ex_funding is None else Decimal(str(ex_funding)),
        funding_reason=settlement.meta.get("r_net_reason"),
        trigger=trigger,
        bars_folded=folded,
    )


def _inherited(case: ReplayCase, policy_key: str, reason: str | None) -> ArmOutcome:
    """The base refused the entry, so every arm refuses it identically."""
    return _open_outcome(
        case,
        policy_key,
        state=ShadowTrackingState.NO_ENTRY,
        reason=reason,
        inherited=True,
    )


async def replay_case(
    session: AsyncSession,
    case: ReplayCase,
    *,
    policies: Sequence[ExitPolicy],
    series: Series,
    base_key: str = "base",
) -> Mapping[str, ArmOutcome]:
    """Replay every requested policy over one entry, with the admission frozen.

    The entry side belongs to the base: if the frozen record says the entry
    never happened, or if the base's own geometry check refuses it, **no arm
    enters**. A larger target could otherwise admit an entry the base rejected
    and the two populations would stop being paired (Strategy Backlog, "ressalva
    de pareamento").

    A ``no_entry: late:*`` is inherited without folding anything: lateness is
    evidence about the clock at decision time and no candle can re-derive it. A
    ``no_entry: geometry`` **is** re-derived from the entry bar, because that
    one is a price statement — copying it back would be auditing the record
    against itself (Astra, R1 diff review, must-fix 2).
    """
    outcomes = await _replayed(session, case, policies=policies, series=series, base_key=base_key)
    matured = series.truncated != "immature"
    return {key: replace(arm, matured=matured) for key, arm in outcomes.items()}


async def _replayed(
    session: AsyncSession,
    case: ReplayCase,
    *,
    policies: Sequence[ExitPolicy],
    series: Series,
    base_key: str,
) -> Mapping[str, ArmOutcome]:
    outcomes: dict[str, ArmOutcome] = {}
    stored_state = case.stored.tracking_state
    late = (case.stored.no_entry_reason or "").startswith("late")
    if stored_state is ShadowTrackingState.NO_ENTRY and late:
        return {p.key: _inherited(case, p.key, case.stored.no_entry_reason) for p in policies}
    base_spec = build_arm(case, next(p for p in policies if p.key == base_key))
    base_outcome = await replay_arm(session, case, base_spec, series)
    outcomes[base_key] = base_outcome
    refused = base_outcome.tracking_state is ShadowTrackingState.NO_ENTRY
    for policy in policies:
        if policy.key == base_key:
            continue
        if refused:
            outcomes[policy.key] = _inherited(case, policy.key, base_outcome.reason)
            continue
        try:
            spec = build_arm(case, policy)
        except ArmNotBuildable as exc:
            outcomes[policy.key] = _unresolved(case, policy.key, Progress.start(), exc.reason, 0)
            continue
        outcomes[policy.key] = await replay_arm(session, case, spec, series)
    return outcomes
