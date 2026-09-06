"""The candles one replayed entry is folded over, and the cut that bounds them.

Split from :mod:`.engine` along the right seam: this module answers *what data
does this entry get to see*, that one answers *what the policy does with it*.

The cut is the whole point. ``as_of`` is a **data cut**, not just a filter on
which decisions enter the population: nothing after the last minute that had
closed by ``as_of`` reaches the fold, history included. Otherwise a run "as of
17:00" would resolve a 20:00 horizon with candles the cut says it cannot see,
and "matured at the cut" would mean nothing (Astra, R1 diff review).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.market import NormalizedCandle
from hunter_strategy_worker.outcomes import last_closed_minute
from hunter_strategy_worker.repo import load_candles
from hunter_strategy_worker.walker import Bar

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.replay.load import ReplayCase

__all__ = ["MINUTE", "Series", "load_series"]

MINUTE = timedelta(minutes=1)
_CHANNEL_HISTORY_BARS = 12
"""15m bars loaded before the entry so the channel's own window is complete."""


@dataclass(frozen=True, slots=True)
class Series:
    """The candles one case is replayed over."""

    candles: tuple[NormalizedCandle, ...]
    """Everything loaded, history included — the channel aggregates over it."""
    bars: tuple[Bar, ...]
    """The contiguous 1m prefix from the entry bar, at most up to the horizon."""
    truncated: str | None
    """Why the prefix stops short of the horizon open, if it does."""


def _bar(candle: NormalizedCandle) -> Bar:
    return Bar(
        open_time=candle.open_time,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
    )


def _prefix(candles: Sequence[NormalizedCandle], start: datetime, end: datetime) -> list[Bar]:
    """Contiguous 1m bars from ``start`` up to and including ``end``."""
    by_minute = {candle.open_time: candle for candle in candles}
    bars: list[Bar] = []
    cursor = start
    while cursor <= end:
        candle = by_minute.get(cursor)
        if candle is None:
            break
        bars.append(_bar(candle))
        cursor += MINUTE
    return bars


async def load_series(session: AsyncSession, case: ReplayCase, *, as_of: datetime) -> Series:
    """Load every candle the eight arms of ``case`` can need, once.

    ``as_of`` is a **data cut**, not only a filter on which decisions enter the
    population: nothing after the last minute that had closed by ``as_of``
    reaches the fold, history included. Otherwise a run "as of 17:00" would
    still resolve a 20:00 horizon with candles the cut says it cannot see, and
    "matured at the cut" would mean nothing (Astra, R1 diff review, must-fix 1).
    """
    limit = min(case.horizon_open, last_closed_minute(as_of))
    history = case.entry_bar_open - timedelta(minutes=15 * _CHANNEL_HISTORY_BARS)
    candles = await load_candles(session, market=case.market, start=history, end=limit + MINUTE)
    bars = _prefix(candles, case.entry_bar_open, limit)
    expected = int((limit - case.entry_bar_open).total_seconds() // 60) + 1
    truncated: str | None = None
    if limit < case.horizon_open:
        truncated = "immature"
    if len(bars) < max(expected, 0):
        missing = case.entry_bar_open + MINUTE * len(bars)
        truncated = f"gap:{missing.isoformat()}"
    return Series(candles=tuple(candles), bars=tuple(bars), truncated=truncated)
