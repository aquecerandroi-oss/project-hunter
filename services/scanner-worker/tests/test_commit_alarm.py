"""The alarm the 30/09 and 02/10 stops should have raised.

Twice the scanner stopped persisting and nothing went red: ``/ready`` and the
heartbeat kept answering for 14 h and then for 2.5 days, because every check
looked at *whether the loop turns* and none at *whether anything reaches the
database* (``obsidian/10-PERFORMANCE/Scanner-lag-2026-10-01.md``). What these
tests pin down:

- cycles failing for more than two minutes with no real commit between turn
  ``/ready`` red, and the heartbeat says when the last commit was;
- a commit that wrote rows ends the streak; an empty flush after a lost batch
  does **not** (Astra, 05/10: it would have reset the alarm every quiet cycle);
- a scanner that is quiet and never fails is **not** an alarm;
- the failed cycle is one short structured log line.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs

from hunter_core.events.outbox import OutboxHealth
from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import Settings
from hunter_scanner_worker import flush_lane, runners
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.consumers import ConsumerHealth
from hunter_scanner_worker.health import (
    MAX_FAILING_S,
    CycleHealth,
    readiness_checks,
    write_heartbeat,
)
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.registry import MarketRef, MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE
from .policies import build_policy
from .test_failure_summary import CONSTRAINT, unique_violation
from .test_health import FakeHeartbeat, FakeRuntime
from .test_load import CUT, MultiMarketHotState

pytestmark = pytest.mark.unit


def test_a_scanner_that_never_fails_is_never_stalled_however_quiet() -> None:
    cycle = CycleHealth()
    cycle.touch(0)
    cycle.touch(200)

    assert cycle.failing_since is None
    assert cycle.persistence_stalled() is False


def test_the_first_failure_starts_the_clock_and_later_ones_do_not_restart_it() -> None:
    cycle = CycleHealth()
    cycle.failed(RuntimeError("one"))
    started = cycle.failing_since
    cycle.failed(RuntimeError("two"))

    assert started is not None
    assert cycle.failing_since == started
    assert (cycle.failures, cycle.failures_total) == (2, 2)


def test_a_real_commit_ends_the_streak_and_keeps_the_loss_counter() -> None:
    cycle = CycleHealth()
    cycle.failed(RuntimeError("one"))

    cycle.committed()

    assert cycle.failing_since is None
    assert cycle.last_commit_at is not None
    assert (cycle.failures, cycle.failures_total) == (0, 1)


def test_a_streak_longer_than_the_limit_is_stalled() -> None:
    cycle = CycleHealth()
    cycle.failed(RuntimeError("one"))
    cycle.failing_since = datetime.now(UTC) - timedelta(seconds=MAX_FAILING_S + 5)

    assert cycle.persistence_stalled() is True

    cycle.failing_since = datetime.now(UTC) - timedelta(seconds=MAX_FAILING_S - 20)

    assert cycle.persistence_stalled() is False


def test_the_limit_is_two_minutes() -> None:
    """~100 failed cycles in a row: longer than a Postgres restart or failover,
    and far under the 14 h it took to notice."""
    assert MAX_FAILING_S == 120.0


def _scanner() -> Scanner:
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(),
        policy=policy,
        registry=MarketRegistry(exchange="binance"),
        state=ScannerState(),
    )
    scanner.cache = BaselineCache(gate=policy.gate)
    return scanner


async def test_readiness_is_red_when_cycles_keep_failing_without_a_commit() -> None:
    cycle = CycleHealth()
    built = readiness_checks(
        _scanner(),
        ConsumerHealth(started_at=datetime.now(UTC)),
        cycle,
        OutboxHealth(last_sweep_at=datetime.now(UTC)),
        ScannerConfig(),
    )
    named = {check.__name__: check for check in built}
    assert "scanner_persistence" in named, "readiness must name the persistence check"
    check = named["scanner_persistence"]
    assert await check() is True

    cycle.failed(RuntimeError("boom"))
    assert await check() is True, "a fresh failure is not yet an outage"

    cycle.failing_since = datetime.now(UTC) - timedelta(minutes=3)
    assert await check() is False

    cycle.committed()
    assert await check() is True


async def test_the_heartbeat_reports_the_last_commit_and_the_failures() -> None:
    redis = FakeHeartbeat()
    scanner = _scanner()
    cycle = CycleHealth()

    async def beat() -> dict[str, str]:
        await write_heartbeat(
            cast("Any", redis),
            cast("Any", FakeRuntime()),
            scanner,
            cycle,
            ConsumerHealth(started_at=datetime.now(UTC)),
        )
        return redis.mapping

    first = await beat()
    # Never committed in this process: an empty string, not an invented time.
    assert first["last_commit_at"] == ""
    assert first["failing_for_s"] == "0"
    assert first["commit_failures"] == "0"
    assert first["commit_failures_total"] == "0"
    assert first["flush_blocked"] == "false"
    cycle.blocked = True
    assert (await beat())["flush_blocked"] == "true"
    cycle.blocked = False

    cycle.failed(RuntimeError("boom"))
    cycle.failing_since = datetime.now(UTC) - timedelta(seconds=90)
    second = await beat()
    assert second["last_commit_at"] == ""
    assert 89 <= int(second["failing_for_s"]) <= 95
    assert second["commit_failures"] == "1"

    cycle.committed()
    third = await beat()
    assert datetime.fromisoformat(third["last_commit_at"]) == cycle.last_commit_at
    assert third["failing_for_s"] == "0"
    assert (third["commit_failures"], third["commit_failures_total"]) == ("0", "1")


def loop_fixture() -> tuple[Scanner, Any, WorkerRuntime]:
    ref = MarketRef(market_id=UUID(int=1), exchange=EXCHANGE, symbol="SYM000USDT")
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE, persist_s=0.0),
        policy=build_policy(),
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply([ref])
    scanner.cache = BaselineCache(gate=scanner.policy.gate)
    market = scanner.state.ensure(ref)
    redis = MultiMarketHotState()
    redis.seed([ref], as_of=CUT)
    market.touch("tick", input_ts=CUT)
    settings = Settings(
        database_url=SecretStr("postgresql+asyncpg://u:p@localhost/x"),
        redis_url=SecretStr("redis://localhost:6379/0"),
    )
    runtime = WorkerRuntime(
        "scanner", settings, engine=cast("Any", None), redis_client=cast("Any", redis)
    )
    return scanner, redis, runtime


async def _run_loop(flush: Any, cycle: CycleHealth, *, seconds: float) -> list[Any]:
    scanner, redis, runtime = loop_fixture()
    original = flush_lane.flush_batch
    flush_lane.flush_batch = flush
    try:
        with capture_logs() as logs, pytest.raises(TimeoutError):
            await asyncio.wait_for(
                runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle),
                seconds,
            )
    finally:
        flush_lane.flush_batch = original
    return logs


async def test_a_failing_flush_starts_the_streak_and_logs_one_short_line() -> None:
    async def refusing(*args: Any, **kwargs: Any) -> set[UUID]:
        raise unique_violation()

    cycle = CycleHealth()
    logs = await _run_loop(refusing, cycle, seconds=0.8)

    assert cycle.last_commit_at is None
    assert cycle.failing_since is not None
    assert cycle.failures >= 1
    failed = [entry for entry in logs if entry["event"] == "scanner_cycle_failed"]
    assert failed, "the failure must still be logged"
    assert failed[0]["constraint"] == CONSTRAINT
    assert "exc_info" not in failed[0] and "exception" not in failed[0]
    assert len(json.dumps(failed[0], default=str)) < 1200


async def test_a_flush_that_writes_rows_is_a_commit() -> None:
    seen: list[bool] = []

    async def accepting(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        seen.append(batch.empty)
        return set()

    cycle = CycleHealth()
    logs = await _run_loop(accepting, cycle, seconds=0.8)

    assert False in seen, "the premise: the evaluation produced rows for this flush"
    assert cycle.last_commit_at is not None
    assert cycle.failing_since is None
    assert not [entry for entry in logs if entry["event"] == "scanner_cycle_failed"]


async def test_a_flush_that_only_acks_is_not_a_commit() -> None:
    """Astra, 05/10: an empty or ACK-only flush proves nothing about the rows a failed
    cycle left behind, so it neither ends the streak nor stamps ``last_commit_at``."""

    async def accepting(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        return set()

    cycle = CycleHealth()
    cycle.failed(RuntimeError("an earlier failure"))
    lane = flush_lane.FlushLane(cast("Any", None), cast("Any", None), cycle)
    lane.batch.acks.append(cast("Any", object()))
    original = flush_lane.flush_batch
    flush_lane.flush_batch = accepting
    try:
        assert await lane.flush() is True
    finally:
        flush_lane.flush_batch = original

    assert cycle.last_commit_at is None
    assert cycle.failing_since is not None
