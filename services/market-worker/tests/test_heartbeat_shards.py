"""T2.5g — one heartbeat per shard, so N shards can never overwrite each other.

``.claude/state/brief-T2.5g-collector-latency-shards.md`` item 2: with
``MARKET_SHARD=i/N`` and ``N > 1`` every shard owns
``hb:market:{exchange}:{i}of{N}`` and the API unions them. A single shared
``hb:market:{exchange}`` is what kept the 200 already-proven markets from being
delivered in M1 (``milestone.json`` ``m1_result``): four shards writing the same
hash makes a dead shard invisible and the System page a liar.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from hunter_core.domain.types import utcnow
from hunter_core.redis import keys
from hunter_core.settings import Settings
from hunter_market_worker import heartbeat
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.universe import MonitoredUniverse

from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


def _universe(*symbols: str) -> MonitoredUniverse:
    universe = MonitoredUniverse()
    universe.set(list(symbols))
    return universe


async def test_the_solo_worker_keeps_writing_the_classic_per_exchange_key(
    redis_client: Any,
) -> None:
    """``MARKET_SHARD=0/1`` must not change a single byte of the key a running
    deployment (and ``/system/market-status``) already reads."""
    code = unique_code()
    await heartbeat._write_hash(  # pyright: ignore[reportPrivateUsage]
        redis_client,
        code,
        _universe("BTCUSDT"),
        HeartbeatState(),
        "connected",
        utcnow(),
        shard_index=0,
        shard_total=1,
    )

    assert await redis_client.exists(f"hb:market:{code}") == 1
    fields = await redis_client.hgetall(f"hb:market:{code}")
    assert fields[b"shard_index"] == b"0"
    assert fields[b"shard_total"] == b"1"


async def test_a_sharded_worker_owns_its_own_key_and_never_the_shared_one(
    redis_client: Any,
) -> None:
    code = unique_code()
    for index in (0, 1):
        await heartbeat._write_hash(  # pyright: ignore[reportPrivateUsage]
            redis_client,
            code,
            _universe(f"SYM{index}USDT"),
            HeartbeatState(),
            "connected",
            utcnow(),
            shard_index=index,
            shard_total=2,
        )

    assert await redis_client.exists(f"hb:market:{code}") == 0
    for index in (0, 1):
        key = keys.market_heartbeat(code, index, 2)
        assert key == f"hb:market:{code}:{index}of2"
        fields = await redis_client.hgetall(key)
        assert fields[b"shard_index"] == str(index).encode()
        assert fields[b"shard_total"] == b"2"
        assert fields[b"markets_monitored"] == b"1"
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= heartbeat.HB_TTL_S


async def test_run_heartbeat_of_a_shard_writes_the_shard_key_and_stays_off_rt_system(
    db_session_factory: Any, redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shard knows only its own slice, so a ``rt:system`` patch from it would
    replace the whole exchange row on the System page with 1 of N shards'
    numbers (``apps/web/components/system/live-status.tsx``
    ``mergeExchangeUpdate``). In sharded mode the aggregate on
    ``/system/market-status`` is the only truth; nobody publishes the live
    patch."""
    monkeypatch.setattr(heartbeat, "HEARTBEAT_INTERVAL_S", 0.01)
    code = unique_code()
    adapter = FakeAdapter(code=code)
    runtime: Any = FakeRuntime(redis=redis_client, settings=Settings(market_shard="2/4"))
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("rt:system")
    task = asyncio.ensure_future(
        heartbeat.run_heartbeat(
            runtime, adapter, _universe("BTCUSDT"), HeartbeatState(), db_session_factory
        )
    )
    try:
        async with asyncio.timeout(5):
            await runtime.success.wait()
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
        assert message is None, "a shard must not patch the whole exchange row on rt:system"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await pubsub.aclose()

    fields = await redis_client.hgetall(f"hb:market:{code}:2of4")
    assert fields[b"shard_index"] == b"2"
    assert fields[b"shard_total"] == b"4"
    assert await redis_client.exists(f"hb:market:{code}") == 0
