"""Swing highs and lows — the anchors every trend line is drawn through.

Three rules, and each one exists because dropping it produces a line a human
would not have drawn:

1. **a confirmation window ``k``**: a bar is a swing high when its high is the
   highest of the ``k`` bars on each side. The right-hand side is the whole
   point: a pivot is only *known* ``k`` bars later, and :attr:`Pivot.confirmed_at`
   carries that index so no consumer can anchor a decision on the bar itself;
2. **an ATR-scaled significance filter**: prominence — the depth of the trough
   measured against the lower of its two flanking peaks (the topographic
   definition, over the ``k`` neighbours on each side, the pivot bar itself
   excluded so its own range cannot vouch for it) — must reach ``min_swing_atr``
   ATRs. Without it every wiggle of a tape that has just gone quiet is a "swing"
   and the lines drawn through them mean nothing;
3. **ties go to the older bar**: strictly greater than the left side, greater
   or equal on the right, so a plateau yields one pivot instead of three.

A bar whose ATR has not warmed up yet cannot pass rule 2 and is therefore not a
pivot. That is a refusal, not a gap: the alternative is to invent a scale.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from hunter_core.strategies.aggregate import Bar

__all__ = ["Pivot", "PivotKind", "find_pivots"]


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
    k: int = 3,
    min_swing_atr: Decimal = Decimal("1.0"),
    as_of: int | None = None,
) -> tuple[Pivot, ...]:
    """Confirmed, significant swings of ``bars[: as_of + 1]``, oldest first.

    ``atr`` must be the per-bar series of the same window (:mod:`scale`).
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
