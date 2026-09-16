"""T4.43 — the tick wiring of the per-mint gate refusal trail: the write side
(cap, batched insert, the two heartbeat counters) and the once-a-day prune
gate, both against a fake repo — no database needed for the wiring itself
(``lab_repo_fast.py``'s own Postgres-backed tests already prove the SQL)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
from hunter_meme_worker.lab_trail import (
    RefusalTrailState,
    maybe_prune_trail,
    should_prune_trail_today,
    write_refusal_trail,
)

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 16, 16, 20, tzinfo=UTC)
RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000001"


class FakeSession:
    def __init__(self, log: list[Any]) -> None:
        self.log = log

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.log.append((str(statement)[:40], params))


def _rows(n: int) -> list[RefusalTrailRow]:
    return [
        RefusalTrailRow(as_of=AS_OF, rule_set_id=RULE_SET_ID, mint=f"mint{i}", refusal=None)
        for i in range(n)
    ]


# ---- write_refusal_trail ---------------------------------------------------


async def test_write_refusal_trail_is_a_no_op_on_an_empty_tick() -> None:
    log: list[Any] = []
    state = RefusalTrailState()
    inserted = await write_refusal_trail(FakeSession(log), state, [])  # type: ignore[arg-type]
    assert inserted == 0 and log == []
    assert (state.rows_total, state.capped_total) == (0, 0)


async def test_write_refusal_trail_counts_every_row_under_the_cap() -> None:
    log: list[Any] = []
    state = RefusalTrailState()
    inserted = await write_refusal_trail(FakeSession(log), state, _rows(5))  # type: ignore[arg-type]
    assert inserted == 5 and len(log) == 1, "one batched INSERT, not five"
    assert (state.rows_total, state.capped_total) == (5, 0)


async def test_write_refusal_trail_caps_and_counts_the_dropped_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", "3")
    log: list[Any] = []
    state = RefusalTrailState()
    inserted = await write_refusal_trail(FakeSession(log), state, _rows(5))  # type: ignore[arg-type]
    assert inserted == 3
    assert (state.rows_total, state.capped_total) == (3, 2), "2 of 5 dropped by the cap"


async def test_write_refusal_trail_accumulates_across_calls_since_boot() -> None:
    log: list[Any] = []
    state = RefusalTrailState()
    await write_refusal_trail(FakeSession(log), state, _rows(2))  # type: ignore[arg-type]
    await write_refusal_trail(FakeSession(log), state, _rows(3))  # type: ignore[arg-type]
    assert state.rows_total == 5, "since boot, not just the last tick"


# ---- should_prune_trail_today / maybe_prune_trail --------------------------


def test_should_prune_trail_today_is_true_the_first_time_a_day_is_seen() -> None:
    today = date(2026, 9, 16)
    assert should_prune_trail_today(None, today) is True
    assert should_prune_trail_today(date(2026, 9, 15), today) is True


def test_should_prune_trail_today_is_false_once_already_run() -> None:
    today = date(2026, 9, 16)
    assert should_prune_trail_today(today, today) is False


async def test_maybe_prune_trail_skips_the_database_within_the_same_day() -> None:
    today = date.today()  # noqa: DTZ011 - only compared to itself, no absolute meaning
    deleted, day = await maybe_prune_trail(object(), today, batch=500)  # type: ignore[arg-type]
    assert (deleted, day) == (0, today), "no session_factory call: it would crash if reached"
