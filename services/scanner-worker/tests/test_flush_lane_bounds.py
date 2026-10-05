"""What keeps a retained batch from growing without bound.

Code review of the lane, 05/10: while the lane is blocked or failing, the Redis
pending list grows, ``consume._read_loop`` reclaims the consumer's own idle entries,
and ``handle`` used to append **another** ``PendingAck`` for every redelivery -- the
~88x amplification measured on 01/10, now living in memory. The book of pending ACKs
is therefore keyed by ``(stream, group, message_id)`` and cannot outgrow the Redis
list it mirrors. The other two bounds: an evaluation that keeps raising counts toward
the retention limit, and an empty lane is the end of a failure, not a state to stay in.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from hunter_core.domain.types import utcnow
from hunter_scanner_worker import flush_lane, runners
from hunter_scanner_worker.cycle_health import CycleHealth
from hunter_scanner_worker.flush_lane import FlushLane
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import PendingAck, ScannerState

from .test_commit_alarm import loop_fixture

pytestmark = pytest.mark.unit

STREAM, GROUP = "market.candles.closed", "scanner-worker.market.candles.closed"


def _ack(message_id: str, event: int = 1) -> PendingAck:
    return PendingAck(STREAM, GROUP, message_id, str(UUID(int=event)))


def test_fifty_redeliveries_of_one_message_hold_one_ack() -> None:
    state = ScannerState()

    for _ in range(50):
        state.hold_ack(_ack("1-0"))
    state.hold_ack(_ack("1-1", event=2))

    assert len(state.pending_acks) == 2
    taken = state.take_acks()
    assert sorted(ack.message_id for ack in taken) == ["1-0", "1-1"]
    assert state.pending_acks == {}, "taking the book empties it"


def test_a_batch_never_holds_the_same_message_twice() -> None:
    batch = WriteBatch()
    batch.add_acks([_ack("1-0"), _ack("1-1", event=2)])

    batch.add_acks([_ack("1-0"), _ack("1-2", event=3), _ack("1-2", event=3)])

    assert [ack.message_id for ack in batch.acks] == ["1-0", "1-1", "1-2"]


async def test_redeliveries_while_the_flush_keeps_failing_do_not_grow_the_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refusing(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        raise ConnectionError("database down")

    monkeypatch.setattr(flush_lane, "flush_batch", refusing)
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()
    lane = FlushLane(cast("Any", None), redis, cycle)

    async def advance(
        self: Scanner, redis: Any, market: Any, batch: WriteBatch, *, now: Any
    ) -> None:
        # What the reclaim does while the batch is retained: the same message, again.
        scanner.state.hold_ack(_ack("1-0"))
        batch.opportunities.append({"id": UUID(int=0xA), "market_id": market.ref.market_id})

    monkeypatch.setattr(Scanner, "advance", advance)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle, lane), 2.8
        )

    assert cycle.failures >= 2, "the premise: several redeliveries against a failing flush"
    assert len(lane.batch.acks) == 1
    assert len(scanner.state.pending_acks) <= 1


async def test_an_evaluation_that_keeps_raising_counts_toward_the_retention_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flush is never reached, so only the evaluation's own failures can block."""
    flushed: list[WriteBatch] = []

    async def flush(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        flushed.append(batch)
        return set()

    monkeypatch.setattr(flush_lane, "flush_batch", flush)
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()
    lane = FlushLane(cast("Any", None), redis, cycle)
    lane.retained_since = utcnow() - timedelta(seconds=flush_lane.RETAIN_MAX_AGE_S + 1)
    attempts: list[int] = []

    async def advance(
        self: Scanner, redis: Any, market: Any, batch: WriteBatch, *, now: Any
    ) -> None:
        attempts.append(1)
        batch.opportunities.append({"id": UUID(int=0xA), "market_id": market.ref.market_id})
        raise TimeoutError("Timeout reading from redis:6379")

    monkeypatch.setattr(Scanner, "advance", advance)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle, lane), 0.5
        )

    assert attempts, "the premise: the evaluation ran and raised"
    assert cycle.blocked, "an evaluation failing for a minute is bounded like a flush"
    assert cycle.persistence_stalled() is True
    assert lane.batch.opportunities, "and what it collected is still there, not dropped"


async def test_an_empty_lane_ends_the_failure_it_was_blocked_by() -> None:
    cycle = CycleHealth()
    cycle.failed(RuntimeError("an evaluation that failed with nothing collected"))
    cycle.blocked = True
    lane = FlushLane(cast("Any", None), cast("Any", None), cycle)
    lane.retained_since = utcnow() - timedelta(minutes=5)

    assert await lane.flush() is True

    assert not cycle.blocked
    assert cycle.failing_since is None and cycle.failures == 0
    assert lane.retained_since is None
    assert cycle.persistence_stalled() is False


async def test_a_checkpoint_failure_after_a_good_flush_is_not_a_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkpoints are an ephemeral Redis projection written *after* the commit. A
    pass that raises must neither start the failure streak nor make ``/ready`` blink
    red with an empty lane; it is logged and counted on its own."""

    async def flush(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        return set()

    async def broken(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("redis refused the checkpoint pass")

    monkeypatch.setattr(flush_lane, "flush_batch", flush)
    monkeypatch.setattr(runners, "_save_checkpoints", broken)
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()
    lane = FlushLane(cast("Any", None), redis, cycle)

    async def advance(
        self: Scanner, redis: Any, market: Any, batch: WriteBatch, *, now: Any
    ) -> None:
        batch.opportunities.append({"id": UUID(int=0xA), "market_id": market.ref.market_id})

    monkeypatch.setattr(Scanner, "advance", advance)
    with capture_logs() as logs, pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle, lane), 0.6
        )

    assert cycle.last_commit_at is not None, "the premise: the flush committed"
    assert cycle.checkpoint_failures_total >= 1
    assert cycle.failures == 0 and cycle.failing_since is None
    assert cycle.persistence_stalled() is False
    assert any(entry["event"] == "scanner_checkpoint_pass_failed" for entry in logs)
