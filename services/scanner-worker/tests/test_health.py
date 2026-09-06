"""Readiness: what makes the scanner red, and what deliberately does not.

Every case here came out of the operational proof. The first one turned
``/ready`` red for half an hour on a perfectly healthy worker, because a stream
that publishes sixty events in thirty minutes looks exactly like a stuck loop if
you only ever record progress when a message arrives.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hunter_core.events.outbox import OutboxHealth
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.consumers import ConsumerHealth
from hunter_scanner_worker.health import CycleHealth, readiness_checks
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .policies import build_policy

NOW = datetime.now(UTC)
QUIET_STREAM = "market.liquidations"


class FakeStreams:
    """``XREVRANGE`` only: the newest id of each stream, or nothing."""

    def __init__(self, newest: dict[str, datetime | None]) -> None:
        self.newest = newest

    async def xrevrange(self, stream: str, count: int = 1) -> list[Any]:
        del count
        moment = self.newest.get(stream)
        if moment is None:
            return []
        return [(f"{int(moment.timestamp() * 1000)}-0", {})]


def _checks(
    consumers: ConsumerHealth, redis: Any, *, cycle: CycleHealth | None = None
) -> dict[str, Any]:
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(),
        policy=policy,
        registry=MarketRegistry(exchange="binance"),
        state=ScannerState(),
    )
    scanner.cache = BaselineCache(gate=policy.gate)
    outbox = OutboxHealth(last_sweep_at=NOW)
    built = readiness_checks(
        scanner, consumers, cycle or CycleHealth(), outbox, ScannerConfig(), redis
    )
    return {check.__name__: check for check in built}


async def test_a_quiet_stream_is_idle_not_stuck() -> None:
    consumers = ConsumerHealth(started_at=NOW - timedelta(minutes=30))
    consumers.last_iteration_at[QUIET_STREAM] = NOW - timedelta(minutes=25)
    # The stream itself has published nothing since the consumer last moved.
    redis = FakeStreams({QUIET_STREAM: NOW - timedelta(minutes=25)})

    assert await _checks(consumers, redis)["scanner_consumers"]() is True


async def test_a_consumer_that_fell_behind_a_moving_stream_is_red() -> None:
    consumers = ConsumerHealth(started_at=NOW - timedelta(minutes=30))
    consumers.last_iteration_at[QUIET_STREAM] = NOW - timedelta(minutes=25)
    # The stream moved on without it: that is a stuck loop, and the only case
    # this check exists to catch.
    redis = FakeStreams({QUIET_STREAM: NOW - timedelta(seconds=5)})

    assert await _checks(consumers, redis)["scanner_consumers"]() is False


async def test_a_stream_nobody_ever_published_to_does_not_hold_readiness_down() -> None:
    consumers = ConsumerHealth(started_at=NOW - timedelta(minutes=30))
    consumers.last_iteration_at[QUIET_STREAM] = NOW - timedelta(minutes=25)
    redis = FakeStreams({QUIET_STREAM: None})

    assert await _checks(consumers, redis)["scanner_consumers"]() is True


async def test_a_worker_with_no_consumers_at_all_is_red() -> None:
    consumers = ConsumerHealth(started_at=NOW)

    assert await _checks(consumers, FakeStreams({}))["scanner_consumers"]() is False


async def test_a_stalled_evaluation_cycle_is_red_even_with_healthy_consumers() -> None:
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    cycle = CycleHealth()
    cycle.last_cycle_at = NOW - timedelta(minutes=5)

    checks = _checks(consumers, FakeStreams({}), cycle=cycle)
    # This is the check that matters most: consumers that mark work nobody
    # performs would otherwise report a perfectly healthy worker producing
    # nothing.
    assert await checks["scanner_evaluation"]() is False


async def test_an_empty_baseline_archive_is_not_a_readiness_failure() -> None:
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    cycle = CycleHealth()
    cycle.baselines_loaded = True

    checks = _checks(consumers, FakeStreams({}), cycle=cycle)
    # A fresh install has no seven-day history. "Under construction" is a state
    # the Radar shows, not a reason to refuse traffic; what would be a failure
    # is not knowing, which is what ``baselines_loaded`` records.
    assert await checks["scanner_baselines"]() is True
