"""Fail-closed admissions while the shared rate-limit coordination is down (T2.9).

The M2 acceptance line for T2.9 says the limiter runs "sem orcamento
independente durante indisponibilidade": with Redis unreachable there is no
local budget to fall back to, because N shards each spending a full local
bucket add up to N quotas against one shared IP quota, and the price of that
mistake is a Binance IP ban. So ``acquire`` suspends instead of admitting,
says why (``redis_unavailable``), backs off with jitter and retries.
"""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest

from hunter_exchanges.base import RateLimited
from hunter_exchanges.binance import BinanceAdapter
from hunter_exchanges.binance.rest import BinanceRestClient
from hunter_exchanges.rate_limit import IpRateGate, TokenBucketRateLimiter
from hunter_exchanges.rate_limit_lua import BLOCK_IP_SCRIPT, IP_WAIT_SCRIPT
from hunter_exchanges.rate_limit_suspension import (
    BACKOFF_BASE_S,
    BACKOFF_JITTER,
    BACKOFF_MAX_S,
    REDIS_UNAVAILABLE,
    REST_GATE_OK,
    REST_GATE_SUSPENDED,
    backoff_s,
    rest_admissions_suspended_total,
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
    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


class _DeadRedis:
    """Accepts the connection, answers nothing — the interesting outage."""

    def __init__(self) -> None:
        self.calls = 0

    async def eval(self, *_args: Any, **_kwargs: Any) -> object:
        self.calls += 1
        raise ConnectionError("redis is down")

    async def hset(self, *_args: Any, **_kwargs: Any) -> object:
        raise ConnectionError("redis is down")


class _FlakyRedis:
    """A real-enough bucket that refuses to answer until ``healthy``."""

    def __init__(self, capacity: float, refill_per_s: float) -> None:
        self.healthy = False
        self.tokens = capacity
        self.ts: float | None = None
        self._capacity = capacity
        self._refill_per_s = refill_per_s

    async def eval(self, _script: str, _numkeys: int, *args: Any) -> str:
        if not self.healthy:
            raise ConnectionError("redis is down")
        weight, now = float(args[3]), float(args[4])
        if self.ts is None:
            self.ts = now
        self.tokens = min(
            self._capacity, self.tokens + max(0.0, now - self.ts) * self._refill_per_s
        )
        self.ts = now
        if self.tokens < weight:
            return str((weight - self.tokens) / self._refill_per_s)
        self.tokens -= weight
        return "0"

    async def hset(self, *_args: Any, **_kwargs: Any) -> object:
        return None


def _limiter(redis: Any, clock: _FakeClock, sleeper: _NoopSleepRecorder) -> TokenBucketRateLimiter:
    return TokenBucketRateLimiter(
        "binance", redis=redis, capacity=2400, refill_period_s=60.0, clock=clock, sleep=sleeper
    )


async def _admitted(limiter: TokenBucketRateLimiter, attempts: int) -> int:
    admitted = 0
    for _ in range(attempts):
        try:
            await limiter.acquire("request_weight", 1, max_wait_s=0.0)
        except RateLimited:
            continue
        admitted += 1
    return admitted


async def test_two_processes_admit_nothing_while_redis_is_down() -> None:
    """Astra's reproduction: two shards, Redis down, 2400 attempts each. The
    in-memory fallback admitted all 4800 — two full quotas against one shared
    IP budget. Fail-closed admits zero."""
    clock = _FakeClock()
    redis = _DeadRedis()
    shard_a = _limiter(redis, clock, _NoopSleepRecorder(clock))
    shard_b = _limiter(redis, clock, _NoopSleepRecorder(clock))

    admitted = await _admitted(shard_a, 2400) + await _admitted(shard_b, 2400)

    assert admitted == 0
    assert shard_a.suspended is True
    assert shard_b.suspended is True


async def test_a_suspended_acquire_says_why_instead_of_leaking_a_redis_error() -> None:
    clock = _FakeClock()
    limiter = _limiter(_DeadRedis(), clock, _NoopSleepRecorder(clock))

    with pytest.raises(RateLimited) as exc_info:
        await limiter.acquire("request_weight", 1, max_wait_s=0.0)

    assert exc_info.value.reason == REDIS_UNAVAILABLE
    assert exc_info.value.exchange == "binance"
    assert limiter.suspension_reason == REDIS_UNAVAILABLE


async def test_a_suspended_acquire_retries_a_few_times_before_giving_up() -> None:
    """Nothing here may kill the caller's loop: the outage is reported as a
    ``RateLimited`` the worker already knows how to survive, after a bounded
    number of short retries."""
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = _limiter(_DeadRedis(), clock, sleeper)

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 1, max_wait_s=5.0)

    assert sleeper.calls, "it retried instead of giving up on the first failure"
    assert all(0 < delay <= BACKOFF_MAX_S * (1 + BACKOFF_JITTER) for delay in sleeper.calls)
    assert sum(sleeper.calls) <= 5.0


def test_the_backoff_grows_and_is_jittered_and_capped() -> None:
    assert backoff_s(0, rand=lambda: 0.0) == pytest.approx(BACKOFF_BASE_S)
    assert backoff_s(1, rand=lambda: 0.0) == pytest.approx(BACKOFF_BASE_S * 2)
    assert backoff_s(0, rand=lambda: 1.0) == pytest.approx(BACKOFF_BASE_S * (1 + BACKOFF_JITTER))
    assert backoff_s(20, rand=lambda: 0.0) == pytest.approx(BACKOFF_MAX_S)
    assert backoff_s(20, rand=lambda: 1.0) == pytest.approx(BACKOFF_MAX_S * (1 + BACKOFF_JITTER))


async def test_admissions_resume_by_themselves_once_redis_answers() -> None:
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _FlakyRedis(capacity=2400, refill_per_s=40.0)
    limiter = _limiter(redis, clock, sleeper)

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 1, max_wait_s=0.0)
    assert limiter.suspended is True

    redis.healthy = True
    await limiter.acquire("request_weight", 1, max_wait_s=5.0)

    assert limiter.suspended is False
    assert limiter.suspension_reason is None


async def test_recovery_never_admits_a_compensating_burst() -> None:
    """The outage does not build up credit. When Redis comes back the shared
    bucket is worth one window's capacity, not one window per minute spent
    waiting — the refill is capped at ``capacity`` and nothing local
    accumulated meanwhile."""
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    redis = _FlakyRedis(capacity=2400, refill_per_s=40.0)
    limiter = _limiter(redis, clock, sleeper)

    for _ in range(50):  # a long outage: nothing is admitted, nothing is owed
        with pytest.raises(RateLimited):
            await limiter.acquire("request_weight", 10, max_wait_s=0.0)
        clock.advance(60.0)

    redis.healthy = True
    await limiter.acquire("request_weight", 2400, max_wait_s=0.0)  # exactly one window

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 1, max_wait_s=0.0)


async def test_record_used_weight_suspends_instead_of_raising() -> None:
    """``BinanceRestClient._get`` reconciles the header before it inspects the
    status code, so an exception here would skip the 429/418 cooldown."""
    clock = _FakeClock()
    limiter = _limiter(_DeadRedis(), clock, _NoopSleepRecorder(clock))

    await limiter.record_used_weight("request_weight", used_weight=1200)

    assert limiter.suspended is True
    assert limiter.suspension_reason == REDIS_UNAVAILABLE


async def test_every_refused_admission_is_counted() -> None:
    clock = _FakeClock()
    limiter = _limiter(_DeadRedis(), clock, _NoopSleepRecorder(clock))
    metric = rest_admissions_suspended_total.labels(
        exchange="binance", bucket="request_weight", reason=REDIS_UNAVAILABLE
    )
    before = float(cast(Any, metric)._value.get())  # pyright: ignore[reportPrivateUsage]

    await _admitted(limiter, 3)

    after = float(cast(Any, metric)._value.get())  # pyright: ignore[reportPrivateUsage]
    assert after == before + 3


async def test_the_rest_client_and_the_adapter_report_the_gate_status() -> None:
    """What the market-worker's heartbeat publishes as ``rest_gate``: a
    degradation an operator can see, not a readiness failure."""
    clock = _FakeClock()
    limiter = _limiter(_DeadRedis(), clock, _NoopSleepRecorder(clock))
    rest = BinanceRestClient(http_client=httpx.AsyncClient(), rate_limiter=limiter)
    adapter = BinanceAdapter(rest=rest)
    try:
        assert rest.rest_gate_status() == REST_GATE_OK

        with pytest.raises(RateLimited):
            await limiter.acquire("request_weight", 1, max_wait_s=0.0)

        assert rest.rest_gate_status() == REST_GATE_SUSPENDED
        assert adapter.rest_gate_status() == REST_GATE_SUSPENDED
    finally:
        await rest.aclose()


async def test_a_limiter_with_no_redis_configured_keeps_its_own_bucket() -> None:
    """No coordination was ever asked for (unit tests, a one-process client):
    that is not an outage, so nothing is suspended."""
    clock = _FakeClock()
    sleeper = _NoopSleepRecorder(clock)
    limiter = TokenBucketRateLimiter(
        "binance", capacity=10, refill_period_s=60, clock=clock, sleep=sleeper
    )

    await limiter.acquire("request_weight", 10, max_wait_s=0.0)

    assert limiter.suspended is False
    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 1, max_wait_s=0.0)


class _PartialRedis:
    """The interesting partial outage: the bucket answers, the IP gate does not.

    A read timeout on one key while another succeeds is ordinary Redis under
    load, not a fantasy — and it is the shape that used to slip through.
    """

    def __init__(self) -> None:
        self.admitted_probes = 0

    async def eval(self, script: str, _numkeys: int, *_args: Any) -> object:
        if script is IP_WAIT_SCRIPT or script is BLOCK_IP_SCRIPT:
            raise ConnectionError("redis is down for this key")
        self.admitted_probes += 1
        return "0"  # the bucket happily says "there is budget"

    async def hset(self, *_args: Any, **_kwargs: Any) -> object:
        return None


async def test_an_unreadable_ip_gate_suspends_instead_of_admitting() -> None:
    """Astra, T2.9 round 3: ``IpRateGate.wait_s()`` falls back to this
    process's local mirror when the shared deadline cannot be read. With an
    empty mirror that is ``0`` — "not blocked" — so a 429 another shard
    already took would be invisible and this process would walk straight into
    the ban the gate exists to prevent. An unreadable gate is coordination
    being down, and coordination being down means admitting nothing."""
    clock = _FakeClock()
    redis: Any = _PartialRedis()
    limiter = TokenBucketRateLimiter(
        "binance",
        redis=redis,
        capacity=2400,
        refill_period_s=60.0,
        clock=clock,
        sleep=_NoopSleepRecorder(clock),
        ip_gate=IpRateGate(),
    )

    admitted = await _admitted(limiter, 10)

    assert admitted == 0
    assert limiter.suspension_reason == REDIS_UNAVAILABLE
