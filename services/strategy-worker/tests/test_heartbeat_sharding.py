"""``write_heartbeat``/``run_heartbeat`` per shard (T3.74f)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from hunter_strategy_worker.config import HEARTBEAT_KEY
from hunter_strategy_worker.consumer import ConsumerHealth
from hunter_strategy_worker.heartbeat import run_heartbeat, write_heartbeat
from hunter_strategy_worker.metrics import (
    _decision_lag_samples,  # pyright: ignore[reportPrivateUsage]
)
from hunter_strategy_worker.outbox import OutboxHealth

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_samples() -> None:  # pyright: ignore[reportUnusedFunction]
    _decision_lag_samples.clear()


class _Redis:
    def __init__(self) -> None:
        self.hset_calls: list[tuple[str, dict[str, Any]]] = []
        self.expired_keys: list[str] = []

    async def hset(self, key: str, mapping: dict[str, Any]) -> None:
        self.hset_calls.append((key, mapping))

    async def expire(self, key: str, *_args: Any, **_kwargs: Any) -> None:
        self.expired_keys.append(key)


class _Runtime:
    def __init__(self, redis: _Redis) -> None:
        self.instance = "test:1"
        self.redis = redis


async def test_solo_deployment_writes_the_classic_key_unchanged() -> None:
    redis = _Redis()
    await write_heartbeat(_Runtime(redis), _config(), ConsumerHealth(), OutboxHealth())  # type: ignore[arg-type]
    key, payload = redis.hset_calls[0]
    assert key == HEARTBEAT_KEY
    assert payload["shard_index"] == "0"
    assert payload["shard_total"] == "1"


async def test_a_shard_writes_its_own_suffixed_key() -> None:
    redis = _Redis()
    await write_heartbeat(
        _Runtime(redis),  # type: ignore[arg-type]
        _config(),
        ConsumerHealth(),
        OutboxHealth(),
        shard_index=2,
        shard_total=4,
    )
    key, payload = redis.hset_calls[0]
    assert key == f"{HEARTBEAT_KEY}:2of4"
    assert payload["shard_index"] == "2"
    assert payload["shard_total"] == "4"


@pytest.mark.parametrize(("shard_index", "expect_query"), [(0, True), (1, False)])
async def test_run_heartbeat_gates_the_open_trackings_query_to_shard_zero(
    monkeypatch: pytest.MonkeyPatch, shard_index: int, expect_query: bool
) -> None:
    """Non-leader shards must never pay for ``load_open_trackings`` -- it is
    unpartitioned by design, so N shards each running it would multiply
    Postgres load for a cluster-wide number none of them owns alone. Every
    piece of the query path is faked and counted so the assertion is about
    whether it ran at all, not whether a real database was reachable."""
    from contextlib import asynccontextmanager

    import hunter_core.db.session as db_session_mod
    import hunter_strategy_worker.heartbeat as heartbeat_mod

    calls = 0

    def fake_factory(_engine: Any) -> Any:
        return object()

    @asynccontextmanager
    async def fake_role_session(*_a: Any, **_kw: Any) -> AsyncGenerator[object]:
        yield object()

    async def fake_load_open_trackings(*_a: Any, **_kw: Any) -> list[int]:
        nonlocal calls
        calls += 1
        return [1, 2, 3]

    async def fake_sleep(_delay: float) -> None:
        raise StopAsyncIteration

    monkeypatch.setattr(db_session_mod, "create_session_factory", fake_factory)
    monkeypatch.setattr(heartbeat_mod, "role_session", fake_role_session)
    monkeypatch.setattr(heartbeat_mod, "load_open_trackings", fake_load_open_trackings)
    monkeypatch.setattr(heartbeat_mod.asyncio, "sleep", fake_sleep)

    redis = _Redis()
    runtime = _Runtime(redis)
    runtime.engine = object()  # type: ignore[attr-defined]
    with pytest.raises(StopAsyncIteration):
        await run_heartbeat(
            runtime,  # type: ignore[arg-type]
            _config(),
            ConsumerHealth(),
            OutboxHealth(),
            shard_index=shard_index,
            shard_total=4,
        )
    assert (calls > 0) is expect_query
    _key, payload = redis.hset_calls[0]
    assert payload["open_trackings"] == ("3" if expect_query else "")


def _config() -> Any:
    from hunter_strategy_worker.config import ShadowConfig

    return ShadowConfig()
