"""Token bucket rate limiting for exchange REST calls (docs/EXCHANGE_INTEGRATION.md §5).

One bucket per ``(exchange, bucket_name)`` — e.g. Binance's ``request_weight``,
refilled continuously to its official cap (2400/min for USDS-M Futures).
State lives in Redis at ``rl:{exchange}:{bucket}`` (``hunter_core.redis.keys.rate_limit``)
so every process sharing one IP shares one budget; when no Redis client is
given, an in-memory fallback keeps the same semantics for unit tests.

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
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

from hunter_core.redis import keys
from hunter_exchanges.base import RateLimited

if TYPE_CHECKING:
    pass

#: Floor for the derived TTL (F2) — short enough that an abandoned bucket's
#: Redis key still expires in a reasonable time, long enough that even the
#: shortest real bucket (request_weight, 60s window) survives comfortably.
_BUCKET_STATE_TTL_FLOOR_S = 120.0

# Lua script: refill-then-consume, atomically. Returns the wait time (seconds,
# as a string — Redis Lua has no float return type) needed before ``weight``
# tokens would be available; "0" means the weight was consumed immediately.
# Tokens are only deducted when the wait is zero, so a caller that ends up
# waiting (or raising) never loses budget it did not actually spend.
_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_s = tonumber(ARGV[2])
local weight = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local tokens = tonumber(redis.call('HGET', key, 'tokens'))
local ts = tonumber(redis.call('HGET', key, 'ts'))
if tokens == nil or ts == nil then
    tokens = capacity
    ts = now
end
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_per_s)

local wait = 0
if tokens < weight then
    wait = (weight - tokens) / refill_per_s
    redis.call('HSET', key, 'tokens', tokens, 'ts', now)
else
    tokens = tokens - weight
    redis.call('HSET', key, 'tokens', tokens, 'ts', now)
end
redis.call('EXPIRE', key, ARGV[5])
return tostring(wait)
"""

# Lua script for record_used_weight (F3): the exchange's own accounting may
# only ever *take budget away*, never give it back. Refills first (so a
# header that arrives after a long idle gap doesn't look artificially low),
# then takes the minimum of "tokens after refill" (which already reflects
# every reservation this or another process made) and "capacity -
# used_weight" — a lower header can shrink the bucket, but can never raise
# it back above what is already reserved in flight.
_RECORD_USED_WEIGHT_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_s = tonumber(ARGV[2])
local used_weight = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local tokens = tonumber(redis.call('HGET', key, 'tokens'))
local ts = tonumber(redis.call('HGET', key, 'ts'))
if tokens == nil or ts == nil then
    tokens = capacity
    ts = now
end
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_per_s)

local proposed = capacity - used_weight
if proposed < 0 then proposed = 0 end
local new_tokens = tokens
if proposed < tokens then new_tokens = proposed end

redis.call('HSET', key, 'tokens', new_tokens, 'ts', now)
redis.call('EXPIRE', key, ttl)
return tostring(new_tokens)
"""


class _RedisEvalClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...
    async def hset(self, name: str, mapping: dict[str, object]) -> object: ...


class IpRateGate:
    """Process-local, monotonic "this IP is blocked until" deadline (F4).

    Binance's ``429``/``418`` responses are per-IP, not per-bucket: a
    ``Retry-After`` on one bucket (e.g. ``funding_history``) means every
    other bucket sharing that IP (``request_weight``) must back off too, or
    the next request escalates a ``429`` into an ``418`` ban. Sharing one
    instance across a process's limiters is the whole fix; cross-process
    coordination is out of scope for M1 (one process per IP) — see the fix
    brief's "known limitations".
    """

    __slots__ = ("_clock", "_blocked_until")

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._blocked_until = 0.0

    def block_for(self, seconds: float) -> None:
        """Extend the block by ``seconds`` from now (never shortens it)."""
        if seconds <= 0:
            return
        self._blocked_until = max(self._blocked_until, self._clock() + seconds)

    def wait_s(self) -> float:
        """Seconds remaining until the IP-wide block lifts (0 if not blocked)."""
        return max(0.0, self._blocked_until - self._clock())


class _LocalBucket:
    """Pure in-memory refill state for one ``(exchange, bucket)`` pair."""

    __slots__ = ("tokens", "ts")

    def __init__(self, capacity: float, now: float) -> None:
        self.tokens = capacity
        self.ts = now


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
        self._bucket_state_ttl_s = max(2.0 * self._refill_period_s, _BUCKET_STATE_TTL_FLOOR_S)
        self.ip_gate = ip_gate
        self._local_buckets: dict[str, _LocalBucket] = {}
        self._local_lock = asyncio.Lock()
        # Guards against an older/overlapping response's used-weight
        # resurrecting tokens a newer response already correctly spent
        # (Astra review, T1.2 resume): (used_weight, clock() at the time it
        # was applied). A lower value is only accepted once a full window
        # has passed since the last one — Binance's own counter resets every
        # window, so "lower" only means "stale" *within* the same window.
        # Only covers this one process; two processes racing on the same
        # Redis key can still reorder — a documented, self-correcting (next
        # response reconciles again) limitation.
        self._last_used_weight: dict[str, tuple[int, float]] = {}

    async def acquire(self, bucket: str, weight: int, *, max_wait_s: float = 30.0) -> None:
        """Block until ``weight`` tokens of ``bucket`` are available.

        Raises :class:`RateLimited` (never waits) once the required wait
        would exceed ``max_wait_s`` — a caller-visible signal instead of a
        request silently stalling.
        """
        if weight <= 0:
            raise ValueError("weight must be positive")
        while True:
            # F4: a 429/418 on *any* bucket sharing this IP gates every
            # bucket, not just the one that got the response — checked
            # first, every loop iteration, so a gate that outlives one
            # sleep still blocks the retry.
            gate_wait = self.ip_gate.wait_s() if self.ip_gate is not None else 0.0
            if gate_wait > 0:
                if gate_wait > max_wait_s:
                    raise RateLimited(
                        f"binance IP is rate-limited for {gate_wait:.2f}s "
                        f"(Retry-After from another bucket), exceeding max_wait_s={max_wait_s}",
                        exchange=self._exchange,
                        retry_after_s=gate_wait,
                    )
                await self._sleep(gate_wait)
                continue
            wait = await self._try_consume(bucket, weight)
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

    async def _try_consume(self, bucket: str, weight: int) -> float:
        if self._redis is not None:
            return await self._consume_redis(bucket, weight)
        return await self._consume_local(bucket, weight)

    async def _consume_redis(self, bucket: str, weight: int) -> float:
        key = keys.rate_limit(self._exchange, bucket)
        now = self._clock()
        result = await self._redis.eval(  # type: ignore[union-attr]
            _ACQUIRE_SCRIPT,
            1,
            key,
            self._capacity,
            self._refill_per_s,
            weight,
            now,
            self._bucket_state_ttl_s,
        )
        return float(result)  # type: ignore[arg-type]

    async def _consume_local(self, bucket: str, weight: int) -> float:
        async with self._local_lock:
            now = self._clock()
            state = self._local_buckets.get(bucket)
            if state is None:
                state = _LocalBucket(self._capacity, now)
                self._local_buckets[bucket] = state
            elapsed = max(0.0, now - state.ts)
            state.tokens = min(self._capacity, state.tokens + elapsed * self._refill_per_s)
            state.ts = now
            if state.tokens < weight:
                return (weight - state.tokens) / self._refill_per_s
            state.tokens -= weight
            return 0.0

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
        """
        async with self._local_lock:
            now = self._clock()
            last = self._last_used_weight.get(bucket)
            if last is not None:
                last_weight, last_at = last
                if used_weight < last_weight and now - last_at < self._refill_period_s:
                    return
            self._last_used_weight[bucket] = (used_weight, now)
            if self._redis is not None:
                key = keys.rate_limit(self._exchange, bucket)
                await self._redis.eval(  # type: ignore[union-attr]
                    _RECORD_USED_WEIGHT_SCRIPT,
                    1,
                    key,
                    self._capacity,
                    self._refill_per_s,
                    used_weight,
                    now,
                    self._bucket_state_ttl_s,
                )
                return
            state = self._local_buckets.get(bucket)
            if state is None:
                tokens_after_refill = self._capacity
            else:
                elapsed = max(0.0, now - state.ts)
                tokens_after_refill = min(
                    self._capacity, state.tokens + elapsed * self._refill_per_s
                )
            proposed = max(0.0, self._capacity - used_weight)
            new_tokens = min(tokens_after_refill, proposed)
            self._local_buckets[bucket] = _LocalBucket(new_tokens, now)

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
        IP/Redis key — the exchange's own ``429``/``418`` on each process's
        next attempt remains the hard backstop for that.
        """
        await self.record_used_weight(bucket, used_weight=int(self._capacity))
        if retry_after_s is not None and self.ip_gate is not None:
            self.ip_gate.block_for(retry_after_s)
