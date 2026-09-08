"""Trend-line primitives, part 1: the ATR scale and the swing pivots.

**This is a port, and the port is the point.** The research home of this
geometry is ``hunter_indicators.patterns`` (T3.34, upstream commit ``db798b8``),
where the figures of KB-0077 were drawn. ``hunter_core.strategies`` cannot
import it: ``hunter-indicators`` depends on ``hunter-core`` and not the other
way round, and, worse, ``hunter_strategy_worker.code_ref.module_closure``
follows **flat sibling modules of this package only**, so a cross-package import
would leave the geometry that produces the decisions *outside* the digest that
freezes the version. That is the one direction the freeze must never fail in.

The numbers therefore live twice, and a test keeps them equal instead of
discipline: ``packages/core/tests/unit/strategies/test_tl_parity.py`` asserts
exact ``Decimal`` equality of :func:`atr_series` and :func:`find_pivots` (and of
the lines, channels and events of the two sibling modules) against
``hunter_indicators.patterns``, on the synthetic wave and on a real 15-minute
slice. **If the two ever disagree, the copy is the wrong one.**

Two refusals carried over verbatim, because dropping either changes numbers:

- **warm-up is ``None``, never a substitute.** The first reading appears one
  smoothing step after the seed (bar ``period + 1``); before that a pivot has
  nothing to be measured against and simply is not a pivot yet;
- **a gap raises.** A line drawn across missing bars is a line through a hole.
  The strategy hands over a window ``aggregate()`` has already proved contiguous.

**One deliberate divergence, declared rather than hidden.** A handful of
divisions and comparisons upstream run under the *ambient* decimal context
(``patterns/pivots.py`` scales the prominence outside ``localcontext``, and so do
two branches of ``patterns/events.py``). Every arithmetic operation in this copy
runs inside :data:`~hunter_core.strategies.numeric.CONTEXT`, because a frozen
strategy version whose numbers depend on what some library did to
``decimal.getcontext()`` is not frozen. Under the default context — 28 digits,
``ROUND_HALF_EVEN``, which is what the parity test runs in — the two produce
*identical* values; under a hostile one only this copy still does.

The pivot rules (upstream ``patterns/pivots.py``): a confirmation window ``k`` on
both sides, ``confirmed_at = index + k`` so no consumer can anchor a decision on
the bar itself; an ATR-scaled prominence filter measured over the ``k``
neighbours on each side **excluding the pivot bar** (including it made the
prominence ~1 ATR by construction and the filter filtered nothing); and ties to
the older bar, so a plateau yields one pivot instead of three.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import timeframe_seconds
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "DEFAULT_MIN_SWING_ATR",
    "DEFAULT_PIVOT_K",
    "Pivot",
    "PivotKind",
    "atr_series",
    "find_pivots",
]

DEFAULT_PIVOT_K = 3
DEFAULT_MIN_SWING_ATR = Decimal("1.0")


class PivotKind(StrEnum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True, order=True)
class Pivot:
    """One swing point. ``index`` is the bar it happened on, never when we knew."""

    index: int
    kind: PivotKind
    price: Decimal
    confirmed_at: int
    prominence_atr: Decimal

    @property
    def is_high(self) -> bool:
        return self.kind is PivotKind.HIGH


def _true_range(bar: Bar, previous_close: Decimal) -> Decimal:
    return max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))


def atr_series(
    bars: Sequence[Bar],
    *,
    period: int,
    timeframe: Timeframe,
) -> tuple[Decimal | None, ...]:
    """Wilder ATR after each bar of ``bars`` (``None`` while warming up).

    The same recursion the upstream ``patterns/scale.py`` drives through the
    anchored checkpoint of ``features/atr.py``, unrolled here so this package
    owns its copy: the seed is the mean of the first ``period`` true ranges
    (complete on bar ``period``), the reading is released one smoothing step
    later (bar ``period + 1``), and every later bar applies
    ``ATR_i = (ATR_{i-1} * (period - 1) + TR_i) / period``.

    Raises on a non-contiguous window: ``bars[i]`` must open exactly one step
    after ``bars[i - 1]``.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if not bars:
        return ()
    step = timeframe_seconds(timeframe)
    values: list[Decimal | None] = [None]
    with localcontext(CONTEXT):
        seed_sum = Decimal(0)
        seed: Decimal | None = None
        value: Decimal | None = None
        for index, bar in enumerate(bars[1:], start=1):
            previous = bars[index - 1]
            if int((bar.open_time - previous.open_time).total_seconds()) != step:
                raise ValueError(
                    f"bars must be contiguous: {bar.open_time.isoformat()} (index {index}) "
                    "does not follow the previous bar"
                )
            true_range = _true_range(bar, previous.close)
            if index <= period:
                seed_sum += true_range
                if index == period:
                    seed = seed_sum / Decimal(period)
            else:
                base = value if value is not None else seed
                assert base is not None  # index > period implies the seed exists
                value = (base * (period - 1) + true_range) / Decimal(period)
            values.append(value)
    return tuple(values)


def _is_swing_high(bars: Sequence[Bar], index: int, k: int) -> bool:
    price = bars[index].high
    left = all(bars[j].high < price for j in range(index - k, index))
    right = all(bars[j].high <= price for j in range(index + 1, index + k + 1))
    return left and right


def _is_swing_low(bars: Sequence[Bar], index: int, k: int) -> bool:
    price = bars[index].low
    left = all(bars[j].low > price for j in range(index - k, index))
    right = all(bars[j].low >= price for j in range(index + 1, index + k + 1))
    return left and right


def _prominence(bars: Sequence[Bar], index: int, k: int, kind: PivotKind) -> Decimal:
    left = range(index - k, index)
    right = range(index + 1, index + k + 1)
    if kind is PivotKind.HIGH:
        shoulder = max(min(bars[j].low for j in left), min(bars[j].low for j in right))
        return bars[index].high - shoulder
    shoulder = min(max(bars[j].high for j in left), max(bars[j].high for j in right))
    return shoulder - bars[index].low


def find_pivots(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    *,
    k: int = DEFAULT_PIVOT_K,
    min_swing_atr: Decimal = DEFAULT_MIN_SWING_ATR,
    as_of: int | None = None,
) -> tuple[Pivot, ...]:
    """Confirmed, significant swings of ``bars[: as_of + 1]``, oldest first.

    ``atr`` must be the per-bar series of the same window (:func:`atr_series`).
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if len(atr) != len(bars):
        raise ValueError("the ATR series must have one entry per bar")
    cut = len(bars) - 1 if as_of is None else as_of
    if cut >= len(bars):
        raise ValueError(f"as_of {cut} is past the last bar ({len(bars) - 1})")
    found: list[Pivot] = []
    for index in range(k, cut - k + 1):
        scale = atr[index]
        if scale is None or scale <= 0:
            continue
        for kind, matches in (
            (PivotKind.HIGH, _is_swing_high(bars, index, k)),
            (PivotKind.LOW, _is_swing_low(bars, index, k)),
        ):
            if not matches:
                continue
            with localcontext(CONTEXT):
                prominence = _prominence(bars, index, k, kind) / scale
            if prominence < min_swing_atr:
                continue
            price = bars[index].high if kind is PivotKind.HIGH else bars[index].low
            found.append(
                Pivot(
                    index=index,
                    kind=kind,
                    price=price,
                    confirmed_at=index + k,
                    prominence_atr=prominence,
                )
            )
    return tuple(sorted(found))
