"""The durable history of cycle times — one ``system_events`` row per completed cycle.

``hb:meme:radar`` keeps only the ring of now (and a restart zeroes it); the §6.8
"before vs after" needs every individual cycle, with its generation (``run_id``)
and sequence (``seq``) so a hole is *declared* and never filled. The queue between
the loops and the writer is bounded and **never blocks a loop**: when it is full the
oldest sample is dropped and counted.

No database here; the real INSERT is proven in ``test_cycle_history_integration.py``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from structlog.testing import capture_logs

from hunter_meme_worker import cycle_history
from hunter_meme_worker.cycle_history import CycleHistory, CycleSample, flush_once
from hunter_meme_worker.cycle_metrics import CycleMeter, timed_step

from .test_cycle_metrics import _Clock  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _sample(seq: int, loop: str = "chain", ms: int = 100) -> CycleSample:
    return CycleSample(loop=loop, run_id="r1", seq=seq, ended_at=T0, duration_ms=ms)


class _Session:
    def __init__(self, db: _Db) -> None:
        self.db = db

    async def execute(self, statement: object, params: list[dict[str, Any]]) -> None:
        if self.db.fail:
            raise ConnectionError("db down")
        self.db.rows.extend(params)
        if self.db.lose_answer_once:  # the server applied it, the answer never arrived
            self.db.lose_answer_once = False
            raise ConnectionError("answer lost")


class _Db:
    """Stands in for ``role_session``: records the role and every inserted row."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.roles: list[str] = []
        self.fail = False
        self.hang = False
        self.lose_answer_once = False
        self.stubborn = False  # a peer that swallows the cancel (asyncpg's out-of-band cancel)
        self.release = asyncio.Event()

    @asynccontextmanager
    async def __call__(self, factory: object, *, db_role: str) -> AsyncGenerator[_Session]:
        self.roles.append(db_role)
        if self.hang:
            await asyncio.sleep(3600)
        while self.stubborn and not self.release.is_set():
            try:
                await asyncio.wait_for(self.release.wait(), timeout=3600)
            except asyncio.CancelledError:
                continue  # swallowed: only ``release`` frees it
        yield _Session(self)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> _Db:
    fake = _Db()
    monkeypatch.setattr(cycle_history, "role_session", fake)
    return fake


async def _no_publish(fields: dict[str, str]) -> None:
    return None


def _seqs(history: CycleHistory) -> list[object]:
    return [row.data["seq"] for _, row in history.peek(10_000)]


def test_the_queue_is_bounded_and_drops_the_oldest_counting_each() -> None:
    history = CycleHistory(capacity=3)
    for seq in range(1, 6):
        history.offer(_sample(seq))
    assert _seqs(history) == [3, 4, 5]
    assert history.dropped_total == 2
    assert history.fields()["cycle_history_dropped_total"] == "2"
    assert history.fields()["cycle_history_queued"] == "3"


def test_capacity_must_be_positive() -> None:
    with pytest.raises(ValueError, match="capacity"):
        CycleHistory(capacity=0)


async def test_a_flush_writes_one_row_per_cycle_as_the_worker_role(db: _Db) -> None:
    history = CycleHistory()
    history.offer(_sample(1, "chain", 61_000))
    history.offer(_sample(2, "lab", 15_500))
    assert await flush_once(history, object(), _no_publish) == 2  # type: ignore[arg-type]
    assert db.roles == ["hunter_worker"]
    first = db.rows[0]
    assert (first["component"], first["event"], first["level"]) == ("meme-worker", "cycle", "info")

    assert json.loads(first["data"]) == {
        "loop": "chain",
        "run_id": "r1",
        "seq": 1,
        "ended_at": "2026-10-07T12:00:00+00:00",
        "duration_ms": 61_000,
    }
    assert history.written_total == 2
    assert history.fields()["cycle_history_queued"] == "0"


async def test_an_empty_queue_costs_no_transaction(db: _Db) -> None:
    assert await flush_once(CycleHistory(), object(), _no_publish) == 0  # type: ignore[arg-type]
    assert db.roles == []


async def test_a_failed_write_keeps_the_rows_and_retries_them(db: _Db) -> None:
    history = CycleHistory()
    history.offer(_sample(1))
    db.fail = True
    with capture_logs() as logs:
        assert await flush_once(history, object(), _no_publish) == 0  # type: ignore[arg-type]
    assert any(e["event"] == "meme_cycle_history_write_failed" for e in logs)
    assert history.failed_total == 1
    assert history.written_total == 0
    db.fail = False
    assert await flush_once(history, object(), _no_publish) == 1  # type: ignore[arg-type]
    assert [r["data"] for r in db.rows].count(db.rows[0]["data"]) == 1  # written once


async def test_samples_offered_while_a_flush_is_in_flight_are_not_acknowledged(db: _Db) -> None:
    """Only what was in the batch is removed after the write, never the newer rows."""
    history = CycleHistory(capacity=10)
    history.offer(_sample(1))

    original = _Session.execute

    async def offer_during_write(self: _Session, statement: object, params: Any) -> None:
        history.offer(_sample(2))
        await original(self, statement, params)

    _Session.execute = offer_during_write  # type: ignore[method-assign]
    try:
        await flush_once(history, object(), _no_publish)  # type: ignore[arg-type]
    finally:
        _Session.execute = original  # type: ignore[method-assign]
    assert _seqs(history) == [2]


async def test_the_batch_is_capped(db: _Db) -> None:
    history = CycleHistory(capacity=50)
    for seq in range(1, 31):
        history.offer(_sample(seq))
    assert await flush_once(history, object(), _no_publish, batch=20) == 20  # type: ignore[arg-type]
    assert await flush_once(history, object(), _no_publish, batch=20) == 10  # type: ignore[arg-type]


async def test_a_hung_database_is_cut_at_the_flush_budget_and_the_rows_stay(db: _Db) -> None:
    history = CycleHistory()
    history.offer(_sample(1))
    db.hang = True
    assert (
        await asyncio.wait_for(
            flush_once(history, object(), _no_publish, budget_s=0.05),  # type: ignore[arg-type]
            timeout=2,
        )
        == 0
    )
    assert history.failed_total == 1
    assert _seqs(history) == [1]


async def test_a_cancel_during_the_write_propagates_and_is_not_a_failure(db: _Db) -> None:
    history = CycleHistory()
    history.offer(_sample(1))
    db.hang = True
    task = asyncio.create_task(flush_once(history, object(), _no_publish))  # type: ignore[arg-type]
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert history.failed_total == 0
    assert _seqs(history) == [1]


async def test_the_counters_reach_the_heartbeat_only_when_they_changed(db: _Db) -> None:
    history = CycleHistory()
    published: list[dict[str, str]] = []

    async def publish(fields: dict[str, str]) -> None:
        published.append(fields)

    await flush_once(history, object(), publish)  # type: ignore[arg-type]
    assert published == []  # nothing happened, nothing to say
    history.offer(_sample(1))
    await flush_once(history, object(), publish)  # type: ignore[arg-type]
    assert published[-1]["cycle_history_written_total"] == "1"
    await flush_once(history, object(), publish)  # type: ignore[arg-type]
    assert len(published) == 1


async def test_a_failing_counter_publication_does_not_fail_the_flush(db: _Db) -> None:
    history = CycleHistory()
    history.offer(_sample(1))

    async def publish(fields: dict[str, str]) -> None:
        raise ConnectionError("redis down")

    assert await flush_once(history, object(), publish) == 1  # type: ignore[arg-type]


async def test_every_completed_cycle_reaches_the_queue_with_its_sequence() -> None:
    """The hook ``timed_step`` calls: one sample per cycle, ``seq`` = ``cycles_total``."""
    meter, clock, history = CycleMeter("lab", nominal_s=15.0, window=3), _Clock(), CycleHistory()

    async def step(ctx: object) -> None:
        clock.advance(0.25)

    wrapped = timed_step(
        meter, step, _no_publish, clock=clock, now=lambda: T0, on_cycle=history.offer
    )
    for _ in range(3):
        await wrapped(object())
    rows = [row for _, row in history.peek(10)]
    assert {row.event for row in rows} == {"cycle"}
    assert [row.data["seq"] for row in rows] == [1, 2, 3]
    assert {row.data["loop"] for row in rows} == {"lab"}
    assert {row.data["run_id"] for row in rows} == {meter.run_id}
    assert {row.data["duration_ms"] for row in rows} == {250}
    assert rows[0].data["ended_at"] == T0.isoformat()


async def test_a_step_that_raises_leaves_no_sample() -> None:
    meter, history = CycleMeter("lab", nominal_s=15.0, window=3), CycleHistory()

    async def boom(ctx: object) -> None:
        raise RuntimeError("boom")

    wrapped = timed_step(meter, boom, _no_publish, on_cycle=history.offer)
    with pytest.raises(RuntimeError):
        await wrapped(object())
    assert history.peek(10) == []


async def test_a_broken_hook_never_stops_the_loop() -> None:
    meter = CycleMeter("lab", nominal_s=15.0, window=3)

    async def step(ctx: object) -> str:
        return "ok"

    def hook(sample: CycleSample) -> None:
        raise RuntimeError("hook")

    wrapped = timed_step(meter, step, _no_publish, on_cycle=hook)
    with capture_logs() as logs:
        assert await wrapped(object()) == "ok"
    assert any(e["event"] == "meme_cycle_history_offer_failed" for e in logs)
