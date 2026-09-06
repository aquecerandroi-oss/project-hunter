"""Two processes on one IP must share one budget (T2.9), against a real Redis.

Each ``TokenBucketRateLimiter`` + ``IpRateGate`` pair below stands for a
separate worker process (a market-worker shard) that happens to share the
egress IP: separate objects, separate in-memory state, one Redis. Nothing here
can be proved with a fake — the point is precisely that the Lua is atomic and
that the deadline is Redis's own clock rather than each process's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any, cast

import pytest
import pytest_asyncio

from hunter_exchanges.base import RateLimited
from hunter_exchanges.rate_limit import IpRateGate, TokenBucketRateLimiter

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from testcontainers.community.redis import RedisContainer

pytestmark = pytest.mark.integration


def _docker_reachable() -> bool:
    try:
        import docker

        docker.from_env().ping()  # type: ignore[reportUnknownMemberType]
    except Exception as exc:
        print(f"Docker is not reachable, skipping integration tests: {exc}")
        return False
    return True


@pytest.fixture(scope="session")
def docker_available() -> bool:
    return _docker_reachable()


@pytest.fixture(scope="session")
def redis_container(docker_available: bool) -> Iterator[RedisContainer]:
    if not docker_available:
        pytest.skip("Docker is not reachable; skipping Redis-backed integration tests")
    from testcontainers.community.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest_asyncio.fixture
async def redis_client(redis_container: RedisContainer) -> AsyncIterator[redis_asyncio.Redis]:
    from pydantic import SecretStr

    from hunter_core.redis import create_redis
    from hunter_core.settings import Settings

    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = create_redis(Settings(redis_url=SecretStr(f"redis://{host}:{port}/0")))
    try:
        await cast(Any, client).flushdb()
        yield client
    finally:
        await client.aclose()


def _process(redis: Any, exchange: str = "binance") -> tuple[TokenBucketRateLimiter, IpRateGate]:
    """One simulated process: its own limiter and gate, the shared Redis."""
    gate = IpRateGate()
    limiter = TokenBucketRateLimiter(exchange, redis=redis, capacity=2400, refill_period_s=60.0)
    limiter.ip_gate = gate
    return limiter, gate


async def test_a_429_in_one_process_stops_the_other_process(
    redis_client: redis_asyncio.Redis,
) -> None:
    """The whole point of moving ``blocked_until`` into Redis: shard A got the
    429, shard B never saw it, and B's very next call would escalate it into an
    IP-wide 418 ban."""
    limiter_a, _gate_a = _process(redis_client)
    limiter_b, _gate_b = _process(redis_client)

    await limiter_a.cooldown("funding_history", retry_after_s=60.0)

    with pytest.raises(RateLimited) as exc_info:
        await limiter_b.acquire("request_weight", 1, max_wait_s=30.0)
    assert exc_info.value.retry_after_s == pytest.approx(60.0, abs=1.0)


async def test_a_shorter_retry_after_never_lifts_a_longer_block(
    redis_client: redis_asyncio.Redis,
) -> None:
    _limiter_a, gate_a = _process(redis_client)
    _limiter_b, gate_b = _process(redis_client)

    await gate_a.block_for(120.0)
    await gate_b.block_for(5.0)

    assert await gate_b.wait_s() == pytest.approx(120.0, abs=1.0)
    assert await gate_a.wait_s() == pytest.approx(120.0, abs=1.0)


async def test_the_shared_block_expires_on_its_own(
    redis_client: redis_asyncio.Redis,
) -> None:
    _limiter_a, gate_a = _process(redis_client)
    _limiter_b, gate_b = _process(redis_client)

    await gate_a.block_for(1.0)
    assert await gate_b.wait_s() > 0

    import asyncio

    await asyncio.sleep(1.2)
    assert await gate_b.wait_s() == 0.0
    assert await gate_a.wait_s() == 0.0


async def test_the_gate_key_is_scoped_to_its_exchange(
    redis_client: redis_asyncio.Redis,
) -> None:
    _binance, binance_gate = _process(redis_client, "binance")
    _bybit, bybit_gate = _process(redis_client, "bybit")

    await binance_gate.block_for(60.0)

    assert await bybit_gate.wait_s() == 0.0
    assert await redis_client.exists("rl:binance:ip:blocked_until") == 1


async def test_a_stale_used_weight_from_another_process_cannot_resurrect_tokens(
    redis_client: redis_asyncio.Redis,
) -> None:
    """The header guard was process-local, so two processes racing on the same
    Redis key could reorder: B's older ``used_weight=10`` overwrote A's fresher
    ``2390`` and re-opened budget the exchange had already spent."""
    limiter_a, _gate_a = _process(redis_client)
    limiter_b, _gate_b = _process(redis_client)

    await limiter_a.record_used_weight("request_weight", used_weight=2390)
    await limiter_b.record_used_weight("request_weight", used_weight=10)

    tokens = float(await redis_client.hget("rl:binance:request_weight", "tokens"))  # type: ignore[arg-type]
    assert tokens <= 10.0 + 1.0, "the stale reading must not have raised the budget"

    with pytest.raises(RateLimited):
        await limiter_b.acquire("request_weight", 100, max_wait_s=0.5)


async def test_a_higher_used_weight_from_any_process_still_shrinks_the_bucket(
    redis_client: redis_asyncio.Redis,
) -> None:
    limiter_a, _gate_a = _process(redis_client)
    limiter_b, _gate_b = _process(redis_client)

    await limiter_a.record_used_weight("request_weight", used_weight=10)
    await limiter_b.record_used_weight("request_weight", used_weight=2399)

    tokens = float(await redis_client.hget("rl:binance:request_weight", "tokens"))  # type: ignore[arg-type]
    assert tokens == pytest.approx(1.0, abs=1.0)


class _Down:
    """A client that accepts calls and answers none of them."""

    async def eval(self, *_args: Any, **_kwargs: Any) -> object:
        raise ConnectionError("redis is down")


async def test_two_shards_admit_nothing_while_redis_is_down_then_share_one_window(
    redis_client: redis_asyncio.Redis,
) -> None:
    """Astra's reproduction, against a real server. With the in-memory
    fallback the two shards admitted 4800 units of weight — two full quotas
    against the one quota Binance accounts per IP. Fail-closed admits zero,
    and the recovery is not a compensating burst either: the two shards
    together get one window's capacity, not one each."""
    limiter_a, _gate_a = _process(redis_client)
    limiter_b, _gate_b = _process(redis_client)
    for limiter in (limiter_a, limiter_b):
        limiter._redis = _Down()  # type: ignore[assignment] # pyright: ignore[reportPrivateUsage]

    admitted = 0
    for limiter in (limiter_a, limiter_b):
        for _ in range(24):
            try:
                await limiter.acquire("request_weight", 100, max_wait_s=0.0)
            except RateLimited:
                continue
            admitted += 100

    assert admitted == 0
    assert limiter_a.suspended is True and limiter_b.suspended is True

    for limiter in (limiter_a, limiter_b):
        limiter._redis = redis_client  # type: ignore[assignment] # pyright: ignore[reportPrivateUsage]
    spent = 0
    for index in range(60):  # more attempts than one window can ever pay for
        limiter = limiter_a if index % 2 == 0 else limiter_b
        try:
            await limiter.acquire("request_weight", 100, max_wait_s=0.0)
        except RateLimited:
            break
        spent += 100

    assert limiter_a.suspended is False
    # 2400 = one window; the slack is the refill earned while the loop ran.
    assert 2400 <= spent <= 2800


async def test_a_block_taken_while_redis_was_down_is_republished_on_recovery(
    redis_client: redis_asyncio.Redis,
) -> None:
    """Astra, round 2. Shard A takes a 60s block during a Redis outage, so the
    shared write fails and only A's mirror holds it. Redis comes back with no
    key: without re-publication, shard B reads zero and keeps calling into a
    ban that is still live."""
    limiter_a, gate_a = _process(redis_client)
    _limiter_b, gate_b = _process(redis_client)

    class _Down:
        async def eval(self, *_args: Any, **_kwargs: Any) -> object:
            raise ConnectionError("redis is down")

    limiter_a.ip_gate = gate_a  # already bound; keep the pair explicit
    gate_a._redis = _Down()  # type: ignore[assignment] # pyright: ignore[reportPrivateUsage]
    await gate_a.block_for(60.0)
    assert gate_a.degraded is True
    assert await gate_b.wait_s() == 0.0, "B cannot know yet — that is the bug"

    gate_a._redis = redis_client  # type: ignore[assignment] # pyright: ignore[reportPrivateUsage]
    assert await gate_a.wait_s() == pytest.approx(60.0, abs=2.0)

    assert await gate_b.wait_s() == pytest.approx(60.0, abs=2.0)
