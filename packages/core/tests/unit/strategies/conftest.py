"""Deterministic synthetic series for the strategy unit tests.

Every number here is exact in ``Decimal``: a 15-minute bar is exploded into
fifteen 1-minute candles whose aggregate reproduces the bar exactly (the whole
range and the whole volume sit in the first minute, the remaining minutes are
flat at the close), so the expected ATR, medians and returns can be written by
hand instead of being read off the implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle

EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
ORIGIN = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
"""Epoch-aligned for every timeframe (1m, 5m, 15m)."""

D = Decimal


@dataclass(frozen=True, slots=True)
class BarSpec:
    """One aggregated bar to be exploded into 1-minute candles."""

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def minute(
    open_time: datetime,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    volume: Decimal,
    *,
    is_final: bool = True,
) -> NormalizedCandle:
    return NormalizedCandle(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        timeframe=Timeframe.M1,
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_final=is_final,
    )


def explode(spec: BarSpec, start: datetime, minutes: int) -> list[NormalizedCandle]:
    """``minutes`` 1-minute candles whose aggregate is exactly ``spec``."""
    candles = [
        minute(start, spec.open, spec.high, spec.low, spec.close, spec.volume),
    ]
    candles.extend(
        minute(start + timedelta(minutes=i), spec.close, spec.close, spec.close, spec.close, D(0))
        for i in range(1, minutes)
    )
    return candles


def series(
    specs: list[BarSpec], *, timeframe: Timeframe, origin: datetime = ORIGIN
) -> list[NormalizedCandle]:
    """1-minute candles for consecutive ``timeframe`` bars starting at ``origin``."""
    step = 5 if timeframe is Timeframe.M5 else 15
    candles: list[NormalizedCandle] = []
    for index, spec in enumerate(specs):
        candles.extend(explode(spec, origin + timedelta(minutes=index * step), step))
    return candles


def flat(close: Decimal, half_range: Decimal, volume: Decimal) -> BarSpec:
    """A bar that opens and closes at ``close`` with a symmetric range.

    ``true_range`` is exactly ``2 * half_range`` when the previous close is also
    ``close``: ``high - low`` dominates ``|high - prev_close|``.
    """
    return BarSpec(close, close + half_range, close - half_range, close, volume)
