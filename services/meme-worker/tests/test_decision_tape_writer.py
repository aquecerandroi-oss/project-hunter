"""T4.89 — the decision-tape writer (pure, no Docker): a bounded buffer the
event lane offers to without ever waiting, flushed in the background; under
pressure it drops and counts, and a failing database is logged and counted —
never raised into the gate."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

import hunter_meme_worker.decision_tape_writer as writer_module
from hunter_meme_worker.decision_tape import DecisionTape
from hunter_meme_worker.decision_tape_writer import DecisionTapeWriter, TapeRow

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 23, 20, 3, 18, tzinfo=UTC)


def _tape(i: int) -> DecisionTape:
    return DecisionTape(
        mint=f"MINT{i}",
        series="meme_event_gate_v1",
        as_of=AS_OF + timedelta(milliseconds=i),
        trades=(),
        trades_in_window=0,
        derived={"version": 1},
    )


@asynccontextmanager
async def _fake_role_session(_factory: Any, *, db_role: str) -> AsyncGenerator[object]:
    yield object()


def _sink(written: list[TapeRow]) -> Any:
    async def insert(_session: object, rows: list[TapeRow]) -> int:
        written.extend(rows)
        return len(rows)

    return insert


def test_offer_beyond_capacity_drops_and_counts_never_blocks() -> None:
    writer = DecisionTapeWriter(capacity=3, batch=2)
    accepted = [writer.offer(_tape(i), proposal_ids=()) for i in range(5)]
    assert accepted == [True, True, True, False, False]
    assert writer.pending == 3
    assert (writer.offered, writer.dropped) == (5, 2)


async def test_flush_writes_in_bounded_batches_in_offer_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[TapeRow] = []
    monkeypatch.setattr(writer_module, "role_session", _fake_role_session)
    monkeypatch.setattr(writer_module, "insert_decision_tapes", _sink(written))
    writer = DecisionTapeWriter(capacity=10, batch=2)
    for i in range(3):
        writer.offer(_tape(i), proposal_ids=(f"p{i}",) if i == 1 else ())
    assert await writer.flush(None) == 2  # type: ignore[arg-type]
    assert await writer.flush(None) == 1  # type: ignore[arg-type]
    assert [row.tape.mint for row in written] == ["MINT0", "MINT1", "MINT2"]
    assert written[1].proposal_ids == ("p1",)
    assert writer.written == 3 and writer.pending == 0


async def test_a_failing_database_is_counted_and_logged_never_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(_session: object, _rows: list[TapeRow]) -> int:
        raise RuntimeError("statement timeout")

    monkeypatch.setattr(writer_module, "role_session", _fake_role_session)
    monkeypatch.setattr(writer_module, "insert_decision_tapes", boom)
    writer = DecisionTapeWriter(capacity=10, batch=5)
    for i in range(3):
        writer.offer(_tape(i), proposal_ids=())
    with capture_logs() as logs:
        assert await writer.flush(None) == 0  # type: ignore[arg-type]
    assert writer.failed == 3 and writer.pending == 0
    failures = [line for line in logs if line["event"] == "meme_decision_tape_write_failed"]
    assert failures and failures[0]["error_type"] == "RuntimeError" and failures[0]["rows"] == 3


async def test_drops_since_the_last_flush_are_logged_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(writer_module, "role_session", _fake_role_session)
    monkeypatch.setattr(writer_module, "insert_decision_tapes", _sink([]))
    writer = DecisionTapeWriter(capacity=1, batch=5)
    for i in range(4):
        writer.offer(_tape(i), proposal_ids=())
    with capture_logs() as logs:
        await writer.flush(None)  # type: ignore[arg-type]
        await writer.flush(None)  # type: ignore[arg-type]
    drops = [line for line in logs if line["event"] == "meme_decision_tape_dropped"]
    assert len(drops) == 1 and drops[0]["dropped"] == 3


def test_the_heartbeat_names_every_counter() -> None:
    writer = DecisionTapeWriter(capacity=1, batch=1)
    writer.offer(_tape(0), proposal_ids=())
    writer.offer(_tape(1), proposal_ids=())
    writer.record_capture_failed()
    fields = writer.heartbeat_fields()
    assert fields == {
        "event_gate_tapes_offered": "2",
        "event_gate_tapes_written": "0",
        "event_gate_tapes_dropped": "1",
        "event_gate_tapes_failed": "0",
        "event_gate_tapes_capture_failed": "1",
        "event_gate_tapes_pending": "1",
        "event_gate_tapes_pruned": "0",
        "event_gate_tapes_prune_failed": "0",
        "event_gate_tapes_last_prune_ok_at": "",
        "event_gate_tapes_unlinked": "0",
    }


def test_prune_runs_once_per_utc_day() -> None:
    writer = DecisionTapeWriter()
    day = datetime(2026, 9, 23, 23, 59, tzinfo=UTC)
    assert writer.prune_due(day) is True
    writer.last_prune_day = day.date()
    assert writer.prune_due(day + timedelta(minutes=0.5)) is False
    assert writer.prune_due(day + timedelta(minutes=2)) is True


async def test_a_failing_prune_is_logged_once_and_waits_for_the_next_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database outage must not turn the 2-second flush loop into a log
    flood: the sweep is retried the next UTC day, never every cycle."""

    async def boom(_session: object, *, now: datetime, batch: int) -> int:
        raise RuntimeError("statement timeout")

    monkeypatch.setattr(writer_module, "role_session", _fake_role_session)
    monkeypatch.setattr(writer_module, "prune_decision_tapes", boom)
    writer = DecisionTapeWriter()
    with capture_logs() as logs:
        assert await writer.maybe_prune(None, AS_OF) == 0  # type: ignore[arg-type]
        assert await writer.maybe_prune(None, AS_OF + timedelta(seconds=2)) == 0  # type: ignore[arg-type]
    assert writer.last_prune_day == AS_OF.date()
    assert [line["event"] for line in logs] == ["meme_decision_tape_prune_failed"]


async def test_a_failed_prune_is_counted_and_a_good_one_stamps_its_instant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[datetime] = []

    async def flaky(_session: object, *, now: datetime, batch: int) -> int:
        calls.append(now)
        if len(calls) == 1:
            raise RuntimeError("statement timeout")
        return 3

    monkeypatch.setattr(writer_module, "role_session", _fake_role_session)
    monkeypatch.setattr(writer_module, "prune_decision_tapes", flaky)
    writer = DecisionTapeWriter()
    await writer.maybe_prune(None, AS_OF)  # type: ignore[arg-type]
    fields = writer.heartbeat_fields()
    assert fields["event_gate_tapes_prune_failed"] == "1"
    assert fields["event_gate_tapes_last_prune_ok_at"] == ""
    next_day = AS_OF + timedelta(days=1)
    assert await writer.maybe_prune(None, next_day) == 3  # type: ignore[arg-type]
    assert writer.heartbeat_fields()["event_gate_tapes_last_prune_ok_at"] == next_day.isoformat()


def test_an_unlinked_tape_is_counted() -> None:
    writer = DecisionTapeWriter()
    writer.record_unlinked()
    assert writer.heartbeat_fields()["event_gate_tapes_unlinked"] == "1"
