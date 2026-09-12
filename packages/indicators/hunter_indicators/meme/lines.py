"""The lines Everton draws by hand, as features computed over a closed minute
(T4.10, EXP-M2 — "você é obrigado a usar traçamento de linha").

Everything here is a pure function of the curve snapshots of the last ``W``
minutes (``W = 15``) and the market cap of the minute being folded:

- ``support_line_sol`` / ``support_line_slope`` / ``higher_lows`` — the straight
  line through the **last two local lows** of the window (a low is a point whose
  two neighbours are both higher), evaluated at ``end_time``; its slope in SOL
  per minute; and whether the second low sits above the first;
- ``distance_to_support_pct`` — ``(mcap_now − support) / support``;
- ``high_15m_sol`` / ``low_15m_sol`` — the extremes of the window;
- ``breakout_15m`` — ``mcap_now >= high`` of the **previous** window
  ``(end_time − 16 min, end_time − 1 min]``, so the minute being folded can
  never be its own reference;
- ``mcap_slope_5m`` / ``mcap_slope_15m`` — the ordinary least squares slope of
  ``ln(mcap)`` against minutes, a growth fraction per minute.

**Non-anticipation is decided here.** Every point carries ``received_at`` and a
point that reached us after ``end_time`` is not an input of that minute, however
early its ``observed_at`` says the curve was read — the same rule the tape and
the boards follow (``features_tape.py``). ``test_meme_lines.py`` proves it: a
point inside the window received one second after the close changes nothing.

Every ``None`` has a name (``line_reason``): ``no_snapshot`` (the minute has no
market cap of its own), ``too_few_points`` (fewer than ``MIN_POINTS`` usable
photos in the window), ``flat`` (no two local lows — a monotone or single-dip
series has no line to draw), ``out_of_range`` (the line exists but a value does
not fit its column, e.g. a support at or below zero). The first two blank every
column; the last two blank only the support group, because the window's
extremes and slopes are still facts.

Numerics: the regression runs on floats (a window in memory, never money); the
support line, the distance and the extremes are ``Decimal`` because they are
persisted next to SOL amounts.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Final

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.definitions import FeatureDefinition

__all__ = [
    "FLAT",
    "LINE_DEFINITIONS",
    "LINE_REASONS",
    "MIN_POINTS",
    "NO_SNAPSHOT",
    "OUT_OF_RANGE",
    "TOO_FEW_POINTS",
    "WINDOW_MINUTES",
    "LineFeatures",
    "LinePoint",
    "compute_lines",
    "local_lows",
    "log_slope",
    "usable_points",
]

WINDOW_MINUTES: Final = 15
MIN_POINTS: Final = 5
"""The brief's frozen parameters: a 15-minute window and at least five photos."""

NO_SNAPSHOT: Final = "no_snapshot"
TOO_FEW_POINTS: Final = "too_few_points"
FLAT: Final = "flat"
OUT_OF_RANGE: Final = "out_of_range"
LINE_REASONS: Final = frozenset({NO_SNAPSHOT, TOO_FEW_POINTS, FLAT, OUT_OF_RANGE})

_MONEY = Decimal("0.0000000001")
_SIX = Decimal("0.000001")
_SLOPE_LIMIT = Decimal(10) ** 6
"""``numeric(12, 6)`` holds less than a million in magnitude."""
_DISTANCE_LIMIT = Decimal(10) ** 3
"""``numeric(9, 6)`` holds less than a thousand in magnitude."""

_INPUTS: Final = (
    "meme_curve_snapshots.mcap_sol",
    "meme_curve_snapshots.observed_at",
    "meme_curve_snapshots.received_at",
    "meme_features_1m.mcap_sol",
)
_WINDOW_PARAMS: Final = {"window_minutes": WINDOW_MINUTES, "min_points": MIN_POINTS}


def _definition(
    key: str, category: FeatureCategory, description: str, **params: object
) -> FeatureDefinition:
    return FeatureDefinition(
        key=key,
        version=1,
        category=category,
        inputs=_INPUTS,
        description=description,
        params={**_WINDOW_PARAMS, **params},
    )


LINE_DEFINITIONS: Final[tuple[FeatureDefinition, ...]] = (
    _definition(
        "mcap_slope_5m",
        FeatureCategory.MOMENTUM,
        "OLS slope of ln(mcap_sol) against minutes over the last 5 minutes (fraction/min).",
        regression_minutes=5,
        min_regression_points=2,
    ),
    _definition(
        "mcap_slope_15m",
        FeatureCategory.MOMENTUM,
        "OLS slope of ln(mcap_sol) against minutes over the window (fraction/min).",
        regression_minutes=WINDOW_MINUTES,
        min_regression_points=2,
    ),
    _definition("high_15m_sol", FeatureCategory.PRICE, "Highest mcap_sol in the window."),
    _definition("low_15m_sol", FeatureCategory.PRICE, "Lowest mcap_sol in the window."),
    _definition(
        "breakout_15m",
        FeatureCategory.PRICE,
        "mcap_now >= the highest mcap_sol of the previous window (end_time - 1 min and earlier).",
        reference_window="(end_time - 16 min, end_time - 1 min]",
    ),
    _definition(
        "support_line_sol",
        FeatureCategory.PRICE,
        "Value at end_time of the line through the last two local lows of the window.",
        low="strictly below both neighbours",
    ),
    _definition(
        "support_line_slope", FeatureCategory.PRICE, "Slope of the support line, SOL per minute."
    ),
    _definition(
        "higher_lows", FeatureCategory.PRICE, "The second of the last two lows is above the first."
    ),
    _definition(
        "distance_to_support_pct",
        FeatureCategory.PRICE,
        "(mcap_now - support_line_sol) / support_line_sol, a fraction.",
    ),
)
"""One registration per column of ``meme_features_1m`` (``0026``). A different
formula is version 2 and a different ``features_version``, never an edit."""


@dataclass(frozen=True, slots=True)
class LinePoint:
    """One curve photo as the lines read it. ``mcap_sol`` may be ``None``
    (a snapshot the generated column could not price) — such a point is not
    usable, and it is not a zero."""

    observed_at: datetime
    received_at: datetime
    mcap_sol: Decimal | None


@dataclass(frozen=True, slots=True)
class LineFeatures:
    """The nine columns plus the count and the reason — one row's worth."""

    mcap_slope_5m: Decimal | None
    mcap_slope_15m: Decimal | None
    high_15m_sol: Decimal | None
    low_15m_sol: Decimal | None
    breakout_15m: bool | None
    support_line_sol: Decimal | None
    support_line_slope: Decimal | None
    higher_lows: bool | None
    distance_to_support_pct: Decimal | None
    line_points: int
    line_reason: str | None


_BLANK = {
    "mcap_slope_5m": None,
    "mcap_slope_15m": None,
    "high_15m_sol": None,
    "low_15m_sol": None,
    "breakout_15m": None,
}
_NO_SUPPORT = {
    "support_line_sol": None,
    "support_line_slope": None,
    "higher_lows": None,
    "distance_to_support_pct": None,
}


def usable_points(
    points: Sequence[LinePoint],
    *,
    end_time: datetime,
    start_offset: timedelta,
    end_offset: timedelta,
) -> list[LinePoint]:
    """Points in ``(end_time − start_offset, end_time − end_offset]`` that had
    **reached us** by ``end_time`` and carry a positive market cap, sorted by
    ``observed_at``, one per instant (the last received wins)."""
    start, stop = end_time - start_offset, end_time - end_offset
    by_instant: dict[datetime, LinePoint] = {}
    for point in sorted(points, key=lambda p: (p.observed_at, p.received_at)):
        if point.received_at > end_time or point.mcap_sol is None or point.mcap_sol <= 0:
            continue
        if start < point.observed_at <= stop:
            by_instant[point.observed_at] = point
    return [by_instant[instant] for instant in sorted(by_instant)]


def _minutes(later: datetime, earlier: datetime) -> Decimal:
    return Decimal(str((later - earlier).total_seconds())) / Decimal(60)


def log_slope(points: Sequence[LinePoint], *, origin: datetime) -> Decimal | None:
    """OLS slope of ``ln(mcap)`` against minutes since ``origin``; ``None`` with
    fewer than two distinct instants. Floats inside, ``Decimal`` at the door."""
    xs = [float(_minutes(p.observed_at, origin)) for p in points]
    ys = [math.log(float(p.mcap_sol)) for p in points if p.mcap_sol is not None]
    if len(xs) < 2 or len(set(xs)) < 2:
        return None
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = Decimal(repr(sxy / sxx)).quantize(_SIX, rounding=ROUND_HALF_EVEN)
    return None if abs(slope) >= _SLOPE_LIMIT else slope


def local_lows(points: Sequence[LinePoint]) -> list[LinePoint]:
    """Points strictly below both neighbours, in time order. Ends never qualify."""
    lows: list[LinePoint] = []
    for i in range(1, len(points) - 1):
        left, here, right = points[i - 1].mcap_sol, points[i].mcap_sol, points[i + 1].mcap_sol
        assert left is not None and here is not None and right is not None
        if left > here < right:
            lows.append(points[i])
    return lows


def _support(
    lows: Sequence[LinePoint], *, end_time: datetime, mcap_now: Decimal
) -> tuple[dict[str, object], str | None]:
    first, second = lows[-2], lows[-1]
    assert first.mcap_sol is not None and second.mcap_sol is not None
    with localcontext(CONTEXT):
        slope = (second.mcap_sol - first.mcap_sol) / _minutes(second.observed_at, first.observed_at)
        support = second.mcap_sol + slope * _minutes(end_time, second.observed_at)
        if support <= 0:
            return dict(_NO_SUPPORT), OUT_OF_RANGE
        distance = (mcap_now - support) / support
    slope_q = slope.quantize(_SIX, rounding=ROUND_HALF_EVEN)
    distance_q = distance.quantize(_SIX, rounding=ROUND_HALF_EVEN)
    if abs(slope_q) >= _SLOPE_LIMIT or abs(distance_q) >= _DISTANCE_LIMIT:
        return dict(_NO_SUPPORT), OUT_OF_RANGE
    return {
        "support_line_sol": support.quantize(_MONEY, rounding=ROUND_HALF_EVEN),
        "support_line_slope": slope_q,
        "higher_lows": second.mcap_sol > first.mcap_sol,
        "distance_to_support_pct": distance_q,
    }, None


def compute_lines(
    points: Sequence[LinePoint], *, end_time: datetime, mcap_now: Decimal | None
) -> LineFeatures:
    """Fold the window that ends at ``end_time``. Total: every input yields a row."""
    minute = timedelta(minutes=1)
    window = usable_points(
        points,
        end_time=end_time,
        start_offset=timedelta(minutes=WINDOW_MINUTES),
        end_offset=timedelta(0),
    )
    count = len(window)
    if mcap_now is None or mcap_now <= 0:
        return LineFeatures(**_BLANK, **_NO_SUPPORT, line_points=count, line_reason=NO_SNAPSHOT)  # type: ignore[arg-type]
    if count < MIN_POINTS:
        return LineFeatures(**_BLANK, **_NO_SUPPORT, line_points=count, line_reason=TOO_FEW_POINTS)  # type: ignore[arg-type]
    previous = usable_points(
        points,
        end_time=end_time,
        start_offset=timedelta(minutes=WINDOW_MINUTES + 1),
        end_offset=minute,
    )
    previous_high = max((p.mcap_sol for p in previous if p.mcap_sol is not None), default=None)
    recent = [p for p in window if p.observed_at > end_time - timedelta(minutes=5)]
    highs = [p.mcap_sol for p in window if p.mcap_sol is not None]
    columns: dict[str, object] = {
        "mcap_slope_5m": log_slope(recent, origin=end_time - timedelta(minutes=5)),
        "mcap_slope_15m": log_slope(window, origin=end_time - timedelta(minutes=WINDOW_MINUTES)),
        "high_15m_sol": max(highs).quantize(_MONEY, rounding=ROUND_HALF_EVEN),
        "low_15m_sol": min(highs).quantize(_MONEY, rounding=ROUND_HALF_EVEN),
        "breakout_15m": None if previous_high is None else mcap_now >= previous_high,
    }
    lows = local_lows(window)
    if len(lows) < 2:
        return LineFeatures(**columns, **_NO_SUPPORT, line_points=count, line_reason=FLAT)  # type: ignore[arg-type]
    support, reason = _support(lows, end_time=end_time, mcap_now=mcap_now)
    return LineFeatures(**columns, **support, line_points=count, line_reason=reason)  # type: ignore[arg-type]
