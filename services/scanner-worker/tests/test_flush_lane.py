"""``FlushLane``: one owner for mutation -> persistence, and what it keeps on failure.

The properties Astra asked for on 05/10 (``obsidian/06-DECISIONS/Revisoes-Astra/
2026-10-05-scanner-parada-0210.md``): rows, event ids, ACKs and callbacks survive a
failed flush; the older batch stays ahead of the newer work; the two writers (cycle
and watchdog) never interleave; retention has a bound that fails loud; and a market
whose rows were dropped at flush time gets its memory back from the table.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from hunter_core.domain.types import utcnow
from hunter_scanner_worker import flush_lane, rehydrate, runners
from hunter_scanner_worker import repo as scanner_repo
from hunter_scanner_worker.cycle_health import CycleHealth
from hunter_scanner_worker.flush_lane import FlushLane
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import PendingAck

from .test_commit_alarm import loop_fixture

pytestmark = pytest.mark.unit

X, Y = UUID(int=0xA), UUID(int=0xB)


def _lane(cycle: CycleHealth | None = None, **kwargs: Any) -> FlushLane:
    return FlushLane(cast("Any", None), cast("Any", None), cycle or CycleHealth(), **kwargs)


def _stub_flush(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> list[WriteBatch]:
    """``flush_batch`` that records each batch and then returns/raises ``outcomes[i]``."""
    seen: list[WriteBatch] = []

    async def flush(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        seen.append(batch)
        outcome = outcomes[min(len(seen), len(outcomes)) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return set(outcome)

    monkeypatch.setattr(flush_lane, "flush_batch", flush)
    return seen


async def test_a_failed_flush_keeps_rows_events_acks_and_callbacks_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub_flush(monkeypatch, [RuntimeError("boom"), set()])
    lane = _lane()
    event = cast("Any", SimpleNamespace(event_id=UUID(int=7)))
    ack = PendingAck("market.candles.closed", "scanner", "1-0", str(UUID(int=7)))
    promoted: list[str] = []
    lane.batch.opportunities.append({"id": X, "market_id": UUID(int=1)})  # EXPIRE of X
    lane.batch.events.append(event)
    lane.batch.acks.append(ack)
    lane.batch.after_commit.append((UUID(int=1), lambda: promoted.append("x")))

    assert await lane.flush() is False
    lane.batch.opportunities.append({"id": Y, "market_id": UUID(int=1)})  # OPEN of Y, later

    assert await lane.flush() is True

    committed = seen[1]
    assert [row["id"] for row in committed.opportunities] == [X, Y], "older work stays ahead"
    assert committed.events == [event], "the retry carries the same event id"
    assert committed.acks == [ack]
    assert len(committed.after_commit) == 1
    assert lane.batch.empty and not lane.batch.acks, "a success starts from a fresh batch"


async def test_a_failure_is_recorded_once_per_attempt_and_a_commit_ends_the_streak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_flush(monkeypatch, [RuntimeError("one"), RuntimeError("two"), set()])
    cycle = CycleHealth()
    lane = _lane(cycle)
    lane.batch.snapshots.append({"market_id": UUID(int=1)})

    await lane.flush()
    await lane.flush()
    assert (cycle.failures, cycle.failures_total) == (2, 2)

    await lane.flush()
    assert (cycle.failures, cycle.failures_total) == (0, 2)
    assert cycle.last_commit_at is not None


async def test_retention_is_bounded_and_the_bound_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_flush(monkeypatch, [RuntimeError("poison"), RuntimeError("poison"), set()])
    cycle = CycleHealth()
    lane = _lane(cycle)
    lane.batch.opportunities.append({"id": X, "market_id": UUID(int=1)})
    lane.retained_since = utcnow() - timedelta(seconds=flush_lane.RETAIN_MAX_AGE_S + 1)

    with capture_logs() as logs:
        await lane.flush()
        await lane.flush()

    assert lane.blocked and cycle.blocked
    assert cycle.persistence_stalled() is True, "red at once, not after the 120 s streak"
    blocked = [entry for entry in logs if entry["event"] == "scanner_flush_blocked"]
    assert len(blocked) == 1, "one CRITICAL line, not one per retry"
    assert blocked[0]["log_level"] == "critical" and blocked[0]["opportunities"] == 1
    assert [row["id"] for row in lane.batch.opportunities] == [X], "nothing was dropped"

    assert await lane.flush() is True
    assert not lane.blocked and cycle.persistence_stalled() is False


async def test_a_blocked_lane_pauses_evaluation_instead_of_growing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_flush(monkeypatch, [RuntimeError("poison")])
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()
    cycle.blocked = True
    lane = FlushLane(cast("Any", None), redis, cycle)
    lane.batch.opportunities.append({"id": X, "market_id": UUID(int=1)})
    advanced: list[str] = []

    async def advance(self: Scanner, redis: Any, market: Any, batch: Any, *, now: Any) -> None:
        advanced.append(market.ref.symbol)

    monkeypatch.setattr(Scanner, "advance", advance)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle, lane),
            0.4,
        )

    assert advanced == [], "no new transition is collected on top of a batch that cannot commit"
    assert [row["id"] for row in lane.batch.opportunities] == [X]
    assert cycle.failures >= 1, "and the retry is still being made, and recorded"


async def test_the_watchdog_waits_for_the_cycle_and_shares_its_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner, redis, runtime = loop_fixture()
    scanner.config = replace(scanner.config, watchdog_s=0.05)
    lane = FlushLane(cast("Any", None), redis, CycleHealth())
    sweeps: list[WriteBatch] = []

    def sweep(scanner: Any, batch: WriteBatch, **kwargs: Any) -> None:
        sweeps.append(batch)

    monkeypatch.setattr(runners, "sweep_silent_markets", sweep)
    task = asyncio.create_task(
        runners.watchdog_loop(scanner, cast("Any", None), redis, runtime, lane)
    )
    try:
        async with lane.lock:  # the evaluation cycle is mid-flight
            await asyncio.sleep(0.25)
            assert sweeps == [], "the watchdog must not mutate memory during a cycle"
        await asyncio.sleep(0.25)
    finally:
        task.cancel()

    assert sweeps and all(batch is lane.batch for batch in sweeps)


async def test_a_failing_watchdog_flush_feeds_scanner_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_flush(monkeypatch, [RuntimeError("watchdog flush failed")])
    scanner, redis, runtime = loop_fixture()
    scanner.config = replace(scanner.config, watchdog_s=0.05)
    cycle = CycleHealth()
    lane = FlushLane(cast("Any", None), redis, cycle)

    def sweep(scanner: Any, batch: WriteBatch, **kwargs: Any) -> None:
        batch.anomalies.append({"id": X, "market_id": UUID(int=1)})

    monkeypatch.setattr(runners, "sweep_silent_markets", sweep)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.watchdog_loop(scanner, cast("Any", None), redis, runtime, lane),
            0.3,
        )

    assert cycle.failures >= 1 and cycle.failing_since is not None
    assert [row["id"] for row in lane.batch.anomalies][:1] == [X], "the sweep was kept, not lost"
    cycle.failing_since = datetime.now(UTC) - timedelta(minutes=3)
    assert cycle.persistence_stalled() is True


async def test_the_worker_hands_the_same_lane_to_both_writers() -> None:
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()

    tasks = runners.writer_tasks(scanner, cast("Any", None), redis, runtime, cycle)
    try:
        lanes = {name: cast("Any", task).cr_frame.f_locals["lane"] for name, task in tasks.items()}
    finally:
        for task in tasks.values():
            task.close()

    assert set(lanes) == {"evaluation", "watchdog"}
    assert lanes["evaluation"] is lanes["watchdog"]
    assert isinstance(lanes["evaluation"], FlushLane)


class RehydrateStub:
    """The table says: episode X is still open for every market asked about."""

    def __init__(self, fail_first: bool) -> None:
        self.fail_first = fail_first
        self.calls = 0
        self.failed_once = False
        self.reloaded = False
        """True once a reload has *succeeded* (what the loop may evaluate after)."""


def rehydrating_stub(monkeypatch: pytest.MonkeyPatch, fail_first: bool) -> RehydrateStub:
    stub = RehydrateStub(fail_first)

    class NoSession:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *exc: object) -> None:
            return None

    def session(factory: Any, db_role: str) -> NoSession:
        return NoSession()

    async def episodes(session: Any, ids: Any) -> dict[UUID, Any]:
        stub.calls += 1
        if stub.fail_first and stub.calls == 1:
            stub.failed_once = True
            raise ConnectionError("database restarting")
        stub.reloaded = True
        return {
            market_id: SimpleNamespace(episode="EPISODE-OF-X", opportunity_id=X, history_wire=None)
            for market_id in ids
        }

    async def anomalies(session: Any, ids: Any, *, since: Any) -> dict[UUID, Any]:
        return {}

    monkeypatch.setattr(rehydrate, "role_session", session)
    monkeypatch.setattr(scanner_repo, "load_open_episodes", episodes)
    monkeypatch.setattr(scanner_repo, "load_open_anomalies", anomalies)
    return stub


async def _run_cycles(monkeypatch: pytest.MonkeyPatch, seconds: float) -> tuple[Scanner, FlushLane]:
    """Cycle 1 collects the EXPIRE of X (memory forgets X); its flush drops the market."""
    scanner, redis, runtime = loop_fixture()
    cycle = CycleHealth()
    lane = FlushLane(cast("Any", None), redis, cycle)
    market = scanner.state.markets["SYM000USDT"]
    appended: list[int] = []

    async def advance(
        self: Scanner, redis: Any, market: Any, batch: WriteBatch, *, now: Any
    ) -> None:
        if not appended:
            appended.append(1)
            batch.opportunities.append({"id": X, "market_id": market.ref.market_id})
            market.opportunity_id = None
            market.episode = None

    monkeypatch.setattr(Scanner, "advance", advance)

    async def flush(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        # The baseline vanished under X's EXPIRE: flush_batch dropped the whole market.
        batch.opportunities.clear()
        return {market.ref.market_id}

    monkeypatch.setattr(flush_lane, "flush_batch", flush)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(scanner, cast("Any", None), redis, runtime, cycle, lane),
            seconds,
        )
    return scanner, lane


async def test_a_market_whose_expiry_was_dropped_gets_its_open_episode_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra, 05/10: after the invalidation there must be no free memory for Y while
    the table still holds X open -- the veto behind both production stops."""
    rehydrating_stub(monkeypatch, fail_first=False)

    scanner, lane = await _run_cycles(monkeypatch, 0.5)

    state = scanner.state.markets["SYM000USDT"]
    assert state.opportunity_id == X
    assert state.episode == "EPISODE-OF-X"
    assert lane.invalidated == set(), "resynced ids are released"


async def test_a_resync_that_fails_is_retried_instead_of_leaving_memory_ahead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = rehydrating_stub(monkeypatch, fail_first=True)

    scanner, lane = await _run_cycles(monkeypatch, 2.6)

    assert stub.calls >= 2, "the first reload hit the database restart and was retried"
    assert scanner.state.markets["SYM000USDT"].opportunity_id == X
    assert lane.invalidated == set()
