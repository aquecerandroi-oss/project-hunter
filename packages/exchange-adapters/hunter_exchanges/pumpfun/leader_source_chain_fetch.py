"""One ``getTransaction`` per signature for the on-chain leader source (H-037).

* **Shared and cached:** the logs path and the confirmation of a NATS event ask for the same signature;
  concurrent askers share one live task, and only a *successful* read is cached (bounded, oldest out).
  Live tasks are tracked apart from the cache, so a burst of fetches can never evict one that is still
  running, and :meth:`TxFetcher.aclose` cancels every live task.
* **A deadline, not just a ladder:** the retries (a fresh transaction is often not visible for a slot or
  two) stop when :data:`DEADLINE_S` has passed since the first attempt, however slow the node was.
* **A refusal pauses everything:** ``429`` and ``401/403/418`` (including a guarded
  :class:`RpcRefused`) stop the ladder at once, are a ``system_event``, and start a cool-down that is
  re-checked *inside* the concurrency slot, right before the call — a request already queued behind
  another cannot slip through the pause.
"""

from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcRefused
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats

logger = get_logger(__name__)

RETRY_DELAYS_S = (1.0, 5.0)
"""Three attempts in all (0, +1 s, +6 s): the design's "até 3 tentativas em 30 s"."""
DEADLINE_S = 30.0
"""The design's "30 s" for ``not_found``: the cut-off of the whole ladder, RPC time included."""
MAX_INFLIGHT = 8
REFUSAL_COOLDOWN_S = 30.0
CACHE_MAX = 256
_HTTP_STATUS = re.compile(r"HTTP (\d{3})")
_REFUSAL_STATUS = frozenset({401, 403, 418})

__all__ = ["DEADLINE_S", "RETRY_DELAYS_S", "FetchTx", "TxFetcher"]

FetchTx = Callable[[str], Awaitable[dict[str, Any] | None]]
Result = tuple[dict[str, Any] | None, str | None]


class _Paused(Exception):
    """The cool-down began while this call waited for its slot."""


class TxFetcher:
    def __init__(
        self,
        fetch: FetchTx,
        *,
        stats: LeaderSourceStats,
        wall: Callable[[], datetime] = utcnow,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_delays_s: Sequence[float] = RETRY_DELAYS_S,
        deadline_s: float = DEADLINE_S,
        max_inflight: int = MAX_INFLIGHT,
    ) -> None:
        self._fetch, self._stats, self._wall, self._sleep = fetch, stats, wall, sleep
        self._retry, self._deadline_s = tuple(retry_delays_s), deadline_s
        self._sem = asyncio.Semaphore(max_inflight)
        self._live: dict[str, asyncio.Task[Result]] = {}
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cool_until: datetime | None = None
        self._cool_reason = "rate_limited"

    def live(self) -> int:
        return len(self._live)

    async def get(self, signature: str) -> Result:
        cached = self._cache.get(signature)
        if cached is not None:
            return cached, None
        task = self._live.get(signature)
        if task is None:
            task = asyncio.create_task(self._ladder(signature))
            self._live[signature] = task
            task.add_done_callback(lambda t, s=signature: self._done(s, t))
        return await asyncio.shield(task)

    def _done(self, signature: str, task: asyncio.Task[Result]) -> None:
        if self._live.get(signature) is task:
            del self._live[signature]
        if task.cancelled() or task.exception() is not None:
            return
        tx, _ = task.result()
        if tx is not None:  # only a success is remembered: a failure must be asked again
            self._cache[signature] = tx
            while len(self._cache) > CACHE_MAX:
                self._cache.popitem(last=False)

    async def aclose(self) -> None:
        tasks = list(self._live.values())
        for task in tasks:
            task.cancel()
        # gather, not a suppressed await: a cancel aimed at THIS task must not be swallowed
        await asyncio.gather(*tasks, return_exceptions=True)
        self._live.clear()

    # ------------------------------------------------------------------ the ladder
    def _refusal(self, exc: Exception) -> tuple[str, float] | None:
        if isinstance(exc, RpcRefused):
            return exc.reason, 0.0  # the guard already logged and started its own pause
        if isinstance(exc, RateLimited):
            return "rate_limited", max(exc.retry_after_s, 1.0)
        found = _HTTP_STATUS.search(str(exc))
        if found is not None and int(found[1]) in _REFUSAL_STATUS:
            return f"refused_{found[1]}", REFUSAL_COOLDOWN_S
        return None

    def _paused(self) -> bool:
        return self._cool_until is not None and self._wall() < self._cool_until

    async def _ladder(self, signature: str) -> Result:
        start = self._wall()
        cutoff = start + timedelta(seconds=self._deadline_s)
        why = "not_found"
        for delay in (0.0, *self._retry):
            if delay:
                if self._wall() + timedelta(seconds=delay) >= cutoff:
                    break  # the next attempt would start after the deadline
                await self._sleep(delay)
            remaining = (cutoff - self._wall()).total_seconds()
            if remaining <= 0:
                break
            try:
                # the deadline covers the wait for the slot AND the call itself
                tx = await asyncio.wait_for(self._attempt(signature), timeout=remaining)
            except _Paused:
                return None, self._cool_reason
            except TimeoutError:
                why = "unavailable"
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                refused = self._refusal(exc)
                if refused is not None:
                    self._pause(*refused)
                    return None, refused[0]
                self._stats.count("fetch_error")
                logger.warning("leader_chain_fetch_error", error=type(exc).__name__)
                why = "unavailable"
                continue
            if tx is not None:
                return tx, None
            why = "not_found"
        return None, why

    async def _attempt(self, signature: str) -> dict[str, Any] | None:
        async with self._sem:
            if self._paused():  # re-checked in the slot: a queued call cannot slip through
                raise _Paused
            return await self._fetch(signature)

    def _pause(self, reason: str, seconds: float) -> None:
        self._cool_reason = reason
        if seconds > 0:
            self._cool_until = self._wall() + timedelta(seconds=seconds)
            logger.warning(
                "system_event", kind="leader_chain_refused", reason=reason, cool_s=seconds
            )
