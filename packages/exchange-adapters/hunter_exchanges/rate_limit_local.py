"""The uncoordinated, in-memory token buckets — used only when a limiter was
built with **no Redis client at all**.

That is the one-process case: a ``BinanceRestClient()`` constructed without
coordination (unit tests, a script), where "one process" and "one IP budget"
are the same thing. It is deliberately *not* what happens when a configured
Redis stops answering — that path suspends admissions instead
(``rate_limit_suspension.py``), because several shards each spending a full
local budget is exactly how a shared IP quota gets exceeded.

Same refill algorithm as ``ACQUIRE_SCRIPT``/``RECORD_USED_WEIGHT_SCRIPT`` in
``rate_limit_lua.py``, in Python: refill by elapsed time (capped at capacity),
consume only when the whole weight fits, and let the exchange's own
``X-MBX-USED-WEIGHT-1M`` take budget away but never give it back.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

__all__ = ["LocalBuckets"]


class _LocalBucket:
    """Pure in-memory refill state for one bucket."""

    __slots__ = ("tokens", "ts")

    def __init__(self, capacity: float, now: float) -> None:
        self.tokens = capacity
        self.ts = now


class LocalBuckets:
    """One in-memory bucket per name, guarded by a single lock.

    The lock is what keeps ten concurrent ``consume`` calls from each thinking
    they got the last token.
    """

    def __init__(
        self,
        *,
        capacity: float,
        refill_per_s: float,
        refill_period_s: float,
        clock: Callable[[], float],
    ) -> None:
        self._capacity = capacity
        self._refill_per_s = refill_per_s
        self._refill_period_s = refill_period_s
        self._clock = clock
        self._buckets: dict[str, _LocalBucket] = {}
        self._lock = asyncio.Lock()
        # Guards against an older/overlapping response's used-weight
        # resurrecting tokens a newer response already correctly spent (Astra
        # review, T1.2 resume): (used_weight, clock() when it was applied). A
        # lower value is only accepted once a full window has passed — the
        # exchange's own counter resets every window, so "lower" only means
        # "stale" *within* the same window. The Redis path decides the same
        # thing inside the Lua, where it is atomic across processes.
        self._last_used_weight: dict[str, tuple[int, float]] = {}

    def tokens(self, bucket: str) -> float | None:
        """Remaining tokens of ``bucket``, or ``None`` if it was never used.

        Read-only introspection: ``tests/unit/test_rest_client.py`` asserts on
        which bucket a REST call actually charged.
        """
        state = self._buckets.get(bucket)
        return None if state is None else state.tokens

    async def consume(self, bucket: str, weight: int) -> float:
        """Seconds to wait for ``weight``; ``0`` means it was consumed."""
        async with self._lock:
            now = self._clock()
            state = self._buckets.get(bucket)
            if state is None:
                state = _LocalBucket(self._capacity, now)
                self._buckets[bucket] = state
            elapsed = max(0.0, now - state.ts)
            state.tokens = min(self._capacity, state.tokens + elapsed * self._refill_per_s)
            state.ts = now
            if state.tokens < weight:
                return (weight - state.tokens) / self._refill_per_s
            state.tokens -= weight
            return 0.0

    async def record_used_weight(self, bucket: str, used_weight: int) -> None:
        """Reconcile ``bucket`` against the exchange's own accounting.

        ``min(tokens after refill, capacity - used_weight)``, never
        ``capacity - used_weight`` outright: a header that arrives while other
        requests are still in flight must not resurrect budget those requests
        already reserved (F3).
        """
        async with self._lock:
            now = self._clock()
            last = self._last_used_weight.get(bucket)
            if last is not None:
                last_weight, last_at = last
                if used_weight < last_weight and now - last_at < self._refill_period_s:
                    return
            self._last_used_weight[bucket] = (used_weight, now)
            state = self._buckets.get(bucket)
            if state is None:
                tokens_after_refill = self._capacity
            else:
                elapsed = max(0.0, now - state.ts)
                tokens_after_refill = min(
                    self._capacity, state.tokens + elapsed * self._refill_per_s
                )
            proposed = max(0.0, self._capacity - used_weight)
            self._buckets[bucket] = _LocalBucket(min(tokens_after_refill, proposed), now)
