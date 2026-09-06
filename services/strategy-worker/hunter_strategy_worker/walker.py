"""The outcome model as a pure fold over closed 1-minute bars.

SHADOW-LAB.md "Decisão conjunta" §3/§4/§5. Everything durable about one
hypothetical trade lives in :class:`Progress`, which is persisted verbatim in
``signal_outcomes.meta.progress``; :func:`walk` folds bars into it and is the
only place the exit rules are written down:

1. the entry bar is entered at its open (``P_entry``), and the frozen geometry
   is revalidated against that price — ``stop < P_entry < target1`` or
   ``no_entry: geometry``;
2. every later bar is judged **at its open first**, in the declared priority
   ``stop > target > expired > invalidated`` (an adverse gap exits at the open,
   a favourable gap gets no credit beyond ``target1``, the horizon open expires,
   a pending invalidation is paid), and only then intrabar;
3. inside one bar, stop wins over target — the versioned pessimistic
   convention, because OHLC cannot say which came first;
4. an invalidation is *observed* at the close of a bar aligned to the
   invalidation timeframe and *paid* at the next eligible open;
5. nothing at or after the horizon open reaches the excursions.

The fold is idempotent by ``last_bar_open`` (a redelivered bar changes
nothing) and refuses a non-contiguous bar instead of silently skipping it: a
skipped minute is a censored outcome, never an invented one.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from decimal import Decimal, localcontext

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState
from hunter_core.domain.market import is_aligned
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_strategy_worker.pricing import entry_price
from hunter_strategy_worker.progress import MINUTE, Bar, Progress, TrackingPlan

__all__ = ["Bar", "MINUTE", "Progress", "TrackingPlan", "walk"]


def _enter(plan: TrackingPlan, progress: Progress, candle: Bar) -> Progress:
    """Take the hypothetical entry at ``candle``'s open, or refuse the geometry."""
    price = entry_price(candle.open, plan.costs)
    if not plan.stop < price < plan.target1:
        return replace(
            progress,
            tracking_state=ShadowTrackingState.NO_ENTRY,
            result=OutcomeResult.OPEN,
            no_entry_reason="geometry",
            last_bar_open=candle.open_time,
        )
    return replace(
        progress,
        tracking_state=ShadowTrackingState.ACTIVE,
        entry=price,
        entry_ts=candle.open_time,
        first_bar_open=candle.open_time,
    )


def _exit_at_open(plan: TrackingPlan, progress: Progress, candle: Bar) -> Progress | None:
    """Anything resolved by the open alone, in the documented priority order.

    ``stop > target > expired > invalidated`` (``notes-S2.md`` §9). The exit
    *price* is the same whichever of the last two fires — it is this open either
    way — so the ordering only decides the label; S3 counts populations by that
    label, which is why the code has to spell the declared convention rather
    than an incidental one.
    """
    if candle.open <= plan.stop:
        return _close(progress, candle, OutcomeResult.STOP, candle.open, at_open=True)
    if candle.open >= plan.target1:
        return _close(progress, candle, OutcomeResult.TARGET, plan.target1, at_open=True)
    if candle.open_time >= plan.horizon_open:
        return _close(progress, candle, OutcomeResult.EXPIRED, candle.open, at_open=True)
    if progress.pending_invalidation:
        return _close(progress, candle, OutcomeResult.INVALIDATED, candle.open, at_open=True)
    return None


def _close(
    progress: Progress,
    candle: Bar,
    result: OutcomeResult,
    base: Decimal,
    *,
    at_open: bool,
) -> Progress:
    """Finish the tracking. ``base`` is the *synthetic* exit; ``exit_observed``
    is the price the market actually printed at that instant.

    They differ on a favourable gap: the trade is credited at ``target1`` (no
    credit beyond it) while the market opened higher, and that higher price is
    a real excursion the position lived through. Measuring the excursion with
    the capped base would understate it (Astra, S2 diff review, must-fix 4).
    """
    return replace(
        progress,
        tracking_state=ShadowTrackingState.TERMINAL,
        result=result,
        exit_base=base,
        exit_observed=candle.open if at_open else base,
        exit_ts=candle.open_time if at_open else candle.close_time,
        exit_at_open=at_open,
        exit_bar_open=candle.open_time,
        exit_bar_high=None if at_open else candle.high,
        exit_bar_low=None if at_open else candle.low,
        last_bar_open=candle.open_time,
        window_last_open=(progress.window_last_open if at_open else candle.open_time),
        bars_in_position=progress.bars_in_position + (0 if at_open else 1),
    )


def _absorb(progress: Progress, candle: Bar) -> Progress:
    """Fold a bar that ended with the tracking still open (a *complete* bar)."""
    with localcontext(CONTEXT):
        high, high_ts = progress.complete_high, progress.complete_high_ts
        if high is None or candle.high > high:
            high, high_ts = candle.high, candle.open_time
        low, low_ts = progress.complete_low, progress.complete_low_ts
        if low is None or candle.low < low:
            low, low_ts = candle.low, candle.open_time
    return replace(
        progress,
        complete_high=high,
        complete_high_ts=high_ts,
        complete_low=low,
        complete_low_ts=low_ts,
        bars_in_position=progress.bars_in_position + 1,
        window_last_open=candle.open_time,
        last_bar_open=candle.open_time,
    )


def _observe_invalidation(plan: TrackingPlan, progress: Progress, candle: Bar) -> Progress:
    level, timeframe = plan.invalidation_level, plan.invalidation_timeframe
    if level is None or timeframe is None or progress.pending_invalidation:
        return progress
    if not is_aligned(candle.close_time, timeframe) or candle.close >= level:
        return progress
    return replace(progress, pending_invalidation=True)


def _step(plan: TrackingPlan, progress: Progress, candle: Bar) -> Progress:
    if progress.tracking_state is ShadowTrackingState.PENDING_ENTRY:
        entered = _enter(plan, progress, candle)
        if entered.finished:
            return entered
        progress = entered
    else:
        resolved = _exit_at_open(plan, progress, candle)
        if resolved is not None:
            return resolved
    if candle.low <= plan.stop:
        return _close(progress, candle, OutcomeResult.STOP, plan.stop, at_open=False)
    if candle.high >= plan.target1:
        return _close(progress, candle, OutcomeResult.TARGET, plan.target1, at_open=False)
    return _observe_invalidation(plan, _absorb(progress, candle), candle)


def walk(plan: TrackingPlan, progress: Progress, bars: Iterable[Bar]) -> Progress:
    """Fold ``bars`` into ``progress``. Pure; the caller persists the result.

    Bars at or before ``last_bar_open`` are ignored (a redelivery is a no-op);
    a bar that is not the next expected minute raises, because guessing over a
    hole would fabricate an outcome the data does not support.
    """
    ordered: Sequence[Bar] = list(bars)
    for candle in ordered:
        if progress.finished:
            return progress
        expected = progress.next_expected_open(plan)
        open_time = ensure_utc(candle.open_time)
        if open_time < expected:
            continue
        if open_time != expected:
            raise ValueError(
                f"bars must be contiguous: expected {expected.isoformat()}, "
                f"got {open_time.isoformat()}"
            )
        progress = _step(plan, progress, candle)
    return progress
