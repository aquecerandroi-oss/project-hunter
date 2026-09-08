"""Trend-line primitives, part 2: the lines themselves.

Ported from ``hunter_indicators.patterns.trendlines`` (T3.34, upstream commit ``db798b8``); see :mod:`hunter_core.strategies.tl_pivots`
for *why* the geometry is copied instead of imported, and
``packages/core/tests/unit/strategies/test_tl_parity.py`` for the test that keeps
the two implementations numerically identical.

The hand-drawn rule, made deterministic. A candidate is the straight line
through **two same-side pivots** (highs give resistance, lows give support). It
becomes a *line* when the tape has honoured it:

- **touches** — at least ``min_touches`` (3, the classic "two points draw it, the
  third confirms it") same-side pivots sit within ``tolerance_atr`` of it;
- **respected** — between the first and the last touch, no close is beyond it by
  more than ``tolerance_atr``. One close through the line is a wick; two are a
  different line;
- **score** ``touches * span - violations``, ``span`` being the bars between the
  first and last touch and ``violations`` the closes through the line **after**
  the first touch up to the cut. A line the market has already left ranks below
  one it is still respecting — while staying in the output, because the breakout
  of a line nobody can see is not a breakout.

Two anti-look-ahead facts are structural, not checks bolted on: only pivots whose
``confirmed_at`` has already happened can anchor or touch a line, and
``valid_from_idx`` — the **latest** of the confirmations of the two pivots that
fix the slope and of the ``min_touches``-th touch — is the first bar on which a
consumer may act on the line. The geometry of a line is history; its *existence*
has a date.

What this module does **not** promise: that the same line would have been
*selected* at ``valid_from_idx``. Scores, buckets and ``max_lines`` are evaluated
at the cut, so a late scan is a retrospective drawing of the lines that survive
today. A consumer that needs the live sequence scans once per bar with ``as_of``
on that bar — which is exactly what ``trendline_breakout_v1`` does.

The **relation** between two of these lines — the channel, whose width turns
"the target is the width of the channel" into a number — lives in
:mod:`hunter_core.strategies.tl_scan`, next to the cut that produces both sides.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum

from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.tl_pivots import Pivot, PivotKind

__all__ = [
    "DEFAULT_ANGLE_BUCKET_ATR",
    "DEFAULT_LEVEL_BUCKET_ATR",
    "DEFAULT_MAX_ANCHORS",
    "DEFAULT_MAX_LINES",
    "DEFAULT_MIN_TOUCHES",
    "DEFAULT_TOLERANCE_ATR",
    "LineKind",
    "TrendLine",
    "find_lines",
]

DEFAULT_MIN_TOUCHES = 3
DEFAULT_TOLERANCE_ATR = Decimal("0.25")
DEFAULT_ANGLE_BUCKET_ATR = Decimal("0.10")
DEFAULT_LEVEL_BUCKET_ATR = Decimal("0.50")
DEFAULT_MAX_ANCHORS = 20
DEFAULT_MAX_LINES = 6


class LineKind(StrEnum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


@dataclass(frozen=True, slots=True)
class TrendLine:
    """A straight line the market has touched ``touches`` times and respected."""

    line_id: str
    kind: LineKind
    origin: tuple[int, Decimal]
    """The first of the two pivots that fix the geometry — where the line *is*.

    Separate from ``anchors`` on purpose (Astra, T3.34 review, must-fix 1): a
    touch only has to sit within ``tolerance_atr`` of the line, so re-anchoring
    the projection on the earliest touch moved the whole line by up to a quarter
    ATR — enough to make the reported line fail the very respect test it had
    just passed (measured: 0.485 ATR of drift on the real 14-day series).
    """
    through: tuple[int, Decimal]
    """The second pivot of the pair. With ``origin`` it *is* the line."""
    anchors: tuple[tuple[int, Decimal], ...]
    slope_per_bar: Decimal
    touches: int
    first_idx: int
    last_idx: int
    valid_from_idx: int
    violations: int
    score: Decimal

    def projected(self, index: int) -> Decimal:
        """Where the line sits at ``index`` — before, between or after its anchors."""
        base_index, base_price = self.origin
        with localcontext(CONTEXT):
            return base_price + self.slope_per_bar * Decimal(index - base_index)


def _line_id(
    kind: LineKind,
    origin: tuple[int, Decimal],
    through: tuple[int, Decimal],
    slope: Decimal,
    anchors: Sequence[tuple[int, Decimal]],
) -> str:
    """Identity = the geometry **and** the touches that earned it.

    The geometry is in the digest because two lines can share a touch set and
    still be different lines; the touches are in it because a line that gains a
    fourth touch is a new claim about the same tape.
    """
    payload = {
        "kind": kind.value,
        "origin": {"index": origin[0], "price": origin[1]},
        "through": {"index": through[0], "price": through[1]},
        "slope_per_bar": slope,
        "anchors": [{"index": index, "price": price} for index, price in anchors],
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()[:16]


def _price_at(base: tuple[int, Decimal], slope: Decimal, index: int) -> Decimal:
    return base[1] + slope * Decimal(index - base[0])


def _kind_of(pivot: Pivot) -> LineKind:
    return LineKind.RESISTANCE if pivot.kind is PivotKind.HIGH else LineKind.SUPPORT


def _quantize(value: Decimal, bucket: Decimal) -> Decimal:
    return (value / bucket).to_integral_value(rounding=ROUND_HALF_EVEN)


def _violations(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    kind: LineKind,
    base: tuple[int, Decimal],
    slope: Decimal,
    start: int,
    end: int,
    tolerance_atr: Decimal,
) -> int:
    count = 0
    for index in range(start, end + 1):
        scale = atr[index]
        if scale is None:
            continue
        level = _price_at(base, slope, index)
        room = tolerance_atr * scale
        close = bars[index].close
        if kind is LineKind.RESISTANCE and close - level > room:
            count += 1
        elif kind is LineKind.SUPPORT and level - close > room:
            count += 1
    return count


def _build(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    kind: LineKind,
    pair: tuple[Pivot, Pivot],
    same_side: Sequence[Pivot],
    cut: int,
    min_touches: int,
    tolerance_atr: Decimal,
) -> TrendLine | None:
    first, second = pair
    with localcontext(CONTEXT):
        slope = (second.price - first.price) / Decimal(second.index - first.index)
        base = (first.index, first.price)
        through = (second.index, second.price)
        touching: list[Pivot] = []
        for pivot in same_side:
            scale = atr[pivot.index]
            if scale is None:
                continue
            if abs(pivot.price - _price_at(base, slope, pivot.index)) <= tolerance_atr * scale:
                touching.append(pivot)
        if len(touching) < min_touches:
            return None
        first_idx, last_idx = touching[0].index, touching[-1].index
        inside = _violations(bars, atr, kind, base, slope, first_idx, last_idx, tolerance_atr)
        if inside:
            return None
        violations = _violations(bars, atr, kind, base, slope, first_idx, cut, tolerance_atr)
        anchors = tuple((pivot.index, pivot.price) for pivot in touching)
        score = Decimal(len(touching) * (last_idx - first_idx) - violations)
    # A line exists when the tape has confirmed BOTH the pivots that fix its slope
    # and the ``min_touches``-th touch. Taking only the touch (Astra, T3.34 review,
    # must-fix 2) let a line whose slope came from pivots at bars 310 and 323 claim
    # to have been valid since bar 232 — and every event searched from that bar was
    # then measured against a slope from the future.
    valid_from = max(
        touching[min_touches - 1].confirmed_at, first.confirmed_at, second.confirmed_at
    )
    return TrendLine(
        line_id=_line_id(kind, base, through, slope, anchors),
        kind=kind,
        origin=base,
        through=through,
        anchors=anchors,
        slope_per_bar=slope,
        touches=len(touching),
        first_idx=first_idx,
        last_idx=last_idx,
        valid_from_idx=valid_from,
        violations=violations,
        score=score,
    )


def _rank(line: TrendLine) -> tuple[Decimal, int, int, int, int, str]:
    """Best first. ``valid_from_idx`` breaks ties **before** the digest does.

    Two pivot pairs can produce the same geometry with the same touches — the
    synthetic wave does exactly that — and then the only honest preference is the
    one that could have been drawn **earlier**. Falling through to ``line_id``
    would pick by hash, which is deterministic and meaningless.
    """
    return (
        -line.score,
        -line.touches,
        line.first_idx - line.last_idx,
        line.valid_from_idx,
        line.first_idx,
        line.line_id,
    )


def _dedupe(
    candidates: Sequence[TrendLine],
    scale: Decimal,
    cut: int,
    angle_bucket_atr: Decimal,
    level_bucket_atr: Decimal,
    max_lines: int,
) -> tuple[TrendLine, ...]:
    """One line per (kind, angle bucket, level bucket); the best-scoring one wins.

    Buckets are in ATRs, not in price: 0.10 ATR per bar of slope difference and
    0.50 ATR of distance at the cut. Two lines a human would have drawn as one
    are one; two he would have drawn separately keep their identity.
    """
    best: dict[tuple[str, Decimal, Decimal], TrendLine] = {}
    with localcontext(CONTEXT):
        for line in sorted(candidates, key=_rank):
            key = (
                line.kind.value,
                _quantize(line.slope_per_bar / scale, angle_bucket_atr),
                _quantize(line.projected(cut) / scale, level_bucket_atr),
            )
            if key not in best:
                best[key] = line
    kept: list[TrendLine] = []
    for line in sorted(best.values(), key=_rank):
        anchors = {index for index, _price in line.anchors}
        if any(anchors <= {index for index, _p in other.anchors} for other in kept):
            continue
        kept.append(line)
    return tuple(kept[:max_lines])


def find_lines(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    pivots: Sequence[Pivot],
    *,
    min_touches: int = DEFAULT_MIN_TOUCHES,
    tolerance_atr: Decimal = DEFAULT_TOLERANCE_ATR,
    angle_bucket_atr: Decimal = DEFAULT_ANGLE_BUCKET_ATR,
    level_bucket_atr: Decimal = DEFAULT_LEVEL_BUCKET_ATR,
    max_anchors: int = DEFAULT_MAX_ANCHORS,
    max_lines: int = DEFAULT_MAX_LINES,
    as_of: int | None = None,
) -> tuple[TrendLine, ...]:
    """Valid, non-redundant lines known at ``as_of``, best score first."""
    if min_touches < 2:
        raise ValueError("a line needs at least two points")
    cut = len(bars) - 1 if as_of is None else as_of
    if cut >= len(bars):
        raise ValueError(f"as_of {cut} is past the last bar ({len(bars) - 1})")
    scale = atr[cut] if cut < len(atr) else None
    if scale is None or scale <= 0:
        return ()
    known = [pivot for pivot in pivots if pivot.confirmed_at <= cut]
    candidates: list[TrendLine] = []
    for kind in (LineKind.SUPPORT, LineKind.RESISTANCE):
        same_side = [pivot for pivot in known if _kind_of(pivot) is kind]
        anchors = same_side[-max_anchors:]
        for left in range(len(anchors) - 1):
            for right in range(left + 1, len(anchors)):
                line = _build(
                    bars,
                    atr,
                    kind,
                    (anchors[left], anchors[right]),
                    same_side,
                    cut,
                    min_touches,
                    tolerance_atr,
                )
                if line is not None and line.valid_from_idx <= cut:
                    candidates.append(line)
    return _dedupe(candidates, scale, cut, angle_bucket_atr, level_bucket_atr, max_lines)
