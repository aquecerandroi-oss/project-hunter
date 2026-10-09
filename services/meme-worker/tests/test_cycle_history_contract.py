"""Code-review round 2 of the cycle history: what makes the series usable as a guard.

- a generation leaves a birth certificate (``generation_start``, for **both** loops,
  enabled or not) and, on a clean shutdown, its final totals (``generation_end``): a
  tail lost in a crash is then *visible* as a generation without an end;
- one budget for a whole flush (database + counters), not one per step;
- shutdown drains the queue (not just one batch) inside its budget;
- a COMMIT applied whose confirmation was lost duplicates rows: the reader's
  identity ``(loop, run_id, seq)`` is what the contract promises.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

import pytest

from hunter_meme_worker.cycle_history import CycleHistory, CycleSample, drain, flush_once
from hunter_meme_worker.cycle_metrics import CycleMeter
from hunter_meme_worker.cycle_wiring import build_cycle_instruments

from .test_cycle_history import _Db, _no_publish  # pyright: ignore[reportPrivateUsage]
from .test_cycle_history import db as db

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _sample(seq: int) -> CycleSample:
    return CycleSample("chain", "r1", seq, T0, 100)


def test_the_birth_certificate_says_whether_the_loop_is_on_and_its_nominal_period() -> None:
    history = CycleHistory()
    on = CycleMeter("chain", nominal_s=60.0, window=120, started_at=T0)
    off = CycleMeter("lab", nominal_s=15.0, window=480, started_at=T0, enabled=False)
    history.mark_start(on)
    history.mark_start(off)
    first, second = (row for _, row in history.peek(10))
    assert first.event == second.event == "generation_start"
    assert first.data == {
        "loop": "chain",
        "run_id": on.run_id,
        "started_at": "2026-10-07T12:00:00+00:00",
        "enabled": True,
        "nominal_ms": 60_000,
        "window": 120,
    }
    assert second.data["enabled"] is False


def test_a_clean_shutdown_leaves_the_final_totals() -> None:
    history, meter = CycleHistory(), CycleMeter("chain", nominal_s=60.0, window=3, started_at=T0)
    meter.record(61_000, T0)
    meter.record(5, T0)
    history.mark_end(meter, T0, clean=True)
    history.mark_end(meter, T0, clean=False)
    (_, row), (_, crashed) = history.peek(10)
    assert row.event == "generation_end"
    assert row.data == {
        "loop": "chain",
        "run_id": meter.run_id,
        "ended_at": "2026-10-07T12:00:00+00:00",
        "cycles_total": 2,
        "overruns_total": 1,
        "clean": True,
    }
    assert crashed.data["clean"] is False  # a loop crashed: real totals, an unclean end


async def test_the_events_are_written_with_their_own_names(db: _Db) -> None:
    history = CycleHistory()
    meter = CycleMeter("chain", nominal_s=60.0, window=3, started_at=T0)
    history.mark_start(meter)
    history.offer(_sample(1))
    history.mark_end(meter, T0, clean=True)
    assert await flush_once(history, object(), _no_publish) == 3  # type: ignore[arg-type]
    assert [r["event"] for r in db.rows] == ["generation_start", "cycle", "generation_end"]
    assert {r["component"] for r in db.rows} == {"meme-worker"}


async def test_one_budget_covers_the_database_and_the_counters(db: _Db) -> None:
    """Database down for the whole budget: the counter publication gets nothing left."""
    history = CycleHistory()
    history.offer(_sample(1))
    db.hang = True
    published: list[dict[str, str]] = []

    async def slow_publish(fields: dict[str, str]) -> None:
        published.append(fields)
        await asyncio.sleep(3600)

    started = time.monotonic()
    written = await flush_once(
        history,
        object(),  # type: ignore[arg-type]
        slow_publish,
        budget_s=0.2,
    )
    assert written == 0
    assert time.monotonic() - started < 0.45  # 0.2 s in total, not 0.2 + 0.2
    assert published == []


async def test_a_slow_publication_cannot_outlive_what_the_database_left_of_the_budget(
    db: _Db,
) -> None:
    history = CycleHistory()
    history.offer(_sample(1))

    async def slow_publish(fields: dict[str, str]) -> None:
        await asyncio.sleep(3600)

    started = time.monotonic()
    assert await flush_once(history, object(), slow_publish, budget_s=0.2) == 1  # type: ignore[arg-type]
    assert time.monotonic() - started < 0.45


async def test_the_shutdown_drain_writes_every_batch_not_only_the_first(db: _Db) -> None:
    history = CycleHistory(capacity=2000)
    for seq in range(1, 1201):
        history.offer(_sample(seq))
    await drain(history, object(), _no_publish, budget_s=5.0)  # type: ignore[arg-type]
    assert history.queued == 0
    assert history.written_total == 1200


async def test_the_drain_stops_at_the_first_failed_write_and_at_its_budget(db: _Db) -> None:
    history = CycleHistory()
    for seq in range(1, 4):
        history.offer(_sample(seq))
    db.fail = True
    await drain(history, object(), _no_publish, budget_s=5.0)  # type: ignore[arg-type]
    assert history.failed_total == 1  # one try, no spinning on a dead database
    assert history.queued == 3
    db.fail = False
    db.hang = True
    started = time.monotonic()
    await drain(history, object(), _no_publish, budget_s=0.1)  # type: ignore[arg-type]
    assert time.monotonic() - started < 0.4


async def test_a_peer_that_swallows_the_cancel_cannot_hold_the_flush_past_its_budget(
    db: _Db,
) -> None:
    """``asyncio.timeout`` waits for the cancelled write to finish; a hung peer (asyncpg's
    out-of-band cancel has no deadline) would hold it for minutes. The write is therefore a
    task the flush *abandons* at the budget, counted, and no second write is started on top
    of one that is still stuck (one stuck connection, not one per tick)."""
    history = CycleHistory()
    history.offer(_sample(1))
    db.stubborn = True
    started = time.monotonic()
    assert await flush_once(history, object(), _no_publish, budget_s=0.1) == 0  # type: ignore[arg-type]
    assert time.monotonic() - started < 0.4
    assert (history.abandoned_total, history.failed_total, history.queued) == (1, 1, 1)
    assert history.fields()["cycle_history_abandoned_total"] == "1"

    assert await flush_once(history, object(), _no_publish, budget_s=0.1) == 0  # type: ignore[arg-type]
    assert db.roles == ["hunter_worker"]  # still the first, stuck checkout
    assert (history.abandoned_total, history.failed_total) == (1, 2)

    db.release.set()  # the peer answers at last: the abandoned write ends, the next flush works
    for _ in range(50):
        if not history.writing:
            break
        await asyncio.sleep(0.01)
    assert not history.writing
    db.stubborn = False
    assert await flush_once(history, object(), _no_publish) == 1  # type: ignore[arg-type]


async def test_the_shutdown_drain_is_bounded_even_when_the_peer_swallows_the_cancel(
    db: _Db,
) -> None:
    history = CycleHistory()
    history.offer(_sample(1))
    db.stubborn = True
    started = time.monotonic()
    await drain(history, object(), _no_publish, budget_s=0.2)  # type: ignore[arg-type]
    assert time.monotonic() - started < 0.5
    assert history.abandoned_total == 1
    db.release.set()


async def test_a_lost_commit_confirmation_duplicates_rows_and_identity_dedups_them(
    db: _Db,
) -> None:
    """The documented contract: the table may hold a cycle twice; ``(loop, run_id, seq)``
    is the identity the reader (``CYCLES_SINCE_SQL``) collapses before any percentile."""
    history = CycleHistory()
    history.offer(_sample(1))
    db.lose_answer_once = True
    assert await flush_once(history, object(), _no_publish) == 0  # type: ignore[arg-type]
    assert await flush_once(history, object(), _no_publish) == 1  # type: ignore[arg-type]
    identities = [(json.loads(r["data"])["loop"], json.loads(r["data"])["seq"]) for r in db.rows]
    assert len(identities) == 2  # physically twice ...
    assert len(set(identities)) == 1  # ... logically once


async def test_the_instruments_announce_birth_certificates_and_close_with_final_totals(
    db: _Db,
) -> None:
    from hunter_meme_worker.config import MemeConfig

    hash_: dict[str, str] = {}

    async def write(fields: dict[str, str]) -> None:
        hash_.update(fields)

    cycles = build_cycle_instruments(MemeConfig(enabled=False), object(), write)  # type: ignore[arg-type]
    await cycles.announce()
    # the counters are announced too, so a stale value of the previous process is replaced
    assert hash_["cycle_history_written_total"] == "0"
    await cycles.close(clean=True)
    events = [(r["event"], json.loads(r["data"])["loop"]) for r in db.rows]
    assert events == [
        ("generation_start", "chain"),
        ("generation_start", "lab"),
        ("generation_end", "chain"),
        ("generation_end", "lab"),
    ]
    assert json.loads(db.rows[0]["data"])["enabled"] is False
