"""What price does to a line: bounce, breakout, retest — decided at the close.

The life cycle of a line is a small state machine, and it runs forward only:

1. while the line holds, every bar whose extreme comes within ``tolerance_atr``
   of it and then closes ``bounce_atr`` away, within ``bounce_bars``, is a
   **bounce** — the evidence that the line is being respected;
2. the first close beyond it by more than ``break_atr`` is the **breakout**.
   When ``rvol_min`` is given, a break without relative volume is **not** an
   event: it is reported nowhere, because "it broke, quietly" is exactly the
   break that fails;
3. after a breakout, a bar that comes back within ``tolerance_atr`` of the line
   and closes again in the direction of the break, within ``retest_bars``, is
   the **retest**. Nothing after that: the line stops being a line once the
   market has left it, and a second break of the same geometry would be a new
   line drawn on new pivots.

Every event is decided **at the close of the bar it is stamped with** and never
before ``line.valid_from_idx`` — the bar the third touch was confirmed on. A
bounce found in the middle of the pivots that define the line would be a
memory, not a signal: nobody could have drawn that line yet.

A wick that goes *through* the line by more than the tolerance and closes back
is not a bounce here (it is a failed break, and naming it would let a strategy
buy a level that has just been pierced). That is a deliberate omission, listed
as a limit in the knowledge page.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum

from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.patterns.trendlines import LineKind, TrendLine

__all__ = [
    "DEFAULT_BOUNCE_ATR",
    "DEFAULT_BOUNCE_BARS",
    "DEFAULT_BREAK_ATR",
    "DEFAULT_RETEST_BARS",
    "BreakDirection",
    "EventKind",
    "LineEvent",
    "detect_events",
]

DEFAULT_BREAK_ATR = Decimal("0.5")
DEFAULT_BOUNCE_ATR = Decimal("0.5")
DEFAULT_TOLERANCE_ATR = Decimal("0.25")
DEFAULT_RETEST_BARS = 10
DEFAULT_BOUNCE_BARS = 3


class EventKind(StrEnum):
    BOUNCE = "bounce"
    BREAKOUT = "breakout"
    RETEST = "retest"


class BreakDirection(StrEnum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class LineEvent:
    """One thing that happened to one line, known at the close of ``index``."""

    kind: EventKind
    line_id: str
    index: int
    origin_idx: int
    direction: BreakDirection
    close: Decimal
    line_price: Decimal
    distance_atr: Decimal


def _direction(kind: LineKind) -> BreakDirection:
    return BreakDirection.UP if kind is LineKind.RESISTANCE else BreakDirection.DOWN


def _beyond(kind: LineKind, price: Decimal, level: Decimal) -> Decimal:
    """How far ``price`` is past the line in the direction a break would go."""
    return price - level if kind is LineKind.RESISTANCE else level - price


def _extreme(bar: Bar, kind: LineKind) -> Decimal:
    """The side of the bar that reaches for the line while it still holds."""
    return bar.high if kind is LineKind.RESISTANCE else bar.low


def _retest_extreme(bar: Bar, kind: LineKind) -> Decimal:
    """The side that reaches back after the break — polarity has reversed.

    Once price closed above a resistance line, it comes back **down** to it: the
    low is what touches. Using the same side as before the break would look for
    the retest on the wrong end of the candle and never find one.
    """
    return bar.low if kind is LineKind.RESISTANCE else bar.high


def _volume_confirms(
    index: int,
    rvol: Sequence[Decimal | None] | None,
    rvol_min: Decimal | None,
) -> bool:
    if rvol_min is None:
        return True
    if rvol is None or index >= len(rvol):
        return False
    value = rvol[index]
    return value is not None and value >= rvol_min


def _event(
    kind: EventKind,
    line: TrendLine,
    index: int,
    origin_idx: int,
    direction: BreakDirection,
    bars: Sequence[Bar],
    scale: Decimal,
) -> LineEvent:
    level = line.projected(index)
    with localcontext(CONTEXT):
        distance = abs(bars[index].close - level) / scale
    return LineEvent(
        kind=kind,
        line_id=line.line_id,
        index=index,
        origin_idx=origin_idx,
        direction=direction,
        close=bars[index].close,
        line_price=level,
        distance_atr=distance,
    )


def _bounce_confirmation(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    line: TrendLine,
    touch_idx: int,
    cut: int,
    bounce_atr: Decimal,
    bounce_bars: int,
    break_atr: Decimal,
) -> int | None:
    """The bar that confirms the bounce, or ``None`` — including when it breaks.

    A pending bounce is **cancelled** by a close through the line (Astra, T3.34
    review, must-fix 3). Without that, a touch at ``t``, a break at ``t+1`` and a
    recovery at ``t+2`` produced a bounce at ``t+2`` and the cursor jumped past
    the break: the breakout the market printed at ``t+1`` disappeared from the
    history, and only from the history — the live cut at ``t+1`` had reported it.
    """
    for index in range(touch_idx, min(touch_idx + bounce_bars, cut) + 1):
        scale = atr[index]
        if scale is None:
            continue
        past = _beyond(line.kind, bars[index].close, line.projected(index))
        if past > break_atr * scale:
            return None
        if -past >= bounce_atr * scale:
            return index
    return None


def _walk_until_break(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    line: TrendLine,
    cut: int,
    tolerance_atr: Decimal,
    break_atr: Decimal,
    bounce_atr: Decimal,
    bounce_bars: int,
    rvol: Sequence[Decimal | None] | None,
    rvol_min: Decimal | None,
) -> tuple[list[LineEvent], int | None]:
    events: list[LineEvent] = []
    index = line.valid_from_idx
    while index <= cut:
        scale = atr[index]
        if scale is None:
            index += 1
            continue
        level = line.projected(index)
        with localcontext(CONTEXT):
            past_close = _beyond(line.kind, bars[index].close, level)
            reach = abs(_extreme(bars[index], line.kind) - level)
            if past_close > break_atr * scale:
                if _volume_confirms(index, rvol, rvol_min):
                    events.append(
                        _event(
                            EventKind.BREAKOUT,
                            line,
                            index,
                            index,
                            _direction(line.kind),
                            bars,
                            scale,
                        )
                    )
                    return events, index
                index += 1
                continue
            touched = reach <= tolerance_atr * scale
        if touched:
            confirmed = _bounce_confirmation(
                bars, atr, line, index, cut, bounce_atr, bounce_bars, break_atr
            )
            if confirmed is not None:
                confirmed_scale = atr[confirmed]
                if confirmed_scale is not None:
                    events.append(
                        _event(
                            EventKind.BOUNCE,
                            line,
                            confirmed,
                            index,
                            BreakDirection.UP
                            if line.kind is LineKind.SUPPORT
                            else BreakDirection.DOWN,
                            bars,
                            confirmed_scale,
                        )
                    )
                index = confirmed + 1
                continue
        index += 1
    return events, None


def _retest(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    line: TrendLine,
    break_idx: int,
    cut: int,
    tolerance_atr: Decimal,
    retest_bars: int,
) -> LineEvent | None:
    touched: int | None = None
    for index in range(break_idx + 1, min(break_idx + retest_bars, cut) + 1):
        scale = atr[index]
        if scale is None:
            continue
        level = line.projected(index)
        with localcontext(CONTEXT):
            if touched is None and abs(_retest_extreme(bars[index], line.kind) - level) <= (
                tolerance_atr * scale
            ):
                touched = index
            back = _beyond(line.kind, bars[index].close, level)
        if touched is not None and back > 0:
            return _event(
                EventKind.RETEST, line, index, touched, _direction(line.kind), bars, scale
            )
    return None


def detect_events(
    bars: Sequence[Bar],
    atr: Sequence[Decimal | None],
    lines: Sequence[TrendLine],
    *,
    tolerance_atr: Decimal = DEFAULT_TOLERANCE_ATR,
    break_atr: Decimal = DEFAULT_BREAK_ATR,
    bounce_atr: Decimal = DEFAULT_BOUNCE_ATR,
    retest_bars: int = DEFAULT_RETEST_BARS,
    bounce_bars: int = DEFAULT_BOUNCE_BARS,
    rvol: Sequence[Decimal | None] | None = None,
    rvol_min: Decimal | None = None,
    as_of: int | None = None,
) -> tuple[LineEvent, ...]:
    """Every event of every line up to ``as_of``, in chronological order."""
    cut = len(bars) - 1 if as_of is None else as_of
    if cut >= len(bars):
        raise ValueError(f"as_of {cut} is past the last bar ({len(bars) - 1})")
    if len(atr) != len(bars):
        raise ValueError("the ATR series must have one entry per bar")
    found: list[LineEvent] = []
    for line in lines:
        events, break_idx = _walk_until_break(
            bars,
            atr,
            line,
            cut,
            tolerance_atr,
            break_atr,
            bounce_atr,
            bounce_bars,
            rvol,
            rvol_min,
        )
        found.extend(events)
        if break_idx is not None:
            retest = _retest(bars, atr, line, break_idx, cut, tolerance_atr, retest_bars)
            if retest is not None:
                found.append(retest)
    found.sort(key=lambda event: (event.index, event.line_id, event.kind.value))
    return tuple(found)
