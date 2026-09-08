"""One call, one cut: the whole geometry of a market as of bar ``as_of``.

This is the entry point a strategy, a chart or a plotting script uses, and the
single place the anti-look-ahead cut is applied. Everything downstream sees a
window that **ends** at ``as_of``: the bars after it are dropped here, once, so
no rule can accidentally read one. ``scan(bars, as_of=i)`` is therefore equal to
``scan(bars[: i + 1])`` for every ``i`` — the property
``tests/patterns/test_no_lookahead.py`` proves over random walks, and the one a
deliberate cheat fails.

The parameters travel with the result (:class:`PatternParams` inside
:class:`PatternScan`), because a line drawn with ``min_touches = 2`` and one
drawn with ``min_touches = 3`` are different claims about the same tape and a
stored picture without its parameters cannot be reproduced.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.features.atr import ATR_PERIOD
from hunter_indicators.patterns.channels import (
    DEFAULT_MAX_CHANNELS,
    DEFAULT_PARALLEL_TOL,
    Channel,
    find_channels,
)
from hunter_indicators.patterns.events import (
    DEFAULT_BOUNCE_ATR,
    DEFAULT_BOUNCE_BARS,
    DEFAULT_BREAK_ATR,
    DEFAULT_RETEST_BARS,
    LineEvent,
    detect_events,
)
from hunter_indicators.patterns.pivots import Pivot, find_pivots
from hunter_indicators.patterns.scale import atr_series
from hunter_indicators.patterns.trendlines import (
    DEFAULT_ANGLE_BUCKET_ATR,
    DEFAULT_LEVEL_BUCKET_ATR,
    DEFAULT_MAX_ANCHORS,
    DEFAULT_MAX_LINES,
    DEFAULT_MIN_TOUCHES,
    DEFAULT_TOLERANCE_ATR,
    TrendLine,
    find_lines,
)

__all__ = ["DEFAULT_PARAMS", "PatternParams", "PatternScan", "scan"]


@dataclass(frozen=True, slots=True)
class PatternParams:
    """Every threshold of the package, in one frozen record.

    All price thresholds are in ATRs; all windows are in bars. Defaults are the
    ones the T3.34 brief fixed, and changing one is a new parameter set, not an
    edit of a picture already drawn.
    """

    pivot_k: int = 3
    min_swing_atr: Decimal = Decimal("1.0")
    atr_period: int = ATR_PERIOD
    min_touches: int = DEFAULT_MIN_TOUCHES
    tolerance_atr: Decimal = DEFAULT_TOLERANCE_ATR
    break_atr: Decimal = DEFAULT_BREAK_ATR
    bounce_atr: Decimal = DEFAULT_BOUNCE_ATR
    retest_bars: int = DEFAULT_RETEST_BARS
    bounce_bars: int = DEFAULT_BOUNCE_BARS
    parallel_tol: Decimal = DEFAULT_PARALLEL_TOL
    angle_bucket_atr: Decimal = DEFAULT_ANGLE_BUCKET_ATR
    level_bucket_atr: Decimal = DEFAULT_LEVEL_BUCKET_ATR
    max_anchors: int = DEFAULT_MAX_ANCHORS
    max_lines: int = DEFAULT_MAX_LINES
    max_channels: int = DEFAULT_MAX_CHANNELS
    rvol_min: Decimal | None = None

    def as_wire(self) -> dict[str, Any]:
        """Serialisable form — what a stored line or picture carries with it."""
        return {
            "pivot_k": self.pivot_k,
            "min_swing_atr": self.min_swing_atr,
            "atr_period": self.atr_period,
            "min_touches": self.min_touches,
            "tolerance_atr": self.tolerance_atr,
            "break_atr": self.break_atr,
            "bounce_atr": self.bounce_atr,
            "retest_bars": self.retest_bars,
            "bounce_bars": self.bounce_bars,
            "parallel_tol": self.parallel_tol,
            "angle_bucket_atr": self.angle_bucket_atr,
            "level_bucket_atr": self.level_bucket_atr,
            "max_anchors": self.max_anchors,
            "max_lines": self.max_lines,
            "max_channels": self.max_channels,
            "rvol_min": self.rvol_min,
        }


DEFAULT_PARAMS = PatternParams()


@dataclass(frozen=True, slots=True)
class PatternScan:
    """What could be drawn on the chart at the close of bar ``as_of``."""

    as_of: int
    timeframe: Timeframe
    params: PatternParams
    atr: tuple[Decimal | None, ...] = ()
    pivots: tuple[Pivot, ...] = ()
    lines: tuple[TrendLine, ...] = ()
    channels: tuple[Channel, ...] = ()
    events: tuple[LineEvent, ...] = field(default_factory=tuple)


def scan(
    bars: Sequence[Bar],
    *,
    timeframe: Timeframe,
    params: PatternParams = DEFAULT_PARAMS,
    rvol: Sequence[Decimal | None] | None = None,
    as_of: int | None = None,
) -> PatternScan:
    """Pivots, lines, channels and events of ``bars[: as_of + 1]``."""
    if not bars:
        raise ValueError("scan needs at least one bar")
    cut = len(bars) - 1 if as_of is None else as_of
    if not 0 <= cut < len(bars):
        raise ValueError(f"as_of {cut} is outside the series (0..{len(bars) - 1})")
    window = bars[: cut + 1]
    volume_ratio = None if rvol is None else list(rvol[: cut + 1])
    atr = atr_series(window, period=params.atr_period, timeframe=timeframe)
    pivots = find_pivots(
        window,
        atr,
        k=params.pivot_k,
        min_swing_atr=params.min_swing_atr,
    )
    lines = find_lines(
        window,
        atr,
        pivots,
        min_touches=params.min_touches,
        tolerance_atr=params.tolerance_atr,
        angle_bucket_atr=params.angle_bucket_atr,
        level_bucket_atr=params.level_bucket_atr,
        max_anchors=params.max_anchors,
        max_lines=params.max_lines,
    )
    channels = find_channels(
        lines,
        atr,
        parallel_tol=params.parallel_tol,
        max_channels=params.max_channels,
    )
    events = detect_events(
        window,
        atr,
        lines,
        tolerance_atr=params.tolerance_atr,
        break_atr=params.break_atr,
        bounce_atr=params.bounce_atr,
        retest_bars=params.retest_bars,
        bounce_bars=params.bounce_bars,
        rvol=volume_ratio,
        rvol_min=params.rvol_min,
    )
    return PatternScan(
        as_of=cut,
        timeframe=timeframe,
        params=params,
        atr=atr,
        pivots=pivots,
        lines=lines,
        channels=channels,
        events=events,
    )
