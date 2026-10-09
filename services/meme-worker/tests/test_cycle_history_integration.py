"""The cycle history against a real Postgres (migrated, roles as in production).

Proves what the unit tests cannot: that ``hunter_worker`` may ``INSERT`` into the
partitioned, append-only ``system_events`` with ``event_severity`` cast and a JSONB
payload (no migration needed), that neither role can rewrite it, and that the
reader's query (``CYCLES_SINCE_SQL``) windows by ``ended_at`` and collapses a cycle
persisted twice to one.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.cycle_history import (
    CYCLES_SINCE_SQL,
    CycleHistory,
    CycleSample,
    flush_once,
)
from hunter_meme_worker.cycle_metrics import CycleMeter, timed_step

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

_RAW = text(
    "SELECT event, level::text AS level, component, data FROM system_events "
    "WHERE component = 'meme-worker' AND data->>'run_id' = :run_id"
)


async def _no_publish(fields: dict[str, str]) -> None:
    return None


async def _guard(
    factory: async_sessionmaker[AsyncSession], since: datetime, until: datetime, run_id: str
) -> list[tuple[str, int, int]]:
    async with role_session(factory, db_role="hunter_worker") as session:
        rows = (
            (await session.execute(text(CYCLES_SINCE_SQL), {"since": since, "until": until}))
            .mappings()
            .all()
        )
    return [(r["loop"], r["seq"], r["duration_ms"]) for r in rows if r["run_id"] == run_id]


async def test_the_events_land_with_their_payload_as_the_worker_role(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    history = CycleHistory()
    chain = CycleMeter("chain", nominal_s=60.0, window=3, enabled=False)
    history.mark_start(chain)
    history.offer(CycleSample("chain", chain.run_id, 1, chain.started_at, 61_000))
    history.mark_end(chain, chain.started_at, clean=True)
    assert await flush_once(history, db_session_factory, _no_publish) == 3
    assert history.queued == 0

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = (await session.execute(_RAW, {"run_id": chain.run_id})).mappings().all()
    # one batch = one transaction = one ``created_at``: the order *inside* it is not the
    # order of the cycles, so a reader orders by ``seq``/``ended_at``, never by ``created_at``.
    by_event = {r["event"]: r for r in rows}
    assert sorted(by_event) == ["cycle", "generation_end", "generation_start"]
    assert {r["level"] for r in rows} == {"info"}
    assert by_event["generation_start"]["data"]["enabled"] is False
    assert by_event["generation_start"]["data"]["nominal_ms"] == 60_000
    assert by_event["cycle"]["data"]["duration_ms"] == 61_000
    assert by_event["generation_end"]["data"]["cycles_total"] == 0
    assert by_event["generation_end"]["data"]["clean"] is True


async def test_the_reader_windows_by_ended_at_and_collapses_a_duplicated_cycle(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    run_id = f"it-dedup-{now.timestamp()}"
    history = CycleHistory()
    for seq, ms in ((1, 61_000), (2, 59_000), (3, 4_000)):
        history.offer(CycleSample("chain", run_id, seq, now - timedelta(minutes=10), ms))
    history.offer(CycleSample("chain", run_id, 2, now - timedelta(minutes=10), 59_000))  # lost ack
    history.offer(CycleSample("chain", run_id, 9, now - timedelta(hours=3), 1))  # before the window
    assert await flush_once(history, db_session_factory, _no_publish) == 5

    window = (now - timedelta(hours=1), now + timedelta(hours=1))
    assert await _guard(db_session_factory, *window, run_id) == [
        ("chain", 1, 61_000),
        ("chain", 2, 59_000),  # once, though persisted twice
        ("chain", 3, 4_000),
    ]


async def test_the_reader_prunes_partitions_on_both_sides_of_created_at(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A row persisted more than a day after the window closed is outside the reader's
    ``created_at`` range (upper bound, DB review nit 6) although its ``ended_at`` is
    inside the window; the same row is read by a window that persistence did not outrun."""
    now = datetime.now(UTC)
    run_id = f"it-late-{now.timestamp()}"
    history = CycleHistory()
    history.offer(CycleSample("chain", run_id, 1, now - timedelta(days=3), 7_000))
    assert await flush_once(history, db_session_factory, _no_publish) == 1

    inside = (now - timedelta(days=4), now - timedelta(days=2))  # persisted 2 days after
    assert await _guard(db_session_factory, *inside, run_id) == []
    reachable = (now - timedelta(days=4), now - timedelta(hours=12))  # within 1 day of it
    assert await _guard(db_session_factory, *reachable, run_id) == [("chain", 1, 7_000)]


async def test_timed_steps_feed_the_real_table_end_to_end(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    meter, history = CycleMeter("lab", nominal_s=15.0, window=3), CycleHistory()

    async def step(ctx: object) -> None:
        await asyncio.sleep(0.05)

    wrapped = timed_step(meter, step, _no_publish, on_cycle=history.offer)
    for _ in range(3):
        await wrapped(object())
    assert await flush_once(history, db_session_factory, _no_publish) == 3
    now = datetime.now(UTC)
    rows = await _guard(
        db_session_factory, now - timedelta(minutes=5), now + timedelta(minutes=5), meter.run_id
    )
    assert [seq for _, seq, _ in rows] == [1, 2, 3]
    assert all(ms >= 20 for _, _, ms in rows)  # a real duration (Windows timers are coarse)


@pytest.mark.parametrize("role", ["hunter_worker", "hunter_app"])
@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM system_events WHERE data->>'run_id' = 'it-append-only'",
        "UPDATE system_events SET data = '{}' WHERE data->>'run_id' = 'it-append-only'",
    ],
)
async def test_neither_role_can_rewrite_the_history(
    db_session_factory: async_sessionmaker[AsyncSession], role: str, statement: str
) -> None:
    """Append-only: neither role may UPDATE or DELETE ``system_events`` (DATABASE.md §1.2)."""
    history = CycleHistory()
    history.offer(CycleSample("chain", "it-append-only", 1, datetime.now(UTC), 10))
    assert await flush_once(history, db_session_factory, _no_publish) == 1
    with pytest.raises(Exception, match="permission denied"):
        async with role_session(db_session_factory, db_role=role) as session:
            await session.execute(text(statement))
