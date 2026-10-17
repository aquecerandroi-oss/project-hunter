"""Intraday OHLC bars for the WIN family (H-039, H-040, H-041), as data.

A :class:`Bar` is a **final** bar: the retrospective MT5 export only carries closed bars,
and a live feed must pass only bars whose ``end`` has passed. ``start`` is the beginning
of the period (MQL5 ``MqlRates.time`` = "Period start time"), timezone-aware and normalised
to UTC. Prices are ``Decimal``. Nothing here reads a clock or does IO.

No look-ahead by construction: :func:`closed_prefix` keeps only bars that ended by ``t``,
and :func:`aggregate` only emits a bucket whose end is not after ``until`` — a bucket is
built from the 1-minute bars that start inside it, all of which have ended by its end.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_indicators.b3.contract import utc
from hunter_indicators.b3.intraday_plan import IntradayWindow


@dataclass(frozen=True, slots=True)
class Bar:
    start: datetime
    minutes: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", utc(self.start, "start"))
        if self.minutes < 1:
            raise ValueError("a bar lasts at least one minute")
        prices = (self.open, self.high, self.low, self.close)
        if any(not p.is_finite() or p <= 0 for p in prices):
            raise ValueError(f"OHLC must be positive finite Decimals at {self.start}")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError(f"inconsistent OHLC at {self.start}: {prices}")

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)


def closed_prefix(bars: Sequence[Bar], t: datetime) -> list[Bar]:
    """The bars of a time-sorted, non-overlapping series that ended at or before ``t``."""
    return list(bars[: bisect_right(bars, t, key=lambda b: b.end)])


def session_bars(bars: Sequence[Bar], window: IntradayWindow) -> list[Bar]:
    """The bars that start inside ``[open_at, exit_at)`` — the part a rule may read."""
    return [b for b in bars if window.open_at <= b.start < window.exit_at]


def _merge(members: Sequence[Bar], start: datetime, minutes: int) -> Bar:
    return Bar(
        start=start,
        minutes=minutes,
        open=members[0].open,
        high=max(m.high for m in members),
        low=min(m.low for m in members),
        close=members[-1].close,
    )


def bucket(bars: Sequence[Bar], *, start: datetime, minutes: int) -> Bar | None:
    """One aggregated bar from the source bars starting in ``[start, start + minutes)``."""
    end = start + timedelta(minutes=minutes)
    members = [b for b in bars if start <= b.start < end]
    return _merge(members, start, minutes) if members else None


def aggregate(
    bars: Sequence[Bar], *, anchor: datetime, minutes: int, until: datetime
) -> list[Bar | None]:
    """Buckets ``[anchor + m·j, anchor + m·(j+1))`` that end by ``until``; ``None`` if empty.

    Open = first bar's open, close = last bar's close, high/low = extremes, all from the
    source bars that **start** inside the bucket. A missing minute is never filled.
    """
    if minutes < 1:
        raise ValueError("bucket size must be at least one minute")
    step = timedelta(minutes=minutes)
    count = max(0, int((until - anchor) / step))
    buckets: list[list[Bar]] = [[] for _ in range(count)]
    for b in bars:
        if b.start < anchor:
            continue
        j = int((b.start - anchor) / step)
        if j < count:
            buckets[j].append(b)
    return [_merge(m, anchor + step * j, minutes) if m else None for j, m in enumerate(buckets)]
