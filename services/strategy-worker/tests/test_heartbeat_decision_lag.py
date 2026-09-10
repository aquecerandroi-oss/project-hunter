"""``write_heartbeat`` carries the decision-lag p50/p95 (T3.74c).

No database: ``open_trackings`` is passed explicitly, the same shape
``run_heartbeat`` already uses when its own count query fails.
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth
from hunter_strategy_worker.heartbeat import write_heartbeat
from hunter_strategy_worker.metrics import (
    _decision_lag_samples,  # pyright: ignore[reportPrivateUsage]
    observe_decision_lag,
)
from hunter_strategy_worker.outbox import OutboxHealth

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_samples() -> None:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    _decision_lag_samples.clear()


class _Redis:
    def __init__(self) -> None:
        self.hset_calls: list[dict[str, Any]] = []

    async def hset(self, _key: str, mapping: dict[str, Any]) -> None:
        self.hset_calls.append(mapping)

    async def expire(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _Runtime:
    def __init__(self, redis: _Redis) -> None:
        self.instance = "test:1"
        self.redis = redis


async def test_no_signal_yet_writes_empty_strings_not_zero() -> None:
    redis = _Redis()
    await write_heartbeat(_Runtime(redis), ShadowConfig(), ConsumerHealth(), OutboxHealth())  # type: ignore[arg-type]
    payload = redis.hset_calls[0]
    assert payload["decision_lag_p50_s"] == ""
    assert payload["decision_lag_p95_s"] == ""


async def test_a_persisted_signal_shows_up_in_the_heartbeat() -> None:
    observe_decision_lag(4.2)
    redis = _Redis()
    await write_heartbeat(_Runtime(redis), ShadowConfig(), ConsumerHealth(), OutboxHealth())  # type: ignore[arg-type]
    payload = redis.hset_calls[0]
    assert payload["decision_lag_p50_s"] == "4.2"
    assert payload["decision_lag_p95_s"] == "4.2"
