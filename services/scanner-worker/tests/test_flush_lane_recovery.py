"""What Astra's 05/10 review of the lane still found, as tests.

Five ways the retained batch could recreate the divergence it exists to prevent:
a resync that ran too late, an invalidation forgotten with an empty batch, a regime
row id exposed before its commit, a stale watchdog touch applied over a newer
evaluation, and ACKs outrunning the evaluation they announce.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from hunter_scanner_worker import flush_lane, runners, writers
from hunter_scanner_worker import publish as projections
from hunter_scanner_worker.cycle_health import CycleHealth
from hunter_scanner_worker.flush_lane import FlushLane
from hunter_scanner_worker.persist import (
    WriteBatch,
    _drop_invalidated,  # pyright: ignore[reportPrivateUsage]
)
from hunter_scanner_worker.regime import RegimeEngine
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import PendingAck

from .policies import build_policy
from .test_commit_alarm import loop_fixture
from .test_flush_lane import X, rehydrating_stub

pytestmark = pytest.mark.unit

MARKET = UUID(int=1)


async def test_no_market_is_evaluated_before_a_failed_resync_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cycle 1 drops X's EXPIRE at flush; the reload then fails once. Evaluating in
    between would open Y beside the X the table still holds open -- and the flush
    that must carry the resync would be vetoed by the very index it protects."""
    state = rehydrating_stub(monkeypatch, fail_first=True)
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()
    lane = FlushLane(cast("Any", None), redis, cycle)
    market = scanner.state.markets["SYM000USDT"]
    evaluated_with_resync_done: list[bool] = []

    async def advance(
        self: Scanner, redis: Any, market: Any, batch: WriteBatch, *, now: Any
    ) -> None:
        evaluated_with_resync_done.append(state.reloaded)
        if len(evaluated_with_resync_done) == 1:
            batch.opportunities.append({"id": X, "market_id": market.ref.market_id})
            market.opportunity_id = None

    async def flush(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        batch.opportunities.clear()
        return {market.ref.market_id}

    monkeypatch.setattr(Scanner, "advance", advance)
    monkeypatch.setattr(flush_lane, "flush_batch", flush)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle, lane), 2.8
        )

    assert len(evaluated_with_resync_done) >= 2, "the premise: the loop evaluated again"
    assert evaluated_with_resync_done[1:] == [True] * (len(evaluated_with_resync_done) - 1)
    assert state.failed_once, "the premise: one reload failed"


async def test_an_invalidation_survives_a_failed_flush_that_left_the_batch_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    async def flush(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        attempts.append(1)
        batch.invalidated.add(MARKET)  # what _drop_invalidated does, before the transaction
        batch.opportunities.clear()
        raise ConnectionError("connection reset")

    monkeypatch.setattr(flush_lane, "flush_batch", flush)
    lane = FlushLane(cast("Any", None), cast("Any", None), CycleHealth())
    lane.batch.opportunities.append({"id": X, "market_id": MARKET})

    assert await lane.flush() is False
    assert await lane.flush() is True, "the batch is empty now: nothing left to commit"

    assert lane.invalidated == {MARKET}, "but the market still has to be reloaded"


def test_dropping_an_invalidated_evaluation_is_remembered_on_the_batch() -> None:
    batch = WriteBatch()
    baseline = UUID(int=9)
    batch.reference(MARKET, [baseline])
    batch.opportunities.append({"id": X, "market_id": MARKET})

    assert _drop_invalidated(batch, {baseline}) == {MARKET}

    assert batch.invalidated == {MARKET}
    assert batch.opportunities == []


async def test_acks_do_not_outrun_the_evaluation_while_the_lane_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refusing(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        raise ConnectionError("database down")

    monkeypatch.setattr(flush_lane, "flush_batch", refusing)
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()
    cycle.blocked = True
    lane = FlushLane(cast("Any", None), redis, cycle)
    lane.batch.opportunities.append({"id": X, "market_id": MARKET})
    ack = PendingAck("market.candles.closed", "scanner", "2-0", str(UUID(int=2)))
    scanner.state.hold_ack(ack)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle, lane), 0.4
        )

    assert lane.batch.acks == [], "a candle nobody evaluated must stay un-acked"
    assert list(scanner.state.pending_acks.values()) == [ack]


async def _regime_scanner() -> tuple[Scanner, Any, RegimeEngine]:
    scanner, redis, _runtime = loop_fixture()
    engine = RegimeEngine(thresholds=build_policy().regime)
    engine.seed([], until=datetime.now(UTC) - timedelta(days=1))
    scanner.regime = engine
    return scanner, redis, engine


async def test_a_regime_row_that_failed_to_commit_is_never_exposed_to_the_evaluations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An opportunity naming a regime the table never got is refused by its foreign
    key; with a retained batch that refusal would hold the whole lane."""

    async def refusing(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        raise ConnectionError("rolled back")

    monkeypatch.setattr(runners, "flush_batch", refusing)
    scanner, redis, engine = await _regime_scanner()
    assert scanner.regime_id is None

    with pytest.raises(ConnectionError):
        await runners.run_regime_once(scanner, cast("Any", None), redis)

    assert scanner.regime_id is None
    assert getattr(engine, "row_id", None) is None


async def test_a_committed_regime_row_becomes_the_id_the_evaluations_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flushed: list[WriteBatch] = []

    async def accepting(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        flushed.append(batch)
        return set()

    async def publish(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(runners, "flush_batch", accepting)
    monkeypatch.setattr(projections, "publish_regime_current", publish)
    scanner, redis, engine = await _regime_scanner()

    await runners.run_regime_once(scanner, cast("Any", None), redis)

    assert flushed and flushed[0].regime_open is not None
    assert scanner.regime_id == flushed[0].regime_open["id"]
    assert engine.row_id == scanner.regime_id


def test_a_touch_only_applies_to_a_row_that_is_not_newer() -> None:
    captured: list[Any] = []

    class Session:
        async def execute(self, statement: Any) -> None:
            captured.append(statement)

    when = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    row = {
        "id": X,
        "below_40_since": None,
        "status": "NORMAL",
        "expired_at": None,
        "last_updated_at": when,
    }
    asyncio.run(writers.touch_episodes(cast("Any", Session()), [row]))

    sql = str(captured[0].compile(dialect=postgresql.dialect()))
    assert "opportunities.last_updated_at <=" in sql, sql
