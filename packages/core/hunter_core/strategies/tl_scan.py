"""Trend-line primitives, part 4: the frozen parameter record and the one cut.

Ported from ``hunter_indicators.patterns.scan`` (T3.34, upstream commit
``db798b8``); :mod:`hunter_core.strategies.tl_pivots` explains why the geometry
is copied instead of imported, and
``packages/core/tests/unit/strategies/test_tl_parity.py`` is what keeps the two
implementations numerically identical.

:func:`tl_scan` is the entry point and the **single place the anti-look-ahead cut
is applied**: the bars after ``as_of`` are dropped here, once, so no rule
downstream can accidentally read one. ``tl_scan(bars, as_of=i)`` therefore equals
``tl_scan(bars[: i + 1])`` for every ``i`` — the property a deliberate cheat
fails.

The parameters travel with the result (:class:`TlParams` inside :class:`TlScan`)
because a line drawn with ``min_touches = 2`` and one drawn with
``min_touches = 3`` are different claims about the same tape, and a stored
decision without its parameters cannot be reproduced.

**``retire_after_break`` is the one rule this copy adds** (T3.34b; correction 1
of KB-0077 — the reason for a copy rather than an edit upstream, which would
change figures already published). A line whose breakout is older than the retest
window stops being drawn at all: it is not a trigger, not a channel side and not
a number in the envelope. Declared consequence, because it is a real limit: the
retirement is applied *after* ``find_lines`` has already spent one of its
``max_lines`` slots on the retired line, so that slot is not handed to the next
candidate. Doing it inside the selection would change ``find_lines`` itself and
break parity with the research package; with ``retire_after_break = False`` the
two are identical, and that is the configuration the parity test runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import Any

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.tl_events import (
    DEFAULT_BOUNCE_ATR,
    DEFAULT_BOUNCE_BARS,
    DEFAULT_BREAK_ATR,
    DEFAULT_RETEST_BARS,
    EventKind,
    LineEvent,
    detect_events,
)
from hunter_core.strategies.tl_lines import (
    DEFAULT_ANGLE_BUCKET_ATR,
    DEFAULT_LEVEL_BUCKET_ATR,
    DEFAULT_MAX_ANCHORS,
    DEFAULT_MAX_LINES,
    DEFAULT_MIN_TOUCHES,
    DEFAULT_TOLERANCE_ATR,
    LineKind,
    TrendLine,
    find_lines,
)
from hunter_core.strategies.tl_pivots import (
    DEFAULT_MIN_SWING_ATR,
    DEFAULT_PIVOT_K,
    Pivot,
    atr_series,
    find_pivots,
)

__all__ = [
    "DEFAULT_MAX_CHANNELS",
    "DEFAULT_PARALLEL_TOL",
    "Channel",
    "TlParams",
    "TlScan",
    "find_channels",
    "tl_scan",
]

DEFAULT_PARALLEL_TOL = Decimal("0.05")
"""Slope difference, in ATR per bar, that still counts as parallel."""
DEFAULT_MAX_CHANNELS = 3


@dataclass(frozen=True, slots=True)
class Channel:
    """Two parallel lines with price between them, at bar ``at_idx``."""

    upper: TrendLine
    lower: TrendLine
    at_idx: int
    width_atr: Decimal


def find_channels(
    lines: Sequence[TrendLine],
    atr: Sequence[Decimal | None],
    *,
    parallel_tol: Decimal = DEFAULT_PARALLEL_TOL,
    max_channels: int = DEFAULT_MAX_CHANNELS,
    as_of: int | None = None,
) -> tuple[Channel, ...]:
    """Support/resistance pairs whose slopes agree to ``parallel_tol`` ATR per bar.

    A channel is only as knowable as the later of its two lines: both come from
    :func:`find_lines` at the same cut, so each already carries its own
    ``valid_from_idx`` and no new claim about the past is made here.
    """
    cut = len(atr) - 1 if as_of is None else as_of
    scale = atr[cut] if 0 <= cut < len(atr) else None
    if scale is None or scale <= 0:
        return ()
    uppers = [line for line in lines if line.kind is LineKind.RESISTANCE]
    lowers = [line for line in lines if line.kind is LineKind.SUPPORT]
    found: list[Channel] = []
    with localcontext(CONTEXT):
        for upper in uppers:
            for lower in lowers:
                if abs(upper.slope_per_bar - lower.slope_per_bar) > parallel_tol * scale:
                    continue
                width = upper.projected(cut) - lower.projected(cut)
                if width <= 0:
                    continue
                found.append(Channel(upper=upper, lower=lower, at_idx=cut, width_atr=width / scale))
    found.sort(key=lambda ch: (-(ch.upper.score + ch.lower.score), ch.width_atr))
    return tuple(found[:max_channels])


@dataclass(frozen=True, slots=True)
class TlParams:
    """Every threshold of the geometry, in one frozen record.

    All price thresholds are in ATRs; all windows are in bars. A stored line or
    a persisted decision carries :meth:`as_wire` with it, because a line drawn
    with ``min_touches = 2`` and one drawn with ``min_touches = 3`` are different
    claims about the same tape.
    """

    pivot_k: int = DEFAULT_PIVOT_K
    min_swing_atr: Decimal = DEFAULT_MIN_SWING_ATR
    atr_period: int = 14
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
    retire_after_break: bool = True

    def as_wire(self) -> dict[str, Any]:
        """Serialisable form — what a decision carries in its envelope."""
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
            "retire_after_break": self.retire_after_break,
        }


@dataclass(frozen=True, slots=True)
class TlScan:
    """What could be drawn on the chart at the close of bar ``as_of``."""

    as_of: int
    timeframe: Timeframe
    params: TlParams
    atr: tuple[Decimal | None, ...] = ()
    pivots: tuple[Pivot, ...] = ()
    lines: tuple[TrendLine, ...] = ()
    channels: tuple[Channel, ...] = ()
    events: tuple[LineEvent, ...] = field(default_factory=tuple)
    retired: tuple[str, ...] = ()
    """``line_id`` of every line dropped by ``retire_after_break`` — reported, so
    a decision log can say the line existed and why it was not a trigger."""


def _retired_ids(events: Sequence[LineEvent], cut: int, retest_bars: int) -> frozenset[str]:
    """Lines whose breakout is older than the retest window (T3.34b)."""
    return frozenset(
        event.line_id
        for event in events
        if event.kind is EventKind.BREAKOUT and event.index + retest_bars < cut
    )


def tl_scan(
    bars: Sequence[Bar],
    *,
    timeframe: Timeframe,
    params: TlParams,
    rvol: Sequence[Decimal | None] | None = None,
    as_of: int | None = None,
) -> TlScan:
    """Pivots, lines, channels and events of ``bars[: as_of + 1]``."""
    if not bars:
        raise ValueError("tl_scan needs at least one bar")
    cut = len(bars) - 1 if as_of is None else as_of
    if not 0 <= cut < len(bars):
        raise ValueError(f"as_of {cut} is outside the series (0..{len(bars) - 1})")
    window = bars[: cut + 1]
    volume_ratio = None if rvol is None else list(rvol[: cut + 1])
    atr = atr_series(window, period=params.atr_period, timeframe=timeframe)
    pivots = find_pivots(window, atr, k=params.pivot_k, min_swing_atr=params.min_swing_atr)
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
    retired = (
        _retired_ids(events, cut, params.retest_bars)
        if params.retire_after_break
        else frozenset[str]()
    )
    if retired:
        lines = tuple(line for line in lines if line.line_id not in retired)
        events = tuple(event for event in events if event.line_id not in retired)
    channels = find_channels(
        lines, atr, parallel_tol=params.parallel_tol, max_channels=params.max_channels
    )
    return TlScan(
        as_of=cut,
        timeframe=timeframe,
        params=params,
        atr=atr,
        pivots=pivots,
        lines=lines,
        channels=channels,
        events=events,
        retired=tuple(sorted(retired)),
    )
