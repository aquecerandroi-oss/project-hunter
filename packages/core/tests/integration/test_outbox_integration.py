"""The T2.9 failure-injection matrix, against a real Postgres and a real Redis.

Every test here kills the producer or the consumer at one specific instant and
asserts what the outbox promises for it: nothing published without the business
row, nothing lost between the commit and the ``XADD``, at-least-once delivery
with a once-only *effect* after the ``XADD``, a redelivery before the ACK that
is a no-op, and a stream trimmed out from under its consumers that
reconciliation can refill.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from structlog.testing import capture_logs

from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import create_session_factory, role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.domain.types import utcnow
from hunter_core.events.consume import ack, consume
from hunter_core.events.outbox import (
    MICRO_BATCH,
    UNPUBLISHABLE_ATTEMPTS,
    OutboxHealth,
    dispatch_pending,
    prune_dispatched,
    reconcile,
    refresh_health,
)
from hunter_core.events.outbox_event import event_id_for
from hunter_core.events.outbox_store import PRUNE_BATCH, enqueue, prunable_ids
from hunter_core.events.produce import ensure_group
from hunter_core.redis import keys

from .conftest import alembic_config, async_engine, create_database

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

STREAM = "market.candles.closed"
PRODUCER = "market-worker@test"

_EFFECT_DDL = """
CREATE TABLE IF NOT EXISTS t29_effect (
    event_id uuid PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


@pytest.fixture(scope="session")
def outbox_db(container_url: str) -> Iterator[str]:
    """A migrated database of this module's own, so a schema test's
    ``downgrade base`` elsewhere can never pull ``outbox_events`` away."""
    url = asyncio.run(create_database(container_url, "hunter_outbox"))
    command.upgrade(alembic_config(url), "head")
    yield url


@pytest_asyncio.fixture
async def outbox_engine(outbox_db: str) -> AsyncIterator[AsyncEngine]:
    engine = async_engine(outbox_db)
    async with engine.begin() as connection:
        await connection.execute(text(_EFFECT_DDL))
        await connection.execute(text("GRANT ALL ON TABLE t29_effect TO hunter_worker, hunter_app"))
        await connection.execute(text("TRUNCATE outbox_events, t29_effect"))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def factory(outbox_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(outbox_engine)


@pytest_asyncio.fixture
async def channel(redis_client: redis_asyncio.Redis) -> AsyncIterator[tuple[str, str]]:
    """A stream **and consumer group** of this test's own.

    The group has to be unique too: ``event_id`` is deterministic, so two tests
    queueing "the same candle" share one identity, and a shared
    ``hunter:processed:{group}`` set would let one test's ACK make the next
    test's message vanish as an already-handled redelivery.
    """
    suffix = uuid.uuid4().hex
    name, group = f"{STREAM}.{suffix}", f"t29.{suffix}"
    await ensure_group(redis_client, name, group)
    yield name, group
    await redis_client.delete(
        name, *(keys.processed(group, (utcnow() - timedelta(days=d)).date()) for d in (0, 1))
    )


def _candle_event(symbol: str, minute: int) -> tuple[uuid.UUID, dict[str, Any]]:
    open_time = utcnow().replace(second=0, microsecond=0) + timedelta(minutes=minute)
    event_id = event_id_for(STREAM, "binance", symbol, "1m", open_time)
    return event_id, {"exchange": "binance", "symbol": symbol, "open_time": open_time.isoformat()}


async def _queue(
    factory: async_sessionmaker[AsyncSession], stream: str, symbol: str, minute: int = 0
) -> uuid.UUID:
    event_id, payload = _candle_event(symbol, minute)
    async with role_session(factory, db_role="hunter_worker") as session:
        await enqueue(
            session, stream, event_id, payload, producer=PRODUCER, key=f"binance:{symbol}"
        )
    return event_id


async def _entries(redis: redis_asyncio.Redis, stream: str) -> list[Any]:
    return list(await redis.xrange(stream) or [])


async def _pending(factory: async_sessionmaker[AsyncSession]) -> int:
    return (await refresh_health(factory, OutboxHealth())).pending


# --- injected failure 1: the producer dies before the commit ----------------


async def test_a_rollback_leaves_neither_the_business_row_nor_the_event(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    stream, _group = channel
    event_id, payload = _candle_event("BTCUSDT", 0)
    with pytest.raises(RuntimeError, match="crash before commit"):
        async with role_session(factory, db_role="hunter_worker") as session:
            session.add(
                SystemEvent(
                    level=RiskEventSeverity.INFO,
                    component="test",
                    event="t29_business_row",
                    message=str(event_id),
                )
            )
            await enqueue(
                session, stream, event_id, payload, producer=PRODUCER, key="binance:BTCUSDT"
            )
            await session.flush()
            raise RuntimeError("crash before commit")

    async with role_session(factory, db_role="hunter_worker") as session:
        rows = await session.execute(
            text("SELECT count(*) FROM system_events WHERE message = :m"), {"m": str(event_id)}
        )
        assert rows.scalar() == 0
    assert await _pending(factory) == 0
    assert await dispatch_pending(redis_client, factory) == 0
    assert await _entries(redis_client, stream) == []


# --- injected failure 2: dead between the commit and the XADD ---------------


async def test_reconcile_publishes_a_row_committed_but_never_dispatched(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    stream, _group = channel
    event_id = await _queue(factory, stream, "BTCUSDT")
    assert await _entries(redis_client, stream) == []  # the producer died here
    assert await _pending(factory) == 1

    assert await reconcile(redis_client, factory) == 1

    entries = await _entries(redis_client, stream)
    assert len(entries) == 1
    assert str(event_id) in str(entries[0][1])
    assert await _pending(factory) == 0
    # a second reconciliation is a no-op, not a second publication
    assert await reconcile(redis_client, factory) == 0
    assert len(await _entries(redis_client, stream)) == 1


# --- injected failure 3: dead after the XADD, before the mark ---------------


async def test_a_crash_before_the_mark_republishes_but_is_consumed_once(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delivery is at-least-once (Redis 7 has no idempotent ``XADD``); the
    *effect* is once, because the envelope is byte-identical and ``consume()``
    filters an already-processed ``event_id``."""
    stream, group = channel
    await _queue(factory, stream, "BTCUSDT")

    async def die_before_marking(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("crash after XADD, before dispatched_at")

    monkeypatch.setattr("hunter_core.events.outbox.mark_dispatched", die_before_marking)
    with pytest.raises(RuntimeError, match="before dispatched_at"):
        await dispatch_pending(redis_client, factory)
    monkeypatch.undo()

    assert len(await _entries(redis_client, stream)) == 1
    assert await _pending(factory) == 1  # the mark never landed

    assert await dispatch_pending(redis_client, factory) == 1
    entries = await _entries(redis_client, stream)
    assert len(entries) == 2, "the same event is physically on the stream twice"
    assert entries[0][1] == entries[1][1], "byte-for-byte the same envelope"

    delivered: list[uuid.UUID] = []
    gen = consume(redis_client, stream, group, "c1", block_ms=200)
    message_id, envelope = await asyncio.wait_for(gen.__anext__(), timeout=10)
    delivered.append(envelope.event_id)
    await ack(redis_client, stream, group, message_id, envelope)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(gen.__anext__(), timeout=2)
    await gen.aclose()
    assert len(delivered) == 1, "the duplicate is filtered by the event_id guard"


# --- injected failure 4: the consumer dies after the effect, before the ACK -


async def test_a_redelivery_before_the_ack_leaves_the_effect_applied_once(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    stream, group = channel
    await _queue(factory, stream, "BTCUSDT")
    await dispatch_pending(redis_client, factory)

    async def apply_effect(event_id: uuid.UUID) -> None:
        async with role_session(factory, db_role="hunter_worker") as session:
            await session.execute(
                text("INSERT INTO t29_effect (event_id) VALUES (:id) ON CONFLICT DO NOTHING"),
                {"id": str(event_id)},
            )

    gen = consume(redis_client, stream, group, "c1", block_ms=200, claim_idle_ms=0)
    _message_id, envelope = await asyncio.wait_for(gen.__anext__(), timeout=10)
    await apply_effect(envelope.event_id)
    await gen.aclose()  # died here: the effect is durable, the message unacked

    gen = consume(redis_client, stream, group, "c2", block_ms=200, claim_idle_ms=0)
    message_id, redelivered = await asyncio.wait_for(gen.__anext__(), timeout=10)
    assert redelivered.event_id == envelope.event_id
    await apply_effect(redelivered.event_id)
    await ack(redis_client, stream, group, message_id, redelivered)
    await gen.aclose()

    async with role_session(factory, db_role="hunter_worker") as session:
        count = await session.execute(text("SELECT count(*) FROM t29_effect"))
        assert count.scalar() == 1
    pending = await redis_client.xpending(stream, group)
    assert pending["pending"] == 0


# --- injected failure 5: the stream itself is lost --------------------------


async def test_reconcile_since_refills_a_trimmed_stream(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    stream, _group = channel
    since = utcnow() - timedelta(minutes=1)
    for minute in range(3):
        await _queue(factory, stream, "BTCUSDT", minute)
    assert await dispatch_pending(redis_client, factory) == 3
    assert len(await _entries(redis_client, stream)) == 3

    await redis_client.xtrim(stream, maxlen=0, approximate=False)
    assert await _entries(redis_client, stream) == []
    # the rows are marked dispatched, so the pending predicate cannot help
    assert await reconcile(redis_client, factory) == 0
    assert await _entries(redis_client, stream) == []

    assert await reconcile(redis_client, factory, since=since) == 3
    assert len(await _entries(redis_client, stream)) == 3


# --- N dispatchers (one per shard) ------------------------------------------


async def test_two_dispatchers_never_publish_the_same_row_twice(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    """``FOR UPDATE ... SKIP LOCKED``: each sweep takes a disjoint slice, so
    the market-worker's shards need no leader election."""
    stream, _group = channel
    for minute in range(20):
        await _queue(factory, stream, "BTCUSDT", minute)

    sent = await asyncio.gather(
        dispatch_pending(redis_client, factory, micro_batch=5),
        dispatch_pending(redis_client, factory, micro_batch=5),
    )
    assert sum(sent) == 20
    assert len(await _entries(redis_client, stream)) == 20
    assert await _pending(factory) == 0


async def test_a_redis_outage_leaves_the_row_pending_with_its_error(
    factory: async_sessionmaker[AsyncSession],
    channel: tuple[str, str],
) -> None:
    class DeadRedis:
        async def xadd(self, *_args: Any, **_kwargs: Any) -> None:
            raise ConnectionError("redis is down")

    stream, _group = channel
    await _queue(factory, stream, "BTCUSDT")
    assert await dispatch_pending(DeadRedis(), factory) == 0  # type: ignore[arg-type]

    async with role_session(factory, db_role="hunter_worker") as session:
        row = (
            await session.execute(
                text("SELECT attempts, last_error, dispatched_at FROM outbox_events")
            )
        ).one()
    assert row.attempts == 1
    assert "redis is down" in row.last_error
    assert row.dispatched_at is None


async def test_enqueue_is_idempotent_on_a_retried_transaction(
    factory: async_sessionmaker[AsyncSession],
    channel: tuple[str, str],
) -> None:
    """The producer retries; ``ON CONFLICT (event_id) DO NOTHING`` keeps one row."""
    stream, _group = channel
    await _queue(factory, stream, "BTCUSDT")
    await _queue(factory, stream, "BTCUSDT")
    assert await _pending(factory) == 1


# --- Astra round 2: the five must-fixes -------------------------------------


async def test_replay_pages_by_the_whole_sort_key_not_by_id(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    """A transaction can start earlier and commit later, taking a *higher* id,
    so a replay page can legitimately end on a high id with lower ones still to
    come. Paging on ``id > after_id`` dropped exactly those — silently, which
    is the worst way to lose an event during a recovery.

    ``created_at`` is inverted against ``id`` below, and there are more rows
    than one page (``MICRO_BATCH``), so the second page is entirely made of
    ids *below* the last id of the first page.
    """
    stream, _group = channel
    total = MICRO_BATCH + 5
    since = utcnow() - timedelta(hours=1)
    for minute in range(total):
        await _queue(factory, stream, "BTCUSDT", minute)
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(
            text("UPDATE outbox_events SET created_at = now() - (id * interval '1 second')")
        )
    await dispatch_pending(redis_client, factory, batch=total)
    await redis_client.xtrim(stream, maxlen=0, approximate=False)

    assert await reconcile(redis_client, factory, since=since, limit=total) == total
    assert len(await _entries(redis_client, stream)) == total


async def test_a_truncated_replay_says_so_and_says_where_to_resume(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    """Hitting ``limit`` is a partial recovery, and silence about it is the
    bug: the same ``since`` replays the same first page forever, so the tail
    is unreachable without the operator knowing to move the window (Astra,
    T2.9 retomada). The warning carries the cursor to resume from.
    """
    stream, _group = channel
    since = utcnow() - timedelta(hours=1)
    total = 5
    for minute in range(total):
        await _queue(factory, stream, "BTCUSDT", minute)
    await dispatch_pending(redis_client, factory, batch=total)
    await redis_client.xtrim(stream, maxlen=0, approximate=False)

    with capture_logs() as logs:
        assert await reconcile(redis_client, factory, since=since, limit=3) == 3
    assert len(await _entries(redis_client, stream)) == 3

    truncated = [e for e in logs if e["event"] == "outbox_replay_truncated"]
    assert truncated, "a partial recovery must not be silent"
    assert truncated[0]["log_level"] == "warning"
    resume = truncated[0]["resume_since"]

    # The advertised cursor actually reaches the tail.
    await redis_client.xtrim(stream, maxlen=0, approximate=False)
    assert await reconcile(redis_client, factory, since=resume, limit=total) == total - 3 + 1


async def test_a_head_of_unreadable_rows_does_not_block_the_ones_behind(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    """Poison pill: the oldest rows can never be published, and the sweep
    re-selects the same head every micro-batch unless it steps over them."""
    stream, _group = channel
    for minute in range(5):
        await _queue(factory, stream, "BTCUSDT", minute)
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(text("UPDATE outbox_events SET payload = '{\"nope\": 1}'::jsonb"))
    good = await _queue(factory, stream, "ETHUSDT", 99)

    assert await dispatch_pending(redis_client, factory, micro_batch=2) == 1

    entries = await _entries(redis_client, stream)
    assert len(entries) == 1
    assert str(good) in str(entries[0][1])
    async with role_session(factory, db_role="hunter_worker") as session:
        stuck = (
            await session.execute(
                text(
                    "SELECT count(*), max(attempts) FROM outbox_events WHERE dispatched_at IS NULL"
                )
            )
        ).one()
    assert stuck[0] == 5, "the unreadable rows stay for diagnosis, never silently dropped"
    assert stuck[1] >= 1, "and their failed attempts are counted"


async def test_a_publication_cannot_outlive_the_sweep_budget(
    factory: async_sessionmaker[AsyncSession],
    channel: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checking the clock *before* the ``XADD`` did not bound the ``XADD``:
    with the client's 5s socket timeout and three retries, one publication
    could hold the transaction ~20s past the advertised budget."""
    stream, _group = channel
    await _queue(factory, stream, "BTCUSDT")

    class HangingRedis:
        async def xadd(self, *_args: Any, **_kwargs: Any) -> None:
            await asyncio.sleep(30)

    monkeypatch.setattr("hunter_core.events.outbox.BUDGET_S", 1.0)
    started = asyncio.get_running_loop().time()
    assert await dispatch_pending(HangingRedis(), factory, budget_s=1.0) == 0  # type: ignore[arg-type]
    assert asyncio.get_running_loop().time() - started < 10

    async with role_session(factory, db_role="hunter_worker") as session:
        row = (
            await session.execute(
                text("SELECT attempts, last_error, dispatched_at FROM outbox_events")
            )
        ).one()
    assert row.dispatched_at is None, "a publication that may not have landed is not marked"
    assert "budget" in row.last_error


# --- T2.9b: an unpublishable row is counted apart, never a red verdict ------

_POISON = text("UPDATE outbox_events SET payload = '{\"nope\": 1}'::jsonb WHERE event_id = :id")


async def _poison(factory: async_sessionmaker[AsyncSession], event_id: uuid.UUID) -> None:
    """Make a queued row's payload something no envelope can be built from."""
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(_POISON, {"id": event_id})


async def test_a_poisoned_row_is_counted_apart_and_leaves_readiness_green(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    """One row nobody can publish must not make a whole worker look broken.

    Before this, a payload that is not an envelope stayed pending forever, so
    ``/ready`` was red until a human edited a JSONB column — and a red that
    stays red for days stops being read as an outage. The row is still there,
    still counted, still logged; it just does not vote.
    """
    stream, _group = channel
    poisoned = await _queue(factory, stream, "BTCUSDT", 0)
    await _poison(factory, poisoned)
    good = await _queue(factory, stream, "ETHUSDT", 1)

    health = OutboxHealth()
    for _ in range(UNPUBLISHABLE_ATTEMPTS):
        await dispatch_pending(redis_client, factory, health=health)

    assert health.unpublishable == 1
    assert health.pending == 0, "the abandoned row must not be counted as owed work"
    assert health.ready(max_pending=0, max_lag_s=30.0) is True

    entries = await _entries(redis_client, stream)
    assert len(entries) == 1
    assert str(good) in str(entries[0][1])

    async with role_session(factory, db_role="hunter_worker") as session:
        attempts, last_error = (
            await session.execute(
                text("SELECT attempts, last_error FROM outbox_events WHERE event_id = :id"),
                {"id": poisoned},
            )
        ).one()
    assert attempts >= UNPUBLISHABLE_ATTEMPTS
    assert last_error is not None
    assert "payload is not an envelope" in last_error


async def test_a_poisoned_row_logs_one_warning_per_sweep_and_no_traceback(
    factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    channel: tuple[str, str],
) -> None:
    """``logger.exception`` here printed the same pydantic traceback once per
    second, forever, for a message the event name already carries. One warning
    per row per sweep is the budget."""
    stream, _group = channel
    await _poison(factory, await _queue(factory, stream, "BTCUSDT", 0))

    with capture_logs() as logs:
        await dispatch_pending(redis_client, factory, micro_batch=1)

    unreadable = [entry for entry in logs if entry["event"] == "outbox_row_unreadable"]
    assert len(unreadable) == 1, logs
    assert unreadable[0]["log_level"] == "warning"
    assert "exc_info" not in unreadable[0]


async def test_a_transport_failure_is_never_mistaken_for_an_unpublishable_row(
    factory: async_sessionmaker[AsyncSession],
    channel: tuple[str, str],
) -> None:
    """The regression this guards is readiness going green *because* Redis died.

    An outage fails the same row on every sweep, so a plain "``attempts >= N``
    and it has an error" rule would write the whole backlog off as N individual
    defects exactly when the backlog matters most.
    """
    stream, _group = channel
    await _queue(factory, stream, "BTCUSDT", 0)

    class DeadRedis:
        async def xadd(self, *_args: Any, **_kwargs: Any) -> None:
            raise ConnectionError("connection reset by peer")

    health = OutboxHealth()
    for _ in range(UNPUBLISHABLE_ATTEMPTS + 2):
        await dispatch_pending(DeadRedis(), factory, health=health)  # type: ignore[arg-type]

    assert health.unpublishable == 0, "a dead transport is an outage, not a broken row"
    assert health.pending == 1
    assert health.ready(max_pending=0, max_lag_s=30.0) is False


# --- T2.9b: retention (DATABASE.md 1.3) ------------------------------------


async def _mark(
    factory: async_sessionmaker[AsyncSession], event_id: uuid.UUID, at: datetime
) -> None:
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(
            text("UPDATE outbox_events SET dispatched_at = :at WHERE event_id = :id"),
            {"at": at, "id": event_id},
        )


async def _survivors(factory: async_sessionmaker[AsyncSession]) -> set[uuid.UUID]:
    async with role_session(factory, db_role="hunter_worker") as session:
        rows = await session.execute(text("SELECT event_id FROM outbox_events"))
        return {row[0] for row in rows}


async def test_prune_deletes_dispatched_rows_past_the_cutoff_and_nothing_else(
    factory: async_sessionmaker[AsyncSession], channel: tuple[str, str]
) -> None:
    """Retention is what keeps the queue from becoming an archive — the
    market-worker alone queues on the order of 700k rows a day. The cutoff is
    also the ceiling of the replay window: ``reconcile(since=)`` can only reach
    rows that are still in the table.
    """
    stream, _group = channel
    now = utcnow()
    old = await _queue(factory, stream, "BTCUSDT", 0)
    recent = await _queue(factory, stream, "ETHUSDT", 1)
    pending = await _queue(factory, stream, "SOLUSDT", 2)
    await _mark(factory, old, now - timedelta(days=8))
    await _mark(factory, recent, now - timedelta(days=6))

    async with role_session(factory, db_role="hunter_worker") as session:
        deleted = await prune_dispatched(session, now - timedelta(days=7))

    assert deleted == 1
    assert await _survivors(factory) == {recent, pending}


async def test_prune_never_deletes_a_pending_row_however_old(
    factory: async_sessionmaker[AsyncSession], channel: tuple[str, str]
) -> None:
    """A row with ``dispatched_at IS NULL`` is a publication the system owes.
    Age does not settle a debt, and a retention job that deleted one would
    produce exactly the silent loss the outbox exists to make impossible."""
    stream, _group = channel
    owed = await _queue(factory, stream, "BTCUSDT", 0)
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(
            text("UPDATE outbox_events SET created_at = :at WHERE event_id = :id"),
            {"at": utcnow() - timedelta(days=400), "id": owed},
        )

    async with role_session(factory, db_role="hunter_worker") as session:
        deleted = await prune_dispatched(session, utcnow())

    assert deleted == 0
    assert await _survivors(factory) == {owed}


async def test_prune_is_bounded_by_its_batch_so_the_job_can_loop(
    factory: async_sessionmaker[AsyncSession], channel: tuple[str, str]
) -> None:
    """One ``DELETE`` over a whole day of rows would hold locks and produce WAL
    for as long as it ran, on a table the dispatcher is writing to. The job
    calls this in a loop until it returns less than it asked for."""
    stream, _group = channel
    cutoff = utcnow() - timedelta(days=7)
    for minute in range(5):
        queued = await _queue(factory, stream, "BTCUSDT", minute)
        # ``minute + 1``: the cutoff is exclusive, so a row dispatched *at* it stays.
        await _mark(factory, queued, cutoff - timedelta(minutes=minute + 1))

    pruned: list[int] = []
    for _ in range(3):
        async with role_session(factory, db_role="hunter_worker") as session:
            pruned.append(await prune_dispatched(session, cutoff, 2))

    assert pruned == [2, 2, 1]
    assert await _survivors(factory) == set()


_BULK_DISPATCHED = """
INSERT INTO outbox_events (event_id, stream, payload, created_at, dispatched_at)
SELECT gen_random_uuid(), 'market.candles.closed', '{}'::jsonb,
       now() - (n || ' seconds')::interval,
       now() - (n || ' seconds')::interval
FROM generate_series(1, 60000) AS n
"""
"""A backlog of dispatched rows retention has not reached yet. Sixty thousand is
under a day of the market-worker's own volume (~700k/day, DATABASE.md §1.3) and
well under the seven days it keeps — the point is only that it is large enough
for the planner to have a real choice."""


async def test_prune_takes_its_batch_from_an_index_and_never_a_seq_scan(
    outbox_engine: AsyncEngine,
) -> None:
    """The batch is ordered by ``id``, and ``EXPLAIN`` is the proof.

    Ordering by ``dispatched_at`` — which is what this did — reads as "oldest
    first" and costs a **Seq Scan of the whole table plus a sort**, every batch,
    every loop of the retention job, because ``dispatched_at`` has no index and
    deliberately gets none: it would be maintained on every ``mark_dispatched``,
    i.e. on the dispatcher's hot path, and would cover every dispatched row the
    seven-day retention still holds, to serve a job that runs once a day. The
    primary key is already there, is insertion order, and lets the scan stop at
    ``batch`` rows.
    """
    async with outbox_engine.begin() as connection:
        await connection.execute(text(_BULK_DISPATCHED))
        await connection.execute(text("ANALYZE outbox_events"))

    compiled = prunable_ids(utcnow(), PRUNE_BATCH).compile(
        dialect=postgresql.dialect(paramstyle="named")
    )
    async with outbox_engine.connect() as connection:
        rows = await connection.scalars(text(f"EXPLAIN {compiled}"), dict(compiled.params))
        plan = "\n".join(rows)

    assert "Seq Scan" not in plan, plan
    assert "Index Scan using pk_outbox_events" in plan, plan


async def test_prune_refuses_a_naive_cutoff(factory: async_sessionmaker[AsyncSession]) -> None:
    """Seven days ago on whose clock? A naive cutoff would silently mean the
    box's local time and delete a different set of rows in every region."""
    async with role_session(factory, db_role="hunter_worker") as session:
        with pytest.raises(ValueError, match="timezone-aware"):
            await prune_dispatched(session, datetime(2026, 9, 6, 12, 0))  # noqa: DTZ001
