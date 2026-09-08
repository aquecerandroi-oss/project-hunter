"""One query per market instead of one per bar — where a replay's speed comes from.

T3.19b, entrega 2. Measured on the local stack before this file existed: a single
replayed bar cost ~763 ms, and ~95 ms of that was re-reading and re-validating
the same 1560 minutes of context that the *previous* bar had already read. Two
consecutive 5m bars share 1555 of their 1560 minutes; reading them again is not
computation, it is repetition.

:class:`WindowCache` reads the whole slice a market needs — the window plus
``context_minutes`` of warm-up in front of it — with one query, and then answers
each bar by slicing what it already holds. The result must be, and is,
**byte-identical** to what :func:`hunter_strategy_worker.repo.load_candles`
would have returned: same ``is_final`` filter, same half-open
``[start, end)`` on ``open_time``, same order, the same objects. Anything else
would make a replay a different experiment from the live lane, and the whole
point of T3.19b is that it is not.

Two refusals, because a cache that guesses is worse than no cache:

- a request that reaches **outside** what was preloaded is delegated to the
  database instead of answered short. That happens for real: the outcome engine
  reads candles past the window's end while resolving a horizon;
- the cache is a snapshot of the series **as of the run's start**. A backfill
  landing mid-run is not seen. That is a property, not a bug — it is what makes
  a sliced run reproducible — and the provenance still records
  ``available_through`` from the rows actually used.
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_strategy_worker.repo import load_candles

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.market import NormalizedCandle
    from hunter_strategy_worker.repo import MarketRow

logger = get_logger(__name__)

__all__ = ["WindowCache", "load_window"]


class WindowCache:
    """The final 1m candles of one market over one slice, held in memory."""

    __slots__ = ("_market_id", "_opens", "_rows", "hits", "misses", "start", "end")

    def __init__(
        self,
        *,
        market_id: object,
        rows: list[NormalizedCandle],
        start: datetime,
        end: datetime,
    ) -> None:
        self._market_id = market_id
        self._rows = rows
        self._opens = [row.open_time for row in rows]
        self.start = ensure_utc(start)
        self.end = ensure_utc(end)
        self.hits = 0
        self.misses = 0

    def covers(self, start: datetime, end: datetime) -> bool:
        return self.start <= ensure_utc(start) and ensure_utc(end) <= self.end

    def slice(self, start: datetime, end: datetime) -> list[NormalizedCandle]:
        """The rows with ``start <= open_time < end`` — ``load_candles``' window."""
        low = bisect_left(self._opens, ensure_utc(start))
        high = bisect_left(self._opens, ensure_utc(end))
        return self._rows[low:high]

    async def __call__(
        self,
        session: AsyncSession,
        *,
        market: MarketRow,
        start: datetime,
        end: datetime,
    ) -> list[NormalizedCandle]:
        """The ``CandleReader`` the replay hands to ``build_market_context``."""
        if market.id != self._market_id or not self.covers(start, end):
            self.misses += 1
            return await load_candles(session, market=market, start=start, end=end)
        self.hits += 1
        return self.slice(start, end)


async def load_window(
    session: AsyncSession,
    *,
    market: MarketRow,
    window_start: datetime,
    window_end: datetime,
    context_minutes: int,
) -> WindowCache:
    """Preload everything the bars of ``[window_start, window_end)`` will ask for.

    The warm-up in front is ``context_minutes`` (1560 in the deployed config):
    the first bar of the window reads that far back, so a cache that started at
    the window would miss on every single bar of it and quietly become a second
    database round trip per bar.
    """
    start = ensure_utc(window_start) - timedelta(minutes=context_minutes)
    end = ensure_utc(window_end)
    rows = await load_candles(session, market=market, start=start, end=end)
    logger.debug(
        "replay_window_cached",
        symbol=market.symbol,
        candles=len(rows),
        start=start.isoformat(),
        end=end.isoformat(),
    )
    return WindowCache(market_id=market.id, rows=rows, start=start, end=end)
