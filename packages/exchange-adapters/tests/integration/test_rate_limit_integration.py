"""Integration test for TokenBucketRateLimiter against a real Redis.

Regression coverage for the incident where ``_bucket_state_ttl_s`` was a
Python ``float`` (120.0): redis-py serializes that to the argument string
``"120.0"``, and a real Redis ``EXPIRE`` rejects it with "value is not an
integer or out of range" — a class of bug the pure-Python
``_FakeRedisEval`` in ``tests/unit/test_rate_limit.py`` cannot catch, since
it re-implements the Lua semantics itself instead of round-tripping
arguments through an actual Redis server.

Uses the ``redis:7-alpine`` testcontainer, matching
``packages/core/tests/conftest.py``'s convention; skips cleanly (with the
reason printed) when Docker is unreachable, and is never in CI (marked
``integration``, same as every other Postgres/Redis-backed test here).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any, cast

import pytest
import pytest_asyncio

from hunter_exchanges.rate_limit import TokenBucketRateLimiter

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
    settings = Settings(redis_url=SecretStr(f"redis://{host}:{port}/0"))
    client = create_redis(settings)
    try:
        yield client
    finally:
        await client.aclose()


async def test_acquire_against_real_redis_does_not_raise_on_expire(
    redis_client: redis_asyncio.Redis,
) -> None:
    """This is the exact failure from the incident report: a real Redis
    ``EXPIRE`` receiving the TTL. Before the fix this raised
    ``redis.exceptions.ResponseError: value is not an integer or out of
    range`` on every single call — i.e. every ``list_markets`` / REST call
    the market-worker ever made."""
    limiter = TokenBucketRateLimiter(
        "binance", redis=cast(Any, redis_client), capacity=2400, refill_period_s=60.0
    )

    # Must not raise. Before the fix, this always raised ResponseError.
    await limiter.acquire("request_weight", 1)

    key = "rl:binance:request_weight"
    ttl = await redis_client.ttl(key)
    assert ttl > 0  # the key was actually given a TTL, not left to live forever

    await redis_client.delete(key)


async def test_record_used_weight_against_real_redis_does_not_raise_on_expire(
    redis_client: redis_asyncio.Redis,
) -> None:
    limiter = TokenBucketRateLimiter(
        "binance", redis=cast(Any, redis_client), capacity=2400, refill_period_s=60.0
    )

    # Must not raise either — the same TTL bug affected this script's EXPIRE.
    await limiter.record_used_weight("request_weight", used_weight=10)

    key = "rl:binance:request_weight"
    ttl = await redis_client.ttl(key)
    assert ttl > 0

    await redis_client.delete(key)
