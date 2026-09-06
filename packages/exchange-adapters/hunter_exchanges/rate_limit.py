"""Token bucket rate limiting for exchange REST calls (docs/EXCHANGE_INTEGRATION.md §5).

One bucket per ``(exchange, bucket_name)`` — e.g. Binance's ``request_weight``,
refilled continuously to its official cap (2400/min for USDS-M Futures).
State lives in Redis at ``rl:{exchange}:{bucket}`` (``hunter_core.redis.keys.rate_limit``)
so every process sharing one IP shares one budget; a limiter built with no
Redis client at all (unit tests, a one-process client) keeps the same
semantics in memory.

**A configured Redis going away is a different thing entirely** and is never
answered with a local budget (T2.9, M2 acceptance): admissions are *suspended*
until coordination comes back — see ``rate_limit_suspension.py`` for why an
in-memory fallback risks an irreversible Binance IP ban.

The Lua these run is in ``rate_limit_lua.py`` and the IP-wide backoff gate in
``rate_limit_gate.py`` (T2.9: ``blocked_until`` and the used-weight staleness
guard are coordinated across processes, not kept per process).

``acquire(bucket, weight)`` waits out short shortfalls and raises
:class:`~hunter_exchanges.base.RateLimited` when the wait would exceed
``max_wait_s`` — callers decide from there (log and skip, backoff, etc.), it
never loops forever. :meth:`TokenBucketRateLimiter.record_used_weight`
reconciles the bucket against Binance's own accounting
(``X-MBX-USED-WEIGHT-1M`` response header) so local drift — a retry, another
process on the same IP — never lets the limiter believe it has more budget
than the exchange does.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from hunter_core.logging import get_logger
from hunter_core.redis import keys
from hunter_exchanges.base import RateLimited
from hunter_exchanges.rate_limit_gate import IpRateGate
from hunter_exchanges.rate_limit_local import LocalBuckets
from hunter_exchanges.rate_limit_lua import ACQUIRE_SCRIPT, RECORD_USED_WEIGHT_SCRIPT
from hunter_exchanges.rate_limit_suspension import (
    REDIS_UNAVAILABLE,
    REST_GATE_OK,
    REST_GATE_SUSPENDED,
    Suspension,
)

__all__ = ["REST_GATE_OK", "REST_GATE_SUSPENDED", "IpRateGate", "TokenBucketRateLimiter"]

logger = get_logger(__name__)

#: Floor for the derived TTL (F2) — short enough that an abandoned bucket's
#: Redis key still expires in a reasonable time, long enough that even the
#: shortest real bucket (request_weight, 60s window) survives comfortably.
_TTL_FLOOR_S = 120  # int: Redis EXPIRE rejects a float-serialized argument

# Re-exported: ``tests/unit/test_rate_limit.py`` and any operator reading the
# protocol reach the scripts through this module's name.
_ACQUIRE_SCRIPT = ACQUIRE_SCRIPT
_RECORD_USED_WEIGHT_SCRIPT = RECORD_USED_WEIGHT_SCRIPT


class _RedisEvalClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...
    async def hset(self, name: str, mapping: dict[str, object]) -> object: ...


class TokenBucketRateLimiter:
    """Token bucket keyed by ``rl:{exchange}:{bucket}``.

    ``clock`` and ``sleep`` are injectable so tests can run a limiter that
    would otherwise wait real seconds instantly and deterministically.
    """

    def __init__(
        self,
        exchange: str,
        *,
        redis: _RedisEvalClient | None = None,
        capacity: float = 2400,
        refill_period_s: float = 60.0,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        ip_gate: IpRateGate | None = None,
    ) -> None:
        if capacity <= 0 or refill_period_s <= 0:
            raise ValueError("capacity and refill_period_s must be positive")
        self._exchange = exchange
        self._redis = redis
        self._capacity = float(capacity)
        self._refill_period_s = float(refill_period_s)
        self._refill_per_s = float(capacity) / refill_period_s
        self._clock = clock
        self._sleep = sleep
        # F2: derived from this bucket's own window so its Redis key can
        # never expire mid-window (a 300s funding-history window with the
        # old fixed 120s TTL let the bucket reset to full capacity at 121s,
        # inside the same exchange window).
        self._bucket_state_ttl_s = math.ceil(max(2.0 * self._refill_period_s, _TTL_FLOOR_S))
        self._ip_gate: IpRateGate | None = None
        if ip_gate is not None:
            self.ip_gate = ip_gate
        # Only ever used when no Redis was given at all (one process, one
        # budget). A configured Redis going down suspends instead.
        self._local = (
            None
            if redis is not None
            else LocalBuckets(
                capacity=self._capacity,
                refill_per_s=self._refill_per_s,
                refill_period_s=self._refill_period_s,
                clock=clock,
            )
        )
        # Only meaningful when a Redis client *was* given: "the coordination
        # this limiter depends on is unreachable, so nothing is admitted".
        self._suspension = Suspension(exchange)

    @property
    def suspended(self) -> bool:
        """True while this limiter admits nothing because coordination is down."""
        return self._suspension.active

    @property
    def suspension_reason(self) -> str | None:
        """Why admissions are suspended (``"redis_unavailable"``), or ``None``."""
        return self._suspension.reason

    async def acquire(self, bucket: str, weight: int, *, max_wait_s: float = 30.0) -> None:
        """Block until ``weight`` tokens of ``bucket`` are available.

        Raises :class:`RateLimited` (never waits) once the required wait
        would exceed ``max_wait_s`` — a caller-visible signal instead of a
        request silently stalling.

        While the shared coordination is unreachable **nothing is admitted**
        (T2.9): the call re-probes Redis on a short jittered backoff and, once
        ``max_wait_s`` of that waiting is spent, raises ``RateLimited`` with
        ``reason="redis_unavailable"``. Never a raw Redis exception — that
        would take the caller's loop (and the worker) down instead of
        degrading REST while the WebSocket keeps ingesting.
        """
        if weight <= 0:
            raise ValueError("weight must be positive")
        suspended_for_s = 0.0
        attempt = 0
        while True:
            # F4: a 429/418 on *any* bucket sharing this IP gates every
            # bucket, not just the one that got the response — checked
            # first, every loop iteration, so a gate that outlives one
            # sleep still blocks the retry.
            gate_wait = await self._gate_wait_s(bucket)
            if gate_wait is not None and gate_wait > 0:
                if gate_wait > max_wait_s:
                    raise RateLimited(
                        f"binance IP is rate-limited for {gate_wait:.2f}s "
                        f"(Retry-After from another bucket), exceeding max_wait_s={max_wait_s}",
                        exchange=self._exchange,
                        retry_after_s=gate_wait,
                    )
                await self._sleep(gate_wait)
                continue
            wait = None if gate_wait is None else await self._try_consume(bucket, weight)
            if wait is None:
                delay = self._suspension.next_delay(bucket, attempt, suspended_for_s, max_wait_s)
                attempt += 1
                suspended_for_s += delay
                await self._sleep(delay)
                continue
            attempt = 0
            if wait <= 0:
                return
            if wait > max_wait_s:
                raise RateLimited(
                    f"binance rate limit bucket {bucket!r} would need to wait {wait:.2f}s "
                    f"for weight {weight}, exceeding max_wait_s={max_wait_s}",
                    exchange=self._exchange,
                    retry_after_s=wait,
                )
            await self._sleep(wait)

    async def _gate_wait_s(self, bucket: str) -> float | None:
        """Seconds the IP-wide block still has to run, or ``None`` when the
        shared deadline could not be read.

        An unreadable gate is coordination being down, and coordination being
        down admits nothing (Astra, T2.9 round 3). :meth:`IpRateGate.wait_s`
        falls back to this process's local mirror when the shared read fails,
        and that mirror is ``0`` whenever the 429 landed on a *peer* shard —
        admitting on it is precisely the walk into the ban the gate prevents.
        """
        gate = self._ip_gate
        if gate is None:
            return 0.0
        wait = await gate.wait_s()
        if gate.degraded:
            self._suspension.suspend(bucket, REDIS_UNAVAILABLE, "ip gate unreadable")
            return None
        return wait

    async def _try_consume(self, bucket: str, weight: int) -> float | None:
        """Seconds to wait for ``weight``, or ``None`` when coordination is down.

        ``None`` is never "assume there is budget": the caller suspends. A
        Redis failure is not propagated because the caller is
        ``BinanceRestClient._get``, which reconciles the used-weight header
        **before** it looks at the status code — an exception escaping here
        skipped the ``429``/``418`` branch entirely, so a rate-limited response
        left no cooldown at all and the next request walked into an IP ban
        (Astra, T2.9 round 2).
        """
        if self._local is not None:
            return await self._local.consume(bucket, weight)
        try:
            wait = await self._consume_redis(bucket, weight)
        except Exception as exc:
            self._suspension.suspend(bucket, REDIS_UNAVAILABLE, exc)
            return None
        self._suspension.resume()
        return wait

    async def _consume_redis(self, bucket: str, weight: int) -> float:
        key = keys.rate_limit(self._exchange, bucket)
        now = self._clock()
        result = await self._redis.eval(  # type: ignore[union-attr]
            ACQUIRE_SCRIPT,
            1,
            key,
            self._capacity,
            self._refill_per_s,
            weight,
            now,
            self._bucket_state_ttl_s,
        )
        return float(result)  # type: ignore[arg-type]

    async def record_used_weight(self, bucket: str, used_weight: int) -> None:
        """Reconcile the bucket to the exchange's own ``X-MBX-USED-WEIGHT-1M``.

        The header may only ever **take budget away**, never give it back
        (F3): the new token count is ``min(tokens after refill, capacity -
        used_weight)``, never just ``capacity - used_weight`` outright. A
        header that arrives while other requests from this process are
        still in flight (already reserved, i.e. already reflected in
        "tokens after refill") must not resurrect that reserved budget —
        otherwise a cold start of many concurrent requests followed by one
        response with a small ``used_weight`` would re-open budget that is
        already committed, and the remaining requests flood out past the
        exchange's real limit.

        Also ignored if ``used_weight`` is lower than the highest one
        already applied for this bucket *within the current window*: an
        older response's number arriving after a newer one must never
        resurrect tokens the newer one already spent. A lower value is
        trusted again once a full ``refill_period_s`` has elapsed (a new
        window legitimately starts lower).

        T2.9: that staleness decision is made **inside the Lua** when there is
        a Redis (``uw``/``uw_at`` next to the tokens they produced), so two
        processes racing on one key cannot reorder — the local dict below only
        governs the memory-only path. The old code returned early on the local
        guard and never reached Redis, which meant one process could refuse a
        reading its peers had every reason to apply.
        """
        if self._redis is not None:
            try:
                await self._redis.eval(
                    RECORD_USED_WEIGHT_SCRIPT,
                    1,
                    keys.rate_limit(self._exchange, bucket),
                    self._capacity,
                    self._refill_per_s,
                    used_weight,
                    self._clock(),
                    self._refill_period_s,
                    self._bucket_state_ttl_s,
                )
            except Exception as exc:
                # Suspending here (instead of reconciling a local bucket that
                # nothing else reads) is what makes the *next* ``acquire`` stop
                # admitting: the outage is detected on whichever call hits it
                # first, and this one is usually first.
                self._suspension.suspend(bucket, REDIS_UNAVAILABLE, exc)
            else:
                self._suspension.resume()
            return
        if self._local is not None:
            await self._local.record_used_weight(bucket, used_weight)

    @property
    def ip_gate(self) -> IpRateGate | None:
        """The IP-wide backoff gate shared by every bucket on this IP."""
        return self._ip_gate

    @ip_gate.setter
    def ip_gate(self, gate: IpRateGate) -> None:
        """Attach ``gate`` and hand it this limiter's Redis client (T2.9).

        ``BinanceRestClient`` constructs a bare ``IpRateGate()`` and assigns it
        to both of its limiters; the assignment is the only place that knows
        both the gate and the (optional) shared client, so it is where the
        binding happens. No IO, idempotent, and a mismatched exchange raises
        rather than silently moving the gate's key.
        """
        if self._redis is not None:
            gate.bind(self._redis, self._exchange)
        self._ip_gate = gate

    @property
    def redis(self) -> _RedisEvalClient | None:
        """The underlying client, so a companion limiter for a *different*
        endpoint-specific budget (e.g. Binance funding history's 500/5min)
        can share the same Redis connection without this class growing a
        multi-bucket capacity table."""
        return self._redis

    async def cooldown(self, bucket: str, *, retry_after_s: float | None = None) -> None:
        """Zero out ``bucket``'s remaining tokens and, if ``retry_after_s``
        is given, block every bucket sharing this limiter's ``ip_gate``.

        Call this right after a ``429``/``418`` so *this process's* own next
        :meth:`acquire` waits out a real refill instead of a token bucket
        that still believes it has budget the exchange just said it does
        not. ``retry_after_s`` (F4) additionally opens the shared
        :class:`IpRateGate`, if one was injected, for the full duration
        Binance asked for — a 429 on one bucket must stop *every* bucket on
        the same IP, not just the one that got the response. Does not by
        itself coordinate a cooldown across processes sharing the same
        IP: since T2.9 the deadline is shared through Redis, so the *other*
        processes on this IP back off from this 429 too, instead of learning
        about it only from their own next 429.

        The gate is opened **before** the bucket reconciliation, which is the
        fallible part (Astra, T2.9 round 1): reconciling first meant an
        exception there left the IP unblocked immediately after a 429.
        """
        if retry_after_s is not None and self._ip_gate is not None:
            await self._ip_gate.block_for(retry_after_s)
        await self.record_used_weight(bucket, used_weight=int(self._capacity))
