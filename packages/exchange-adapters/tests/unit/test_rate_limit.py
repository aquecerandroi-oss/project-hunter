"""TokenBucketRateLimiter: local in-memory fallback and Redis-backed path.

Both paths share one Lua-equivalent refill algorithm; the local-vs-redis
split is exercised separately so a bug in either backend shows up here
instead of only in an integration test.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from hunter_exchanges.base import RateLimited
from hunter_exchanges.rate_limit import (
    _RECORD_USED_WEIGHT_SCRIPT,  # pyright: ignore[reportPrivateUsage]
    IpRateGate,
    TokenBucketRateLimiter,
)

pytestmark = pytest.mark.unit


class _FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _NoopSleepRecorder:
    """Records requested sleep durations and advances a fake clock instead of waiting."""

    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


class _FakeRedisEval:
    """A minimal in-memory stand-in for the one Lua script the limiter runs."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, float]] = {}
        self.last_ttl: float | None = None

    async def eval(self, script: str, numkeys: int, *args: Any) -> str:
        key, capacity, refill_per_s, arg3, now, ttl = args
        capacity = float(capacity)
        refill_per_s = float(refill_per_s)
        now = float(now)
        self.last_ttl = float(ttl)
        state = self._hashes.get(key)
        if state is None:
            tokens, ts = capacity, now
        else:
            tokens, ts = state["tokens"], state["ts"]
        elapsed = max(0.0, now - ts)
        tokens = min(capacity, tokens + elapsed * refill_per_s)
        if script is _RECORD_USED_WEIGHT_SCRIPT:
            # F3 emulation: min(tokens after refill, capacity - used_weight)
            # — mirrors _RECORD_USED_WEIGHT_SCRIPT exactly, since this fake
            # stands in for a real Lua interpreter that would run the actual
            # script text.
            used_weight = float(arg3)
            proposed = max(0.0, capacity - used_weight)
            new_tokens = min(tokens, proposed)
            self._hashes[key] = {"tokens": new_tokens, "ts": now}
            return str(new_tokens)
        weight = float(arg3)
        if tokens < weight:
            self._hashes[key] = {"tokens": tokens, "ts": now}
            return str((weight - tokens) / refill_per_s)
        tokens -= weight
        self._hashes[key] = {"tokens": tokens, "ts": now}
        return "0"

    async def hset(self, name: str, mapping: dict[str, object]) -> None:
        self._hashes[name] = {
            "tokens": float(mapping["tokens"]),  # type: ignore[arg-type]
            "ts": float(mapping["ts"]),  # type: ignore[arg-type]
        }


async def test_local_acquire_consumes_tokens_immediately_when_budget_available() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=10, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter.acquire("request_weight", 5)

    assert sleeper.calls == []


async def test_local_acquire_waits_for_refill_then_succeeds() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=10, refill_period_s=10, clock=clock, sleep=sleeper
    )
    await limiter.acquire("request_weight", 10)  # drain the bucket

    await limiter.acquire("request_weight", 5, max_wait_s=30)

    assert sleeper.calls  # it had to wait out a refill
    assert sleeper.calls[0] == pytest.approx(5.0, rel=0.05)  # 5 tokens at 1/s refill


async def test_local_acquire_raises_rate_limited_when_wait_exceeds_max_wait_s() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=10, refill_period_s=100, clock=clock, sleep=sleeper
    )
    await limiter.acquire("request_weight", 10)

    with pytest.raises(RateLimited) as exc_info:
        await limiter.acquire("request_weight", 10, max_wait_s=1.0)

    assert exc_info.value.exchange == "binance"
    assert exc_info.value.retry_after_s > 1.0
    assert sleeper.calls == []  # never actually waited; raised instead


async def test_record_used_weight_reconciles_local_bucket() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=100, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter.record_used_weight("request_weight", used_weight=95)
    # Only 5 tokens should remain; requesting 6 must wait, not succeed immediately.
    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 6, max_wait_s=0.0)


async def test_record_used_weight_ignores_a_stale_lower_reading_in_the_same_window() -> None:
    """An older response (used_weight=90) processed after a newer one
    (used_weight=95) must not resurrect the 5 tokens the newer one spent."""
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=100, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter.record_used_weight("request_weight", used_weight=95)
    await limiter.record_used_weight("request_weight", used_weight=90)  # stale, same window

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 6, max_wait_s=0.0)  # still only 5 left, not 10


async def test_record_used_weight_accepts_a_lower_reading_after_a_new_window() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=100, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter.record_used_weight("request_weight", used_weight=95)
    clock.advance(61)  # a full window has passed: Binance's own counter reset
    await limiter.record_used_weight("request_weight", used_weight=10)

    await limiter.acquire("request_weight", 6, max_wait_s=0.0)  # 90 left: succeeds immediately
    assert sleeper.calls == []


async def test_cooldown_zeroes_the_bucket_after_a_429() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=100, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter.cooldown("request_weight")

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 1, max_wait_s=0.0)


async def test_two_buckets_are_independent() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=10, refill_period_s=60, clock=clock, sleep=sleeper
    )
    await limiter.acquire("request_weight", 10)

    await limiter.acquire("orders", 10)  # a different bucket must have its own full budget

    assert sleeper.calls == []


async def test_redis_backed_acquire_uses_the_shared_script() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _FakeRedisEval()
    limiter = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=10, refill_period_s=10, clock=clock, sleep=sleeper
    )

    await limiter.acquire("request_weight", 10)
    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 1, max_wait_s=0.0)


async def test_redis_backed_state_is_shared_across_limiter_instances() -> None:
    """Two processes sharing one Redis key share one budget."""
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _FakeRedisEval()
    limiter_a = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=10, refill_period_s=60, clock=clock, sleep=sleeper
    )
    limiter_b = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=10, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter_a.acquire("request_weight", 6)

    with pytest.raises(RateLimited):
        await limiter_b.acquire("request_weight", 5, max_wait_s=0.0)


async def test_concurrent_local_acquires_never_oversubscribe_the_bucket() -> None:
    """Ten concurrent weight-1 acquires against a capacity-1 bucket: only one
    proceeds immediately, and no interleaving lets two callers both think
    they got the last token (the lock in _consume_local must be exclusive).
    """
    clock = _FakeClock()

    async def instant_sleep(seconds: float) -> None:
        clock.advance(seconds)

    limiter = TokenBucketRateLimiter(
        "binance", capacity=1, refill_period_s=1_000_000, clock=clock, sleep=instant_sleep
    )

    async def try_once() -> bool:
        try:
            await limiter.acquire("request_weight", 1, max_wait_s=0.0)
            return True
        except RateLimited:
            return False

    results = await asyncio.gather(*[try_once() for _ in range(10)])

    assert sum(results) == 1


def test_redis_property_exposes_the_underlying_client_for_a_companion_limiter() -> None:
    class _FakeRedis:
        async def eval(self, script: str, numkeys: int, *args: object) -> object:
            return "0"

        async def hset(self, name: str, mapping: dict[str, object]) -> object:
            return None

    redis = _FakeRedis()
    limiter = TokenBucketRateLimiter("binance", redis=redis)

    assert limiter.redis is redis


def test_redis_property_is_none_for_the_local_fallback() -> None:
    limiter = TokenBucketRateLimiter("binance")

    assert limiter.redis is None


# --- F2: bucket state TTL must outlive the limiter's own refill window ---


async def test_bucket_state_ttl_never_expires_inside_the_limiters_own_window() -> None:
    """A 300s-period bucket (Binance funding history: 500/5min) must write a
    Redis key with a TTL of at least two full windows — never the old fixed
    120s, which expires *inside* a single 300s window and lets the bucket
    reset to full capacity mid-window (F2)."""
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _FakeRedisEval()
    limiter = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=500, refill_period_s=300.0, clock=clock, sleep=sleeper
    )

    await limiter.acquire("funding_history", 1)

    assert redis.last_ttl is not None
    assert redis.last_ttl >= 600.0


async def test_bucket_state_ttl_has_a_120s_floor_for_short_windows() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _FakeRedisEval()
    limiter = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=2400, refill_period_s=60.0, clock=clock, sleep=sleeper
    )

    await limiter.acquire("request_weight", 1)

    assert redis.last_ttl == pytest.approx(120.0)


class _RawArgsRedisEval:
    """Captures the raw, un-coerced positional args passed to ``eval``.

    ``_FakeRedisEval`` above re-implements the Lua refill/consume semantics
    in pure Python, so it never actually round-trips an argument the way
    redis-py serializes it for a real Redis command — it could not have
    caught the bug where ``_bucket_state_ttl_s`` was a Python ``float``
    (``120.0``), which redis-py turns into the string ``"120.0"``, which a
    real Redis ``EXPIRE`` then rejects ("value is not an integer or out of
    range"). Asserting on the exact Python type of the captured argument
    does.
    """

    def __init__(self) -> None:
        self.last_args: tuple[Any, ...] | None = None

    async def eval(self, script: str, numkeys: int, *args: Any) -> str:
        self.last_args = args
        return "0"

    async def hset(self, name: str, mapping: dict[str, object]) -> None:
        return None


async def test_acquire_sends_the_redis_ttl_as_an_int_not_a_float() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _RawArgsRedisEval()
    limiter = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=2400, refill_period_s=60.0, clock=clock, sleep=sleeper
    )

    await limiter.acquire("request_weight", 1)

    assert redis.last_args is not None
    ttl_arg = redis.last_args[-1]
    assert isinstance(ttl_arg, int) and not isinstance(ttl_arg, bool)


async def test_record_used_weight_sends_the_redis_ttl_as_an_int_not_a_float() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _RawArgsRedisEval()
    limiter = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=2400, refill_period_s=60.0, clock=clock, sleep=sleeper
    )

    await limiter.record_used_weight("request_weight", used_weight=10)

    assert redis.last_args is not None
    ttl_arg = redis.last_args[-1]
    assert isinstance(ttl_arg, int) and not isinstance(ttl_arg, bool)


# --- F3: record_used_weight must never release in-flight reservations ---


async def test_record_used_weight_never_resurrects_locally_reserved_tokens() -> None:
    """Cold start: 200 concurrent weight-10 acquires reserve 2000 tokens
    locally before any response arrives. The first response's used_weight=10
    header must NOT reset the bucket back up to capacity-10 — that would
    release the 1990 units of weight already reserved by requests still in
    flight (F3)."""
    clock = _FakeClock()

    async def instant_sleep(seconds: float) -> None:
        clock.advance(seconds)

    limiter = TokenBucketRateLimiter(
        "binance", capacity=2400, refill_period_s=60, clock=clock, sleep=instant_sleep
    )

    await asyncio.gather(*[limiter.acquire("request_weight", 10) for _ in range(200)])
    # 2000 reserved -> 400 tokens should remain locally.

    await limiter.record_used_weight("request_weight", used_weight=10)
    # A naive "tokens = capacity - used_weight" would set tokens back to 2390.

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 401, max_wait_s=0.0)
    await limiter.acquire("request_weight", 400, max_wait_s=0.0)  # exactly what remains


async def test_record_used_weight_never_resurrects_redis_reserved_tokens() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _FakeRedisEval()
    limiter = TokenBucketRateLimiter(
        "binance", redis=redis, capacity=2400, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter.acquire("request_weight", 2000)  # simulate 2000 already reserved

    await limiter.record_used_weight("request_weight", used_weight=10)

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 401, max_wait_s=0.0)
    await limiter.acquire("request_weight", 400, max_wait_s=0.0)


# --- F4: a 429 on one bucket must gate every bucket on the same IP ---


async def test_ip_gate_blocks_another_buckets_acquire_after_a_429() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    gate = IpRateGate(clock=clock)
    funding = TokenBucketRateLimiter(
        "binance", capacity=500, refill_period_s=300, clock=clock, sleep=sleeper, ip_gate=gate
    )
    general = TokenBucketRateLimiter(
        "binance", capacity=2400, refill_period_s=60, clock=clock, sleep=sleeper, ip_gate=gate
    )

    await funding.cooldown("funding_history", retry_after_s=60.0)

    with pytest.raises(RateLimited) as exc_info:
        await general.acquire("request_weight", 1, max_wait_s=30.0)
    assert exc_info.value.retry_after_s == pytest.approx(60.0, rel=0.05)


async def test_ip_gate_lifts_once_the_retry_after_deadline_passes() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    gate = IpRateGate(clock=clock)
    funding = TokenBucketRateLimiter(
        "binance", capacity=500, refill_period_s=300, clock=clock, sleep=sleeper, ip_gate=gate
    )
    general = TokenBucketRateLimiter(
        "binance", capacity=2400, refill_period_s=60, clock=clock, sleep=sleeper, ip_gate=gate
    )
    await funding.cooldown("funding_history", retry_after_s=5.0)

    clock.advance(5.1)

    await general.acquire("request_weight", 1, max_wait_s=1.0)  # no longer gated
    assert sleeper.calls == []


async def test_no_ip_gate_means_buckets_stay_fully_independent() -> None:
    """No regression for callers that never pass an ``ip_gate``."""
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    funding = TokenBucketRateLimiter(
        "binance", capacity=500, refill_period_s=300, clock=clock, sleep=sleeper
    )
    general = TokenBucketRateLimiter(
        "binance", capacity=2400, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await funding.cooldown("funding_history", retry_after_s=60.0)

    await general.acquire("request_weight", 1, max_wait_s=0.0)
    assert sleeper.calls == []
