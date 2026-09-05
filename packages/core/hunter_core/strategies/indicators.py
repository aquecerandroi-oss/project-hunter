"""Pure indicators over aggregated bars — every division is explicit ``Decimal``.

The window a calculator gets is already the exact window the strategy asked for
(:mod:`hunter_core.strategies.aggregate`), so "not enough data" here means the
caller asked for more than it has, and the answer is ``None`` — never a shorter
window, never a float.

Determinism: every arithmetic operation runs inside :data:`CONTEXT` (28
significant digits, banker's rounding) via ``localcontext``, not only the
divisions — a sum or a product also rounds under the ambient context, so a
process that changed ``decimal.getcontext()`` could otherwise move a frozen
strategy version's numbers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.numeric import CONTEXT

ATR_METHOD = "wilder_v1"
"""Versioned name of the ATR formula below; a new formula is a new name."""

ATR_ORIGIN = "rolling_window_v1"
"""How the recursion is initialised, and it is **not** a continuous Wilder state.

A pure function has no checkpoint: :func:`wilder_atr` reseeds on the first bar
of the window it is handed and smooths forward from there. That is what makes a
bootstrapped context and a continuously running worker produce the same number
— they recompute the same declared window — and it is *not* the same number an
incremental ATR carried since an older origin would hold (the M2 calculator
keeps such a checkpoint; see ``.claude/state/notes-S1.md``). The strategies pass
a window long enough for the seed's weight to decay to a fraction of a percent,
and the window start is persisted with the reading.
"""


@dataclass(frozen=True, slots=True)
class Atr:
    """A Wilder ATR reading with everything needed to reproduce it later.

    ``seed``, ``seed_anchor`` and ``window_start`` are persisted with the signal
    (SHADOW-LAB.md §7): without the origin *and* the extent of the window, an ATR
    recomputed later is a different number and the frozen version could not be
    audited.
    """

    value: Decimal
    period: int
    seed: Decimal
    seed_anchor: datetime
    window_start: datetime
    bars_used: int
    method: str = ATR_METHOD
    origin: str = ATR_ORIGIN


def _true_range(current: Bar, previous: Bar) -> Decimal:
    return max(
        current.high - current.low,
        abs(current.high - previous.close),
        abs(current.low - previous.close),
    )


def wilder_atr(bars: Sequence[Bar], period: int) -> Atr | None:
    """Wilder's ATR over ``bars``, or ``None`` while it is still warming up.

    Needs ``period + 2`` bars: the first bar only provides the previous close of
    the first true range, the next ``period`` true ranges average into the seed,
    and the reading is released only after **one smoothing step** has been
    applied on top of the seed — the conservative gate agreed for the M2
    calculator (``.claude/state/dialogue-M2.md`` round 4 §2: "não reutilizar a
    seed como se fosse o ATR atual").

    The seed is first defined on ``bars[period]``; that bar's ``open_time`` is the
    anchor. Every later bar applies ``ATR_i = (ATR_{i-1}(period-1) + TR_i)/period``.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(bars) < period + 2:
        return None

    with localcontext(CONTEXT):
        true_ranges = [_true_range(bars[i], bars[i - 1]) for i in range(1, len(bars))]
        seed = sum(true_ranges[:period], start=Decimal(0)) / Decimal(period)
        value = seed
        for true_range in true_ranges[period:]:
            value = (value * (period - 1) + true_range) / Decimal(period)
    return Atr(
        value=value,
        period=period,
        seed=seed,
        seed_anchor=bars[period].open_time,
        window_start=bars[0].open_time,
        bars_used=len(bars),
    )


def atr_percent(atr: Atr, close: Decimal) -> Decimal | None:
    """ATR as a fraction of ``close`` (docs/plans/M2.md T2.2: last close is the denominator)."""
    if close <= 0:
        return None
    with localcontext(CONTEXT):
        return atr.value / close


def median(values: Sequence[Decimal]) -> Decimal | None:
    """Exact median; the mean of the two middle values for an even sample."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    with localcontext(CONTEXT):
        return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def relative_volume(bars: Sequence[Bar], window: int) -> Decimal | None:
    """Last bar's volume over the median of the ``window`` bars **before** it.

    ``None`` when the lookback is incomplete or its median is zero (a market
    that did not trade has no baseline, and 0 is not a divisor).
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if len(bars) < window + 1:
        return None
    baseline = median([bar.volume for bar in bars[-window - 1 : -1]])
    if baseline is None or baseline == 0:
        return None
    with localcontext(CONTEXT):
        return bars[-1].volume / baseline


def max_previous_close(bars: Sequence[Bar], count: int) -> Decimal | None:
    """Highest close of the ``count`` bars before the last one (the current bar is excluded)."""
    if count < 1:
        raise ValueError("count must be >= 1")
    if len(bars) < count + 1:
        return None
    return max(bar.close for bar in bars[-count - 1 : -1])


def return_n(bars: Sequence[Bar], n: int) -> Decimal | None:
    """``close_t / close_{t-n} - 1`` as a fraction, or ``None`` without the reference."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if len(bars) < n + 1:
        return None
    reference = bars[-1 - n].close
    if reference <= 0:
        return None
    with localcontext(CONTEXT):
        return bars[-1].close / reference - 1
