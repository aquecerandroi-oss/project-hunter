"""A finite stream queue whose overflow is a named gap (H-037, security review R1 LOW-1).

The leader streams hand items to a consumer through a queue. Unbounded, a stalled consumer plus a burst
of leader activity is an out-of-memory; bounded and silent, it is lost trades. :class:`OverflowQueue` is
the third way, with an **episode** protocol the lane already understands (open gap, then closed gap):

* past ``cap`` an event or confirmation is **dropped and counted**, and *at that moment* an open
  ``<name>_overflow`` :class:`LeaderGap` (``wallet=None``: we cannot say whose item it was, so every
  wallet is censored) is queued — it does not wait for the consumer to catch up;
* gaps are small and rare, so they get headroom up to ``2 * cap`` items in the queue. Past it they are
  **absorbed into a bounded ledger** instead of queued: the earliest start of everything absorbed, the
  one coalesced closed interval per ``(wallet, reason)`` and the still-open gaps with their original
  start. Nothing is lost, only coalesced (a closing gap is never swallowed: a gap that was queued open
  must reach the consumer closed);
* once the consumer has drained the queue to half its cap the episode ends: ONE closing
  ``<name>_overflow`` gap over ``[earliest start, now)`` is queued, then the coalesced closed gaps, then
  every absorbed gap that is still open, re-issued with its original start (emptying the queue does not
  recover a source).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import LeaderGap, LeaderItem

logger = get_logger(__name__)

QUEUE_MAX = 20_000

__all__ = ["QUEUE_MAX", "OverflowQueue"]


class OverflowQueue(asyncio.Queue[LeaderItem]):
    def __init__(
        self, name: str, *, cap: int = QUEUE_MAX, wall: Callable[[], datetime] = utcnow
    ) -> None:
        super().__init__()  # unbounded at the base: the caps are applied here
        self.name, self.cap, self._wall = name, cap, wall
        self.dropped = 0
        self.gaps_absorbed = 0
        self._since: datetime | None = None  # earliest start of the episode, absorbed gaps included
        self._absorbed_open: dict[tuple[str | None, str], datetime] = {}
        self._absorbed_closed: dict[tuple[str | None, str], LeaderGap] = {}

    def _begin_episode(self) -> None:
        self._since = self._wall()
        logger.error("leader_queue_overflow", queue=self.name, cap=self.cap)
        super().put_nowait(LeaderGap(None, self._since, None, f"{self.name}_overflow"))

    def _absorb(self, gap: LeaderGap) -> None:
        if self._since is None:
            self._begin_episode()
        self.gaps_absorbed += 1
        assert self._since is not None
        self._since = min(self._since, gap.start)
        key = (gap.wallet, gap.reason)
        if gap.end is None:
            self._absorbed_open[key] = min(gap.start, self._absorbed_open.get(key, gap.start))
            return
        start = min(gap.start, self._absorbed_open.pop(key, gap.start))
        known = self._absorbed_closed.get(key)
        if known is not None and known.end is not None:
            start, end = min(start, known.start), max(gap.end, known.end)
        else:
            end = gap.end
        self._absorbed_closed[key] = LeaderGap(gap.wallet, start, end, gap.reason)

    def put_nowait(self, item: LeaderItem) -> None:
        if isinstance(item, LeaderGap):
            if self.qsize() >= 2 * self.cap:
                self._absorb(item)
                return
            super().put_nowait(item)
            return
        if self.qsize() >= self.cap:
            self.dropped += 1
            if self._since is None:
                self._begin_episode()
            return
        super().put_nowait(item)

    async def get(self) -> LeaderItem:
        item = await super().get()
        if self._since is not None and self.qsize() <= self.cap // 2:
            since, self._since = self._since, None
            end = max(self._wall(), since)
            super().put_nowait(LeaderGap(None, since, end, f"{self.name}_overflow"))
            closed, self._absorbed_closed = self._absorbed_closed, {}
            for gap in closed.values():
                super().put_nowait(gap)
            reopened, self._absorbed_open = self._absorbed_open, {}
            for (wallet, reason), start in reopened.items():
                super().put_nowait(LeaderGap(wallet, start, None, reason))
        return item
