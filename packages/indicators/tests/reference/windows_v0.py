"""FROZEN reference: ``features/windows.py`` as of commit ``551d542`` (pre-T2.2b).

Test-only. See ``tests/reference/__init__.py``: this file exists so
``test_engine_identity.py`` can run the feature engine on the old, un-memoised
window code and compare canonical bytes with the memoised one. It must never be
"improved" — a fix here would make the equivalence test compare the new code
with itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle, align_open_time
from hunter_core.strategies.aggregate import Bar, aggregate
from hunter_indicators.features.context import MISSING_INPUT, MarketContext, SourceEntry, TapeTrade
from hunter_indicators.features.vector import Reason

_MINUTE = timedelta(minutes=1)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _epoch_minutes(candles: Sequence[NormalizedCandle]) -> np.ndarray:
    return np.array(
        [int((c.open_time - _EPOCH).total_seconds()) // 60 for c in candles], dtype=np.int64
    )


def _contiguous_tail_length(candles: Sequence[NormalizedCandle]) -> int:
    """How many candles at the end of ``candles`` form an unbroken minute run."""
    if not candles:
        return 0
    minutes = _epoch_minutes(candles)
    steps = np.diff(minutes)
    broken = np.nonzero(steps != 1)[0]
    if broken.size == 0:
        return int(minutes.size)
    return int(minutes.size - (broken[-1] + 1))


@dataclass(frozen=True, slots=True)
class MinuteWindow:
    """``count`` contiguous final minutes, plus the forming candle when asked."""

    candles: tuple[NormalizedCandle, ...] = ()
    forming: NormalizedCandle | None = None
    reason: Reason | None = None

    @property
    def available(self) -> bool:
        return self.reason is None

    @property
    def last_close(self):
        """Close of the newest candle in the window (the forming one if included)."""
        if self.forming is not None:
            return self.forming.close
        return self.candles[-1].close if self.candles else None


def tail_minutes(ctx: MarketContext, count: int, *, include_forming: bool = False) -> MinuteWindow:
    """The last ``count`` contiguous final minutes of ``ctx``.

    ``include_forming`` adds the candle still printing — the ``_live`` path, and
    the only way a non-final candle ever reaches a calculation.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    candles = ctx.final_candles
    if not candles:
        return MinuteWindow(reason=Reason.MISSING_INPUT)
    forming = ctx.forming
    if include_forming and forming is None:
        return MinuteWindow(reason=Reason.MISSING_INPUT)
    run = _contiguous_tail_length(candles)
    if run < count:
        # history that never reached back is warm-up; a hole inside a history
        # that *does* reach back is a gap (aggregate.py's distinction).
        return MinuteWindow(reason=Reason.GAP if len(candles) > run else Reason.WARMUP)
    window = candles[-count:]
    if include_forming and forming is not None and forming.open_time != window[-1].close_time:
        return MinuteWindow(reason=Reason.GAP)
    return MinuteWindow(candles=window, forming=forming if include_forming else None)


@dataclass(frozen=True, slots=True)
class BarWindow:
    """Complete UTC bars of a higher timeframe, oldest first."""

    bars: tuple[Bar, ...] = ()
    timeframe: Timeframe = Timeframe.M15
    reason: Reason | None = None

    @property
    def available(self) -> bool:
        return self.reason is None


def bars_15m(ctx: MarketContext) -> BarWindow:
    """Every **complete** 15-minute UTC bar the contiguous minute tail supports.

    The last bar ends at the newest 15-minute boundary that had already closed
    at the newest final minute: a partial bucket is never emitted, so a bar the
    market had not finished printing cannot reach the ATR.
    """
    last = ctx.last_final
    if last is None:
        return BarWindow(reason=Reason.MISSING_INPUT)
    anchor = align_open_time(last.close_time, Timeframe.M15)
    usable = [c for c in ctx.final_candles if c.close_time <= anchor]
    run = _contiguous_tail_length(usable)
    bars_needed = run // 15
    if bars_needed < 1:
        return BarWindow(reason=Reason.WARMUP)
    window = aggregate(usable, Timeframe.M15, anchor, bars_needed)
    if not window.available:
        reason = {
            "gap": Reason.GAP,
            "warmup": Reason.WARMUP,
            "misaligned": Reason.MISALIGNED,
        }.get(window.reason or "", Reason.GAP)
        return BarWindow(reason=reason)
    return BarWindow(bars=window.bars)


@dataclass(frozen=True, slots=True)
class TradeWindow:
    trades: tuple[TapeTrade, ...] = ()
    reason: Reason | None = None

    @property
    def available(self) -> bool:
        return self.reason is None


def trades_between(
    entry: SourceEntry[tuple[TapeTrade, ...]], start: datetime, end: datetime
) -> TradeWindow:
    """Trades in ``(start, end]``, only when the window is **proven covered**.

    Half-open at the *start* so consecutive windows never count a trade twice,
    and inclusive at the end because ``end`` is the cut itself: a trade stamped
    exactly at ``as_of`` was observed and belongs to the current window.

    Coverage needs both ends: ``covers_from <= start`` (the tape reaches back far
    enough) **and** ``covered_until >= end`` (the collector proves it stayed
    connected through the window). The trades present prove neither — a quiet
    market and a dropped connection look identical from the tape, and a trade
    right before the cut only says the collector came back.

    ``covered_until`` is therefore supplied by the collector, not inferred here:
    until the scanner (T2.5) fills it from stream health, every trade window is
    ``insufficient_coverage``. That is the honest state, not a temporary bug.
    """
    if not entry.available or entry.value is None:
        return TradeWindow(
            reason=Reason.MISSING_INPUT if entry.reason == MISSING_INPUT else Reason.GAP
        )
    if entry.covers_from is None or entry.covers_from > start:
        return TradeWindow(reason=Reason.INSUFFICIENT_COVERAGE)
    if entry.covered_until is None or entry.covered_until < end:
        # The tape proves where it *starts*, never that the collector stayed
        # connected through the window: a trade at 12:00:55 after a reconnection
        # says nothing about 12:00:00-12:00:50 (Astra, T2.2 round 2). Only the
        # collector can prove continuity, and until it does there is no window —
        # neither a zero nor a count built on an unknown number of missed trades.
        return TradeWindow(reason=Reason.INSUFFICIENT_COVERAGE)
    tape = entry.value
    stamps = np.array(
        [int((t.ts - _EPOCH) / timedelta(microseconds=1)) for t in tape], dtype=np.int64
    )
    lo = int(np.searchsorted(stamps, int((start - _EPOCH) / timedelta(microseconds=1)), "right"))
    hi = int(np.searchsorted(stamps, int((end - _EPOCH) / timedelta(microseconds=1)), "right"))
    return TradeWindow(trades=tape[lo:hi])


__all__ = [
    "BarWindow",
    "MinuteWindow",
    "TradeWindow",
    "bars_15m",
    "tail_minutes",
    "trades_between",
]
