"""The IP gate's local half: binding, mirroring and the Redis-outage fallback.

Cross-process coordination is only provable against a real server, so it lives
in ``tests/integration/test_rate_limit_gate_integration.py``. What is unit
tested here is everything that must keep working when Redis does not.
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_exchanges.rate_limit import IpRateGate, TokenBucketRateLimiter

pytestmark = pytest.mark.unit


class _FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _DeadRedis:
    """Accepts the connection, answers nothing — the interesting outage."""

    def __init__(self) -> None:
        self.calls = 0

    async def eval(self, *_args: Any, **_kwargs: Any) -> object:
        self.calls += 1
        raise ConnectionError("redis is down")

    async def hset(self, *_args: Any, **_kwargs: Any) -> object:
        raise ConnectionError("redis is down")


async def test_an_unbound_gate_is_purely_local() -> None:
    clock = _FakeClock()
    gate = IpRateGate(clock=clock)

    await gate.block_for(60.0)

    assert await gate.wait_s() == pytest.approx(60.0)
    clock.advance(60.1)
    assert await gate.wait_s() == 0.0


async def test_a_block_never_shortens() -> None:
    clock = _FakeClock()
    gate = IpRateGate(clock=clock)

    await gate.block_for(60.0)
    await gate.block_for(5.0)

    assert await gate.wait_s() == pytest.approx(60.0)


async def test_a_non_positive_block_is_ignored() -> None:
    gate = IpRateGate(clock=_FakeClock())
    await gate.block_for(0.0)
    await gate.block_for(-5.0)
    assert await gate.wait_s() == 0.0


async def test_binding_a_limiters_redis_is_what_makes_the_gate_shared() -> None:
    """``BinanceRestClient`` builds a bare ``IpRateGate()`` and assigns it to
    both limiters; the assignment is what hands it the shared Redis, so the
    gate is coordinated without that call site having to know about Redis."""
    redis = _DeadRedis()
    limiter = TokenBucketRateLimiter("binance", redis=redis)
    gate = IpRateGate()
    assert gate.bound_to is None

    limiter.ip_gate = gate

    assert gate.bound_to == ("binance", id(redis))


async def test_binding_is_idempotent_and_never_switches_exchange() -> None:
    """A second bind to a *different* exchange would silently move the gate's
    key, quietly un-blocking an IP that is still banned."""
    redis = _DeadRedis()
    gate = IpRateGate()
    TokenBucketRateLimiter("binance", redis=redis).ip_gate = gate
    TokenBucketRateLimiter("binance", redis=redis).ip_gate = gate  # same pair: fine

    with pytest.raises(ValueError, match="already bound"):
        TokenBucketRateLimiter("bybit", redis=redis).ip_gate = gate


async def test_a_block_is_remembered_locally_even_when_redis_refuses_it() -> None:
    """Astra's scenario A: coordination fails, but a block this process *knows*
    about must never be forgotten — otherwise a 429 turns into an immediate
    retry and escalates into an IP ban."""
    clock = _FakeClock()
    redis = _DeadRedis()
    gate = IpRateGate(clock=clock)
    TokenBucketRateLimiter("binance", redis=redis).ip_gate = gate

    await gate.block_for(60.0)

    assert redis.calls == 1, "it did try to coordinate"
    assert await gate.wait_s() == pytest.approx(60.0), "and kept the block anyway"
    assert gate.degraded is True


async def test_the_gate_recovers_from_degraded_once_redis_answers() -> None:
    class _FlakyRedis(_DeadRedis):
        healthy = False

        async def eval(self, *args: Any, **kwargs: Any) -> object:
            if not self.healthy:
                return await super().eval(*args, **kwargs)
            return "0"

    clock = _FakeClock()
    redis = _FlakyRedis()
    gate = IpRateGate(clock=clock)
    TokenBucketRateLimiter("binance", redis=redis).ip_gate = gate

    await gate.block_for(1.0)
    assert gate.degraded is True

    redis.healthy = True
    clock.advance(1.1)
    assert await gate.wait_s() == 0.0
    assert gate.degraded is False


async def test_the_limiter_awaits_the_gate_before_spending_a_token() -> None:
    clock = _FakeClock()
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)
        clock.advance(seconds)

    gate = IpRateGate(clock=clock)
    limiter = TokenBucketRateLimiter("binance", clock=clock, sleep=sleeper, ip_gate=gate)
    await gate.block_for(2.0)

    await limiter.acquire("request_weight", 1, max_wait_s=10.0)

    assert slept == [pytest.approx(2.0)]


async def test_a_429_still_blocks_the_ip_when_redis_is_unreachable() -> None:
    """Astra, round 2. Two separate holes closed by one test:

    ``cooldown`` used to reconcile the bucket *before* opening the gate, so an
    exception from that call left the IP unblocked right after a 429. And
    ``record_used_weight`` used to propagate a Redis failure — which matters
    because ``BinanceRestClient._get`` reconciles the used-weight header
    **before** it inspects the status code, so the exception skipped the
    ``429``/``418`` branch entirely and no cooldown was ever applied.
    """
    clock = _FakeClock()
    gate = IpRateGate(clock=clock)
    limiter = TokenBucketRateLimiter("binance", redis=_DeadRedis(), clock=clock, ip_gate=gate)

    # the header reconciliation the REST client runs first: suspended, not fatal
    await limiter.record_used_weight("request_weight", used_weight=1200)
    assert limiter.suspended is True

    await limiter.cooldown("request_weight", retry_after_s=60.0)

    assert await gate.wait_s() == pytest.approx(60.0)
