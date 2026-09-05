"""HIGH-3: a missing future partition must show up on ``/ready`` and log a
CRITICAL ``system_event`` — not be discovered by a failed insert months later."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_market_worker import partitions
from hunter_market_worker.partitions import (
    PartitionReadiness,
    PartitionsMissing,
    assert_writable_partitions,
)

pytestmark = pytest.mark.integration


async def test_ready_when_the_target_partition_exists(db_session_factory: Any) -> None:
    checker = PartitionReadiness(db_session_factory)
    assert await checker.ready() is True


async def test_not_ready_and_records_a_critical_system_event_for_a_missing_partition(
    db_session_factory: Any,
) -> None:
    far_future = datetime(2027, 2, 1, tzinfo=UTC)
    checker = PartitionReadiness(db_session_factory, now=lambda: far_future)

    assert await checker.ready() is False

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(SystemEvent)
            .where(SystemEvent.event == "partition_missing")
            .order_by(SystemEvent.created_at.desc())
        )
    assert row is not None and row.level.value == "critical"


async def test_recheck_interval_avoids_a_query_on_every_probe(db_session_factory: Any) -> None:
    calls = 0
    clock_value = 0.0

    def fake_clock() -> float:
        return clock_value

    checker = PartitionReadiness(db_session_factory, clock=fake_clock, recheck_interval=60.0)
    original_check = checker._check  # type: ignore[attr-defined]

    async def counting_check() -> bool:
        nonlocal calls
        calls += 1
        return await original_check()

    checker._check = counting_check  # type: ignore[method-assign]

    assert await checker.ready() is True
    assert await checker.ready() is True  # same tick, must reuse the cached result
    assert calls == 1

    clock_value = 61.0
    assert await checker.ready() is True
    assert calls == 2


async def test_a_cancelled_check_does_not_lock_in_a_stale_cached_result() -> None:
    """Astra's second opinion: ``_last_checked_at`` and ``_ready`` must
    advance together. If the caller's own timeout (``/ready``'s 2s backstop
    in ``runtime.py``) cancels a slow check mid-flight, the *next* probe must
    retry immediately — not reuse a result from a check that never finished."""

    class _NeverFactory:
        def __call__(self) -> Any:
            raise AssertionError("must not be called before the check is cancelled")

    checker = PartitionReadiness(_NeverFactory())  # type: ignore[arg-type]

    async def hanging_check() -> bool:
        await asyncio.sleep(10)
        return True

    checker._check = hanging_check  # type: ignore[method-assign]
    checker._ready = False  # pyright: ignore[reportPrivateUsage]  # a previously observed problem

    task = asyncio.create_task(checker.ready())
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert checker._last_checked_at is None  # pyright: ignore[reportPrivateUsage]
    assert checker._ready is False  # pyright: ignore[reportPrivateUsage]


async def test_fails_open_when_the_database_is_unreachable() -> None:
    class _BrokenFactory:
        def __call__(self) -> Any:
            raise ConnectionError("db unreachable")

    checker = PartitionReadiness(_BrokenFactory())  # type: ignore[arg-type]

    assert await checker.ready() is True


async def _partition_events(factory: Any, marker: str) -> list[SystemEvent]:
    """``partition_missing`` events whose message names ``marker`` — the tests
    share one database, so counting must be scoped to the target date."""
    async with role_session(factory, db_role="hunter_worker") as session:
        rows = await session.scalars(
            select(SystemEvent)
            .where(SystemEvent.event == "partition_missing")
            .where(SystemEvent.message.contains(marker))
        )
        return list(rows)


async def test_a_missing_partition_for_now_is_fatal_at_startup(db_session_factory: Any) -> None:
    """The worker cannot persist anything in that period: starting is dishonest."""
    now = datetime(2027, 3, 15, 12, tzinfo=UTC)
    assert await _partition_events(db_session_factory, "2027-03-15") == []

    with pytest.raises(PartitionsMissing):
        await assert_writable_partitions(db_session_factory, now=lambda: now)

    events = await _partition_events(db_session_factory, "2027-03-15")
    assert len(events) == 1
    assert events[0].level.value == "critical"
    message = events[0].message
    assert message is not None and "candles_1m_2027_03" in message


async def test_present_partitions_for_now_start_silently(db_session_factory: Any) -> None:
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)

    await assert_writable_partitions(db_session_factory, now=lambda: now)

    assert await _partition_events(db_session_factory, "2026-11-15") == []


async def test_the_startup_assertion_fails_open_when_the_database_is_unreachable() -> None:
    """A Postgres blip has its own readiness signal (``check_database``); this
    check must not become a second way to wedge startup."""

    class _BrokenFactory:
        def __call__(self) -> Any:
            raise ConnectionError("db unreachable")

    await assert_writable_partitions(_BrokenFactory())  # type: ignore[arg-type]


async def test_a_missing_lookahead_partition_is_not_fatal_at_startup(
    db_session_factory: Any,
) -> None:
    """``main.py``'s startup sequence on 2026-12-31: today is writable, so the
    worker keeps collecting, but the lookahead is gone and ``/ready`` says so."""
    now = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)

    await assert_writable_partitions(db_session_factory, now=lambda: now)

    assert await PartitionReadiness(db_session_factory, now=lambda: now).ready() is False


async def test_a_hanging_startup_check_gives_up_instead_of_wedging_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra's second opinion: the startup gate runs before any collection task,
    so it needs a budget of its own — a Postgres holding the connection is a
    database error like any other, and must not delay today's ingestion."""

    class _HangingSession:
        async def __aenter__(self) -> Any:
            await asyncio.sleep(30)
            raise AssertionError("the check must have given up by now")

        async def __aexit__(self, *_: object) -> None:
            return None

    class _HangingFactory:
        def __call__(self) -> Any:
            return _HangingSession()

    monkeypatch.setattr(partitions, "CHECK_TIMEOUT_S", 0.05)

    async with asyncio.timeout(2.0):
        await assert_writable_partitions(_HangingFactory())  # type: ignore[arg-type]


async def test_a_hanging_system_event_still_leaves_a_missing_partition_fatal(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CRITICAL report is best-effort; giving up on it must not downgrade a
    confirmed absence into a normal start."""

    async def hanging_record(*_: object, **__: object) -> None:
        await asyncio.sleep(30)

    monkeypatch.setattr(partitions, "record_system_event", hanging_record)
    monkeypatch.setattr(partitions, "REPORT_TIMEOUT_S", 0.05)

    async with asyncio.timeout(2.0):
        with pytest.raises(PartitionsMissing):
            await assert_writable_partitions(
                db_session_factory, now=lambda: datetime(2027, 4, 1, tzinfo=UTC)
            )
