"""Wilder's ATR as an **anchored checkpoint**, not a rolling-window recompute.

``docs/plans/M2.md`` §Estágio and ``.claude/state/dialogue-M2.md`` round 4 §2:
the M2 calculator initialises "com origem reproduzível ou checkpoint
persistido, **sem reseed a cada janela móvel**". A pure recompute over the last
N bars reseeds every time the 1500-minute buffer rolls, and near a stage
threshold (``r = |return_1h| / atr_pct`` at 1.5 or 4) that silent reseed changes
the answer without any new market information.

So the state is explicit and serialisable:

- ``origin_bar_open`` is the first bar ever folded in (it only provides the
  previous close of the first true range) and it **does not move** as the window
  rolls;
- the next ``period`` true ranges average into ``seed``, which is *not* an ATR:
  the reading is released only after one smoothing step on top of it, i.e. on
  the 16th bar for ``period = 14`` (the conservative gate agreed in round 4);
- ``advance`` is a pure transition ``(state, closed bars) -> state``: a
  duplicate bar does not advance the recursion, an older bar never rewinds it,
  and a missing bar stops it with ``gap`` instead of jumping.

Losing the checkpoint is not free and is not hidden: :func:`advance_from_context`
re-anchors and stamps ``origin_reason = "gap_rebuild"`` / ``"bootstrap"``, and
the value stays unavailable until the new anchor has warmed up again.

This is a **different policy** from ``hunter_core.strategies.indicators``'
``rolling_window_v1`` (S1, pure, reseeds on the window it is handed). Different
names, different numbers, neither claims to be the other —
``.claude/state/notes-S1.md`` §3 and ``.claude/state/notes-T2.2.md``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import timeframe_seconds
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.context import MarketContext
from hunter_indicators.features.vector import Reason
from hunter_indicators.features.windows import bars_15m

ATR_METHOD = "wilder_v1"
"""The formula. A new formula is a new name, never an edit of this one."""
ATR_ORIGIN = "anchored_checkpoint_v1"
"""The initialisation policy — see the module docstring."""
ATR_PERIOD = 14
ATR_STATE_VERSION = 1


@dataclass(frozen=True, slots=True)
class AtrCheckpoint:
    """Everything needed to continue — and to reproduce — a Wilder recursion."""

    period: int
    timeframe: Timeframe
    origin_bar_open: datetime
    origin_reason: str
    last_bar_open: datetime
    last_close: Decimal
    bars_seen: int
    true_ranges_seen: int
    seed_sum: Decimal
    seed: Decimal | None = None
    seed_anchor: datetime | None = None
    value: Decimal | None = None
    method: str = ATR_METHOD
    origin: str = ATR_ORIGIN
    state_version: int = ATR_STATE_VERSION

    @property
    def available(self) -> bool:
        return self.value is not None

    def as_wire(self) -> dict[str, Any]:
        """Serialisable form (``Decimal``/``datetime`` typed, canonical-friendly)."""
        return {
            "period": self.period,
            "timeframe": self.timeframe.value,
            "origin_bar_open": self.origin_bar_open,
            "origin_reason": self.origin_reason,
            "last_bar_open": self.last_bar_open,
            "last_close": self.last_close,
            "bars_seen": self.bars_seen,
            "true_ranges_seen": self.true_ranges_seen,
            "seed_sum": self.seed_sum,
            "seed": self.seed,
            "seed_anchor": self.seed_anchor,
            "value": self.value,
            "method": self.method,
            "origin": self.origin,
            "state_version": self.state_version,
        }

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> AtrCheckpoint:
        def _decimal(value: Any) -> Decimal | None:
            return None if value is None else Decimal(str(value))

        def _instant(value: Any) -> datetime | None:
            if value is None:
                return None
            return ensure_utc(
                value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            )

        origin = _instant(data["origin_bar_open"])
        last = _instant(data["last_bar_open"])
        close = _decimal(data["last_close"])
        seed_sum = _decimal(data["seed_sum"])
        if origin is None or last is None or close is None or seed_sum is None:
            raise ValueError("an ATR checkpoint needs its origin, last bar and running sum")
        return cls(
            period=int(data["period"]),
            timeframe=Timeframe(data["timeframe"]),
            origin_bar_open=origin,
            origin_reason=str(data["origin_reason"]),
            last_bar_open=last,
            last_close=close,
            bars_seen=int(data["bars_seen"]),
            true_ranges_seen=int(data["true_ranges_seen"]),
            seed_sum=seed_sum,
            seed=_decimal(data.get("seed")),
            seed_anchor=_instant(data.get("seed_anchor")),
            value=_decimal(data.get("value")),
            method=str(data.get("method", ATR_METHOD)),
            origin=str(data.get("origin", ATR_ORIGIN)),
            state_version=int(data.get("state_version", ATR_STATE_VERSION)),
        )


@dataclass(frozen=True, slots=True)
class AtrAdvance:
    """The outcome of folding bars into a checkpoint."""

    checkpoint: AtrCheckpoint | None
    skipped: int = 0
    """Bars ignored as duplicates or as older than the state."""
    reason: Reason | None = None
    """Why the advance stopped (``gap``) or why there is no checkpoint (``warmup``)."""


def _true_range(bar: Bar, previous_close: Decimal) -> Decimal:
    return max(
        bar.high - bar.low,
        abs(bar.high - previous_close),
        abs(bar.low - previous_close),
    )


def _start(bar: Bar, period: int, timeframe: Timeframe, origin_reason: str) -> AtrCheckpoint:
    return AtrCheckpoint(
        period=period,
        timeframe=timeframe,
        origin_bar_open=bar.open_time,
        origin_reason=origin_reason,
        last_bar_open=bar.open_time,
        last_close=bar.close,
        bars_seen=1,
        true_ranges_seen=0,
        seed_sum=Decimal(0),
    )


def _fold(checkpoint: AtrCheckpoint, bar: Bar) -> AtrCheckpoint:
    period = checkpoint.period
    with localcontext(CONTEXT):
        true_range = _true_range(bar, checkpoint.last_close)
        seen = checkpoint.true_ranges_seen + 1
        seed_sum = checkpoint.seed_sum + true_range
        seed, seed_anchor, value = checkpoint.seed, checkpoint.seed_anchor, checkpoint.value
        if seen < period:
            pass  # still filling the seed
        elif seen == period:
            seed = seed_sum / Decimal(period)
            seed_anchor = bar.open_time
        else:
            base = value if value is not None else seed
            assert base is not None  # seen > period implies the seed exists
            value = (base * (period - 1) + true_range) / Decimal(period)
    return replace(
        checkpoint,
        last_bar_open=bar.open_time,
        last_close=bar.close,
        bars_seen=checkpoint.bars_seen + 1,
        true_ranges_seen=seen,
        seed_sum=seed_sum,
        seed=seed,
        seed_anchor=seed_anchor,
        value=value,
    )


def advance(
    checkpoint: AtrCheckpoint, bars: Iterable[Bar], *, period: int | None = None
) -> AtrAdvance:
    """Fold ``bars`` into ``checkpoint``, in order, refusing to guess.

    A bar at or before ``last_bar_open`` is a redelivery and is skipped; a bar
    that does not start exactly one step after it means a bar was lost, and the
    advance stops with ``gap`` leaving the checkpoint untouched — the caller
    decides whether to rebuild (:func:`advance_from_context` does).
    """
    if period is not None and period != checkpoint.period:
        raise ValueError(f"checkpoint period {checkpoint.period} != requested period {period}")
    step = timeframe_seconds(checkpoint.timeframe)
    current = checkpoint
    skipped = 0
    for bar in sorted(bars, key=lambda b: b.open_time):
        if bar.open_time <= current.last_bar_open:
            skipped += 1
            continue
        if int((bar.open_time - current.last_bar_open).total_seconds()) != step:
            return AtrAdvance(checkpoint=current, skipped=skipped, reason=Reason.GAP)
        current = _fold(current, bar)
    return AtrAdvance(checkpoint=current, skipped=skipped)


def bootstrap(
    bars: Sequence[Bar],
    *,
    period: int = ATR_PERIOD,
    timeframe: Timeframe = Timeframe.M15,
    origin_reason: str = "bootstrap",
) -> AtrAdvance:
    """Anchor a new checkpoint on ``bars[0]`` and fold the rest."""
    if period < 1:
        raise ValueError("period must be >= 1")
    if not bars:
        return AtrAdvance(checkpoint=None, reason=Reason.WARMUP)
    ordered = sorted(bars, key=lambda b: b.open_time)
    result = advance(_start(ordered[0], period, timeframe, origin_reason), ordered[1:])
    return result


def last_bar_close(checkpoint: AtrCheckpoint) -> datetime:
    """Close of the newest bar folded into ``checkpoint`` — the reading's instant."""
    return checkpoint.last_bar_open + timedelta(seconds=timeframe_seconds(checkpoint.timeframe))


def _is_after_cut(checkpoint: AtrCheckpoint, as_of: datetime) -> bool:
    """True when the checkpoint has folded a bar that had not closed at ``as_of``."""
    return last_bar_close(checkpoint) > as_of


def atr_percent(checkpoint: AtrCheckpoint) -> Decimal | None:
    """ATR as a **fraction** of the close of the bar that produced it."""
    if checkpoint.value is None or checkpoint.last_close <= 0:
        return None
    with localcontext(CONTEXT):
        return checkpoint.value / checkpoint.last_close


def advance_from_context(
    ctx: MarketContext,
    checkpoint: AtrCheckpoint | None,
    *,
    period: int = ATR_PERIOD,
) -> AtrAdvance:
    """Carry ``checkpoint`` forward with the complete 15m bars of ``ctx``.

    Without a checkpoint (cold start, or one that cannot be continued) it
    bootstraps from the oldest complete bar the context holds and records the
    anchor, so the reading always says where its recursion started.
    """
    if checkpoint is not None and _is_after_cut(checkpoint, ctx.as_of):
        # The state has already folded bars this cut had not printed: replaying an
        # older instant with it would read the future (Astra, T2.2 diff review,
        # must-fix 1). Re-anchor on what the context itself can prove.
        checkpoint = None
        origin = "cut_rebuild"
    else:
        origin = "bootstrap"
    window = bars_15m(ctx)
    if not window.available:
        return AtrAdvance(checkpoint=checkpoint, reason=window.reason)
    bars = window.bars
    if checkpoint is None:
        return bootstrap(bars, period=period, origin_reason=origin)
    if checkpoint.period != period or checkpoint.timeframe is not Timeframe.M15:
        return bootstrap(bars, period=period, origin_reason="policy_rebuild")
    fresh = [bar for bar in bars if bar.open_time > checkpoint.last_bar_open]
    if not fresh:
        return AtrAdvance(checkpoint=checkpoint)
    result = advance(checkpoint, fresh)
    if result.reason is Reason.GAP:
        # the bar that would have continued the recursion never arrived: re-anchor
        # on what we do have, and say so instead of pretending continuity.
        return bootstrap(bars, period=period, origin_reason="gap_rebuild")
    return result


__all__ = [
    "ATR_METHOD",
    "ATR_ORIGIN",
    "ATR_PERIOD",
    "ATR_STATE_VERSION",
    "AtrAdvance",
    "AtrCheckpoint",
    "advance",
    "advance_from_context",
    "last_bar_close",
    "atr_percent",
    "bootstrap",
]
