"""1-minute candles -> 5m/15m bars, without look-ahead — SHADOW-LAB.md §7.

A strategy never sees a bar the market had not finished printing at
``source_bar_close``. This module is the only place that builds the higher
timeframe, and it refuses to guess:

- the window is **exactly** ``bars_needed`` buckets ending at ``source_bar_close``
  (which must sit on a bucket boundary), never a shorter one;
- every UTC minute inside that window must be present, exactly once and final —
  one missing minute makes the whole window unavailable with ``reason = "gap"``,
  because a bucket built from 14 of its 15 minutes is a different bar with the
  same name;
- candles after the cut are ignored, so a partial trailing bucket cannot exist;
- the reason travels with the empty result instead of being raised: "no window"
  is an ordinary market condition (warm-up, gap), and the worker logs it.

Non-final or non-1m input is a *contract* violation (the caller built the
context wrong) and raises.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle, is_aligned, timeframe_seconds
from hunter_core.strategies.numeric import CONTEXT

_MINUTE = timedelta(minutes=1)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Bar:
    """An aggregated OHLCV bar. Prices and volume are ``Decimal``, times are UTC."""

    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class Window:
    """``bars_needed`` aggregated bars, or the reason there are none."""

    bars: tuple[Bar, ...] = ()
    reason: str | None = None
    detail: Mapping[str, str] = field(default_factory=lambda: {})

    @property
    def available(self) -> bool:
        return self.reason is None


def _check_inputs(candles: Sequence[NormalizedCandle], bars_needed: int) -> None:
    if bars_needed < 1:
        raise ValueError("bars_needed must be >= 1")
    for candle in candles:
        if candle.timeframe is not Timeframe.M1:
            raise ValueError(f"aggregate() takes 1m candles, got {candle.timeframe}")
        if not candle.is_final:
            raise ValueError(
                f"aggregate() takes final candles only; {candle.open_time} is_final=False"
            )


def _fold(minutes: Sequence[NormalizedCandle], close_time: datetime) -> Bar:
    with localcontext(CONTEXT):  # the volume sum rounds under the ambient context otherwise
        volume = sum((candle.volume for candle in minutes), start=Decimal(0))
    return Bar(
        open_time=minutes[0].open_time,
        close_time=close_time,
        open=minutes[0].open,
        high=max(candle.high for candle in minutes),
        low=min(candle.low for candle in minutes),
        close=minutes[-1].close,
        volume=volume,
    )


def aggregate(
    candles: Sequence[NormalizedCandle],
    timeframe: Timeframe,
    source_bar_close: datetime,
    bars_needed: int,
) -> Window:
    """The last ``bars_needed`` ``timeframe`` bars ending at ``source_bar_close``.

    ``candles`` must be final 1-minute candles sorted by ``open_time``; anything
    at or after ``source_bar_close`` is ignored (the caller's cut is authoritative).
    """
    _check_inputs(candles, bars_needed)
    if not is_aligned(source_bar_close, timeframe):
        return Window(reason="misaligned", detail={"source_bar_close": _iso(source_bar_close)})

    span = timedelta(seconds=timeframe_seconds(timeframe) * bars_needed)
    window_start = source_bar_close - span
    by_minute = {
        candle.open_time: candle
        for candle in candles
        if window_start <= candle.open_time < source_bar_close
    }
    first_candle = min(by_minute) if by_minute else None
    if first_candle is None or first_candle > window_start:
        # "warm-up" means the history does not reach back far enough; if candles
        # exist *before* the window and the window's own first minutes are missing,
        # that is a hole and the worker may have to backfill or censor it.
        if any(candle.open_time < window_start for candle in candles):
            return Window(reason="gap", detail={"missing_minute": _iso(window_start)})
        return Window(
            reason="warmup",
            detail={
                "window_start": _iso(window_start),
                "first_candle": _iso(first_candle) if first_candle else "none",
            },
        )

    step = timedelta(seconds=timeframe_seconds(timeframe))
    bars: list[Bar] = []
    bucket_start = window_start
    while bucket_start < source_bar_close:
        bucket_end = bucket_start + step
        minutes: list[NormalizedCandle] = []
        cursor = bucket_start
        while cursor < bucket_end:
            candle = by_minute.get(cursor)
            if candle is None:
                return Window(reason="gap", detail={"missing_minute": _iso(cursor)})
            minutes.append(candle)
            cursor += _MINUTE
        bars.append(_fold(minutes, bucket_end))
        bucket_start = bucket_end

    return Window(bars=tuple(bars))
