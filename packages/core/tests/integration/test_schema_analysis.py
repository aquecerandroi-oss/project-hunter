"""The M2 analysis contracts — migration ``0003_analysis``, DATABASE.md §17.

Every assertion here is about something the *database* must refuse, because each
one is a promise the pipeline makes to a person reading a score weeks later:

- a ``feature_baselines`` revision is written once and never edited, and cannot
  be deleted except by a job that says it is the retention job;
- a recomputation after a backfill is a new revision, while a retry of the same
  computation is a no-op — the difference is ``input_fingerprint``;
- one opportunity episode per market while it is open, keyed on ``expired_at``
  rather than on a list of statuses, with ``status = 'EXPIRED'`` and
  ``expired_at`` unable to disagree;
- one active anomaly per (market, type), with data quality on its own axis;
- ``outbox_events`` de-duplicates on ``event_id`` and can absorb every pending
  row of ``shadow_outbox`` without losing one.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.domain.types import uuid7
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.outbox_event import envelope_from_row

pytestmark = pytest.mark.integration

_WINDOW_END = datetime(2026, 9, 5, 11, 59, tzinfo=UTC)
_AVAILABLE_AT = datetime(2026, 9, 5, 12, 1, tzinfo=UTC)
_IMMUTABLE = "is immutable"
_RETENTION_ONLY = "may only be deleted by the retention job"


@pytest_asyncio.fixture
async def connection(schema_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose work is rolled back — these tests share one database."""
    async with schema_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


async def _market(connection: AsyncConnection) -> uuid.UUID:
    exchange, market = uuid7(), uuid7()
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Probe')"),
        {"id": exchange, "code": f"probe-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:id, :exchange, :symbol, 'perpetual')"
        ),
        {"id": market, "exchange": exchange, "symbol": f"BTC{uuid.uuid4().hex[:6].upper()}"},
    )
    return market


_BASELINE_SQL = text(
    "INSERT INTO feature_baselines "
    "(id, market_id, feature, feature_version, algo_version, hour_of_day, "
    " window_start, window_end, available_at, median, mad, sample_size, "
    " expected_size, distinct_days, coverage, source, sampling, input_fingerprint) "
    "VALUES (:id, :market, :feature, 1, 'mad_v1', :hour, :window_start, :window_end, "
    " :available_at, :median, :mad, :sample_size, 420, 7, :coverage, :source, "
    " 'per_minute', :fingerprint) "
    "RETURNING id"
)


async def _baseline(connection: AsyncConnection, market: uuid.UUID, **overrides: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "id": uuid7(),
        "market": market,
        "feature": "volume_relative",
        "hour": 11,
        "window_start": _WINDOW_END - timedelta(days=7),
        "window_end": _WINDOW_END,
        "available_at": _AVAILABLE_AT,
        "median": Decimal("1.0000000000"),
        "mad": Decimal("0.2500000000"),
        "sample_size": 400,
        "coverage": Decimal("0.952381"),
        "source": "live",
        "fingerprint": uuid.uuid4().hex,
    }
    values.update(overrides)
    result = await connection.execute(_BASELINE_SQL, values)
    return result.scalar_one()


async def _opportunity(
    connection: AsyncConnection, market: uuid.UUID, **overrides: Any
) -> uuid.UUID:
    values: dict[str, Any] = {
        "id": uuid7(),
        "market": market,
        "score": Decimal("80.00"),
        "confidence": Decimal("0.9000"),
        "status": "HOT",
        "stage": "EARLY",
        "expired_at": None,
    }
    values.update(overrides)
    await connection.execute(
        text(
            "INSERT INTO opportunities "
            "(id, market_id, direction, score, confidence, status, stage, expired_at) "
            "VALUES (:id, :market, 'long', :score, :confidence, :status, :stage, :expired_at)"
        ),
        values,
    )
    return values["id"]


async def _anomaly(connection: AsyncConnection, market: uuid.UUID, *, status: str) -> uuid.UUID:
    anomaly_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO anomalies (id, market_id, type, severity, confidence, status) "
            "VALUES (:id, :market, 'VOLUME_SPIKE', 75.00, 0.8000, :status)"
        ),
        {"id": anomaly_id, "market": market, "status": status},
    )
    return anomaly_id


async def _outbox(
    connection: AsyncConnection,
    event_id: uuid.UUID,
    *,
    stream: str = "opportunities.updated",
    attempts: int = 0,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO outbox_events (event_id, stream, attempts) "
            "VALUES (:id, :stream, :attempts)"
        ),
        {"id": event_id, "stream": stream, "attempts": attempts},
    )


# --------------------------------------------------------------- baselines


async def test_a_baseline_revision_cannot_be_updated(connection: AsyncConnection) -> None:
    """The whole point of the archive: recomputing tomorrow reproduces today.

    If a revision could be edited, every score that names it would change
    meaning silently, and "recompute this score from what it saw" would be a
    claim nobody could check. The trigger refuses for every role, the owner
    included — the grants already deny ``UPDATE`` to both application roles, and
    this is the second lock.
    """
    market = await _market(connection)
    baseline_id = await _baseline(connection, market)

    with pytest.raises(DBAPIError, match=_IMMUTABLE):
        await connection.execute(
            text("UPDATE feature_baselines SET median = 2 WHERE id = :id"), {"id": baseline_id}
        )


async def test_the_worker_can_lock_a_baseline_row_and_still_cannot_rewrite_it(
    schema_engine: AsyncEngine,
) -> None:
    """BUG-1 of T2.5, closed by ``0005`` — and the archive is untouched.

    §17.2 makes the writer take ``SELECT ... FOR SHARE`` on every
    ``baseline_id`` it is about to reference, so that the retention job's
    ``FOR UPDATE`` on the same row cannot delete a revision between "the job
    proved nobody references it" and "the scorer wrote the envelope". PostgreSQL
    requires the ``UPDATE`` privilege for that lock, which ``0003`` deliberately
    withheld, so the statement failed with *permission denied* and the scanner
    degraded to an existence check.

    Both halves are asserted here, as ``hunter_worker`` itself, because the pair
    is the point: the lock now works, and the ``UPDATE`` the grant nominally
    authorises is still refused row by row by ``feature_baselines_immutable``.
    Immutability was never the grant's to keep — the trigger refuses the owner
    too, and no ``REVOKE`` reaches an owner.
    """
    async with schema_engine.begin() as setup:
        await setup.execute(text("GRANT hunter_worker TO CURRENT_USER"))

    async with schema_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL ROLE hunter_worker"))
            market = await _market(conn)
            baseline_id = await _baseline(conn, market)

            locked = await conn.scalar(
                text("SELECT id FROM feature_baselines WHERE id = ANY(:ids) FOR SHARE"),
                {"ids": [str(baseline_id)]},
            )
            assert locked == baseline_id, "hunter_worker still cannot take the row lock"

            with pytest.raises(DBAPIError, match=_IMMUTABLE):
                await conn.execute(
                    text("UPDATE feature_baselines SET median = 2 WHERE id = :id"),
                    {"id": baseline_id},
                )
        finally:
            await transaction.rollback()


async def test_the_lock_grant_did_not_open_the_retention_door_for_the_worker(
    schema_engine: AsyncEngine,
) -> None:
    """``0005`` widened one privilege and no behaviour: a ``DELETE`` by the role
    that owns the scanner is still refused unless it declares itself the
    retention job. A bug in the scanner must not be able to delete the evidence
    its own scores point at."""
    async with schema_engine.begin() as setup:
        await setup.execute(text("GRANT hunter_worker TO CURRENT_USER"))

    async with schema_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL ROLE hunter_worker"))
            market = await _market(conn)
            baseline_id = await _baseline(conn, market)

            with pytest.raises(DBAPIError, match=_RETENTION_ONLY):
                await conn.execute(
                    text("DELETE FROM feature_baselines WHERE id = :id"), {"id": baseline_id}
                )
        finally:
            await transaction.rollback()


async def test_a_baseline_cannot_be_deleted_without_declaring_the_retention_job(
    connection: AsyncConnection,
) -> None:
    """Deletion has to be an act, not an accident.

    Retention does eventually expire revisions — they are not append-only like
    ``audit_logs`` — but only after proving no preserved sample still depends on
    them. Requiring the marker means a bug in the scanner cannot delete the
    evidence its own scores point at.
    """
    market = await _market(connection)
    baseline_id = await _baseline(connection, market)

    with pytest.raises(DBAPIError, match=_RETENTION_ONLY):
        await connection.execute(
            text("DELETE FROM feature_baselines WHERE id = :id"), {"id": baseline_id}
        )


async def test_the_retention_job_may_delete_a_baseline_when_it_says_so(
    connection: AsyncConnection,
) -> None:
    """``SET LOCAL`` — transaction-scoped, so it cannot leak across a pooled
    connection, exactly like ``app.current_org``."""
    market = await _market(connection)
    baseline_id = await _baseline(connection, market)

    await connection.execute(text("SET LOCAL app.baseline_retention = 'on'"))
    result = await connection.execute(
        text("DELETE FROM feature_baselines WHERE id = :id RETURNING id"), {"id": baseline_id}
    )
    assert result.scalar_one() == baseline_id


async def test_the_retention_marker_does_not_survive_its_transaction(
    schema_engine: AsyncEngine,
) -> None:
    """``SET LOCAL`` ends with the transaction — proven, not assumed.

    That is the whole reason the marker is safe behind the pooler: a connection
    that ran the retention job must not hand the next borrower of that same
    connection the right to delete baselines. Two transactions on one connection
    is exactly the shape the pooler produces.
    """
    async with schema_engine.connect() as connection:
        first = await connection.begin()
        market = await _market(connection)
        kept = await _baseline(connection, market)
        await connection.execute(text("SET LOCAL app.baseline_retention = 'on'"))
        await first.commit()

        second = await connection.begin()
        try:
            with pytest.raises(DBAPIError, match=_RETENTION_ONLY):
                await connection.execute(
                    text("DELETE FROM feature_baselines WHERE id = :id"), {"id": kept}
                )
        finally:
            await second.rollback()

        cleanup = await connection.begin()
        await connection.execute(text("SET LOCAL app.baseline_retention = 'on'"))
        await connection.execute(text("DELETE FROM markets WHERE id = :id"), {"id": market})
        await cleanup.commit()


async def test_a_retry_of_the_same_computation_collides_and_a_recomputation_does_not(
    connection: AsyncConnection,
) -> None:
    """``input_fingerprint`` is what separates the two.

    Astra's scenario: the 09:00 window is computed at 10:00, and at 10:15 a
    backfill changes what that window contains. Market, feature, versions, hour,
    ``window_end`` and source are all still identical, so without the
    fingerprint in the key the corrected revision could not be stored at all —
    ``DO NOTHING`` would keep the incomplete one and ``UPDATE`` is refused. With
    it, a redelivered refresh job is a no-op and a genuine recomputation is a new
    revision with a later ``available_at``.
    """
    market = await _market(connection)
    fingerprint = uuid.uuid4().hex
    await _baseline(connection, market, fingerprint=fingerprint, sample_size=400)

    with pytest.raises(IntegrityError, match="uq_feature_baselines_revision"):
        await _baseline(connection, market, fingerprint=fingerprint, sample_size=400)


async def test_a_recomputation_after_a_backfill_lands_as_a_new_revision(
    connection: AsyncConnection,
) -> None:
    market = await _market(connection)
    first = await _baseline(connection, market, fingerprint=uuid.uuid4().hex, sample_size=400)
    second = await _baseline(
        connection,
        market,
        fingerprint=uuid.uuid4().hex,
        sample_size=418,
        available_at=_AVAILABLE_AT + timedelta(minutes=15),
    )

    assert first != second
    surviving = await connection.scalar(
        text("SELECT count(*) FROM feature_baselines WHERE market_id = :market"), {"market": market}
    )
    assert surviving == 2, "the corrected revision must not replace the one a score already named"


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"hour": 24}, "hour_of_day_in_range"),
        ({"window_start": _WINDOW_END + timedelta(days=1)}, "window_is_ordered_and_causal"),
        ({"available_at": _WINDOW_END - timedelta(minutes=1)}, "window_is_ordered_and_causal"),
        ({"sample_size": 421}, "counts_are_coherent"),
        ({"coverage": Decimal("1.500000")}, "coverage_is_a_fraction"),
        ({"mad": Decimal("-0.0000000001")}, "mad_not_negative"),
    ],
)
async def test_a_baseline_cannot_be_internally_inconsistent(
    connection: AsyncConnection, overrides: dict[str, Any], constraint: str
) -> None:
    """Local invariants, so a broken refresh fails at the write and not at the
    read three weeks later. ``available_at`` before ``window_end`` is the one
    worth naming: a baseline cannot have been usable before its window closed.
    """
    market = await _market(connection)
    with pytest.raises(IntegrityError, match=constraint):
        await _baseline(connection, market, **overrides)


# -------------------------------------------------------------- episodes


async def test_episode_identity_is_keyed_on_expired_at_and_not_on_a_status_list(
    schema_engine: AsyncEngine,
) -> None:
    """Alembic never sees this, so the test has to.

    ``alembic check`` compares an index's *columns* and not its ``WHERE``
    clause, so an index left with ``0001``'s status list would report no drift
    while enforcing an invariant the M2 decision replaced. The predicate is read
    from ``pg_indexes`` for that reason.
    """
    async with schema_engine.connect() as connection:
        definition = await connection.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": "uq_opportunities_open_per_market"},
        )
    assert definition is not None
    assert "(expired_at IS NULL)" in definition
    assert "WATCHING" not in definition, "the status-list predicate of 0001 is still in place"


async def test_a_market_can_only_have_one_open_episode(connection: AsyncConnection) -> None:
    market = await _market(connection)
    await _opportunity(connection, market, status="HOT")

    with pytest.raises(IntegrityError, match="uq_opportunities_open_per_market"):
        await _opportunity(connection, market, status="WATCHING")


async def test_a_normal_episode_still_holds_the_slot(connection: AsyncConnection) -> None:
    """The decisive scenario of the joint decision, at the schema level.

    HOT(id=A, 80) that falls to NORMAL(35) and recovers to WATCHING(45) has to
    stay the same episode. Under ``0001``'s predicate the row left the index the
    moment it went NORMAL and a second episode could take the slot — the Radar
    would then show a "new" opportunity that is the same move. The state machine
    itself is T2.4/T2.5; what the database has to guarantee is that the slot is
    never free while the episode is unexpired.
    """
    market = await _market(connection)
    episode = await _opportunity(connection, market, status="HOT", score=Decimal("80.00"))

    await connection.execute(
        text(
            "UPDATE opportunities SET status = 'NORMAL', score = 35.00, "
            "below_40_since = now() WHERE id = :id"
        ),
        {"id": episode},
    )
    with pytest.raises(IntegrityError, match="uq_opportunities_open_per_market"):
        await _opportunity(connection, market, status="WATCHING")


async def test_an_expired_episode_frees_the_slot_for_a_new_one(
    connection: AsyncConnection,
) -> None:
    """Recovery after a real expiry is a *new* episode, with a new id."""
    market = await _market(connection)
    first = await _opportunity(
        connection, market, status="EXPIRED", expired_at=datetime.now(tz=UTC)
    )
    second = await _opportunity(connection, market, status="WATCHING")
    assert first != second


@pytest.mark.parametrize(
    ("status", "expired_at"),
    [("EXPIRED", None), ("WATCHING", datetime(2026, 9, 5, 12, tzinfo=UTC))],
)
async def test_status_and_expired_at_cannot_disagree(
    connection: AsyncConnection, status: str, expired_at: datetime | None
) -> None:
    """``(status = 'EXPIRED') = (expired_at IS NOT NULL)``, both directions.

    The index above keys episode identity on ``expired_at`` and every consumer
    reads ``status``; if the two could drift, an episode would be open for the
    index and finished for the Radar, or the reverse.
    """
    market = await _market(connection)
    with pytest.raises(IntegrityError, match="expired_at_matches_status"):
        await _opportunity(connection, market, status=status, expired_at=expired_at)


async def test_the_new_status_and_stage_labels_are_usable(connection: AsyncConnection) -> None:
    """``EXTENDED`` exists on both axes and they are different types: a status
    ``EXTENDED`` episode can carry stage ``DEVELOPING`` and vice versa."""
    market = await _market(connection)
    episode = await _opportunity(connection, market, status="EXTENDED", stage="DEVELOPING")
    row = await connection.execute(
        text("SELECT status::text, stage::text FROM opportunities WHERE id = :id"), {"id": episode}
    )
    assert row.one() == ("EXTENDED", "DEVELOPING")


async def test_history_carries_the_envelope_and_the_stage(connection: AsyncConnection) -> None:
    """A sample has to be recomputable from what it actually saw."""
    market = await _market(connection)
    episode = await _opportunity(connection, market)
    envelope = '{"as_of": "2026-09-05T12:00:00Z", "baseline_ids": [], "state_in": {}}'
    await connection.execute(
        text(
            "INSERT INTO opportunity_history "
            "(opportunity_id, ts, score, confidence, status, stage, envelope) "
            "VALUES (:id, :ts, 80.00, 0.9000, 'HOT', 'EARLY', CAST(:envelope AS jsonb))"
        ),
        {"id": episode, "ts": datetime(2026, 9, 5, 12, tzinfo=UTC), "envelope": envelope},
    )
    stored = await connection.scalar(
        text("SELECT envelope ->> 'as_of' FROM opportunity_history WHERE opportunity_id = :id"),
        {"id": episode},
    )
    assert stored == "2026-09-05T12:00:00Z"


# -------------------------------------------------------------- anomalies


async def test_only_one_anomaly_of_a_type_can_be_active_on_a_market(
    connection: AsyncConnection,
) -> None:
    market = await _market(connection)
    await _anomaly(connection, market, status="active")

    with pytest.raises(IntegrityError, match="uq_anomalies_active_per_market_type"):
        await _anomaly(connection, market, status="active")


async def test_a_resolved_anomaly_does_not_block_the_next_one(
    connection: AsyncConnection,
) -> None:
    """Dedupe is per *active* anomaly; the history of the same (market, type) is
    unbounded, which is what makes a 24-hour timeline possible."""
    market = await _market(connection)
    await _anomaly(connection, market, status="resolved")
    await _anomaly(connection, market, status="expired")
    await _anomaly(connection, market, status="active")

    total = await connection.scalar(
        text("SELECT count(*) FROM anomalies WHERE market_id = :market"), {"market": market}
    )
    assert total == 3


async def test_evaluation_state_is_a_separate_axis_from_status(
    connection: AsyncConnection,
) -> None:
    """``active + unknown``: the feed went away, so the anomaly is ineligible and
    is *not* resolved. "We stopped looking" is not "it stopped happening"."""
    market = await _market(connection)
    anomaly = await _anomaly(connection, market, status="active")

    default_state = await connection.scalar(
        text("SELECT evaluation_state::text FROM anomalies WHERE id = :id"), {"id": anomaly}
    )
    assert default_state == "ok"

    await connection.execute(
        text("UPDATE anomalies SET evaluation_state = 'unknown' WHERE id = :id"), {"id": anomaly}
    )
    row = await connection.execute(
        text("SELECT status::text, evaluation_state::text FROM anomalies WHERE id = :id"),
        {"id": anomaly},
    )
    assert row.one() == ("active", "unknown")


# ----------------------------------------------------------------- outbox


async def test_the_outbox_queues_an_event_once(connection: AsyncConnection) -> None:
    """A retried transaction must not publish twice."""
    event_id = uuid7()
    await _outbox(connection, event_id)
    with pytest.raises(IntegrityError, match="uq_outbox_events_event_id"):
        await _outbox(connection, event_id)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"stream": ""}, "stream_not_empty"),
        ({"attempts": -1}, "attempts_not_negative"),
    ],
)
async def test_the_outbox_refuses_an_event_it_could_not_dispatch(
    connection: AsyncConnection, overrides: dict[str, Any], constraint: str
) -> None:
    """A nameless stream is an event that can never be delivered, and a negative
    attempt count is a retry counter that has lost its place. One expected
    failure per test: a violated constraint aborts the transaction, so two of
    them in one would report the wrong error for the second."""
    with pytest.raises(IntegrityError, match=constraint):
        await _outbox(connection, uuid7(), **overrides)


async def test_pending_events_are_found_by_the_partial_index(
    schema_engine: AsyncEngine,
) -> None:
    """``dispatched_at IS NULL`` is the pending predicate, not a watermark on
    ``id``: the sequence has gaps and its order is not commit order.

    ``0004`` widened the key from ``(id)`` to ``(created_at, id)`` -- the order
    the dispatcher actually claims in. With ``(id)`` alone Postgres abandoned the
    index and seq-scanned plus sorted the whole pending set on every sweep
    (measured 15.3 ms against 0.2 ms per claim with 30k pending rows).
    """
    async with schema_engine.connect() as connection:
        definition = await connection.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_outbox_events_pending'")
        )
    assert definition is not None
    assert "(dispatched_at IS NULL)" in definition
    assert "(created_at, id)" in definition, definition


ABSORB_SHADOW_OUTBOX = """
INSERT INTO outbox_events
    (event_id, stream, payload, created_at, dispatched_at, attempts, last_error)
SELECT
    event_id,
    stream,
    jsonb_build_object(
        'event_id', event_id,
        'type',     stream,
        'ts',       to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || 'Z',
        'producer', 'strategy-worker.shadow',
        'key',      coalesce(nullif(payload ->> 'symbol', ''), event_id::text),
        'payload',  payload
    ),
    created_at,
    dispatched_at,
    attempts,
    last_error
FROM shadow_outbox
"""
"""The absorption of ``shadow_outbox``, exactly as DATABASE.md §17.5 documents it.

Not a plain column copy: the two queues store *different things* in ``payload``.
``shadow_outbox`` keeps only the business payload and the S2 dispatcher builds
the envelope at publication time; ``outbox_events`` keeps the whole envelope, so
that a row is a finished message and republishing it is the same bytes. Copying
the legacy column across would produce rows the generic dispatcher rejects as
"payload is not an envelope" — pending forever, counted as unpublishable, never
delivered. So the statement **wraps**:

- ``event_id`` is the same value in both places — identity is preserved, which
  is the whole point of not losing pendencies;
- ``type`` is the row's own ``stream``;
- ``ts`` is ``created_at``. The historical ``ts`` does not exist: S2 generated it
  at dispatch, so for a row that never dispatched there is nothing to recover.
  ``created_at`` is the honest substitute — the instant the decision committed —
  and it is documented as a substitute rather than passed off as the original;
- ``producer`` is S2's own ``PRODUCER`` (``strategy-worker.shadow``), because
  that is who produced it;
- ``key`` repeats S2's heuristic (``payload["symbol"] or event_id``), so routing
  after the absorption is identical to routing before it.
"""


async def test_the_generic_outbox_can_absorb_shadow_outbox_without_losing_a_pending_row(
    connection: AsyncConnection,
) -> None:
    """SHADOW-LAB.md §6: T2.9 absorbs ``shadow_outbox`` preserving pendencies.

    The copy has an explicit column list that keeps ``event_id`` — the durable
    identity — and lets ``id`` be re-issued locally, because ``id`` is a drain
    order and copying it across two populated queues would collide for no
    benefit. This is the statement T2.9 will run; proving it here means the two
    shapes cannot drift apart without a test failing.
    """
    pending, dispatched = uuid7(), uuid7()
    await connection.execute(
        text(
            "INSERT INTO shadow_outbox (event_id, stream, payload, attempts, last_error) "
            "VALUES (:id, 'shadow.signals.emitted', CAST(:payload AS jsonb), 2, 'timeout')"
        ),
        {"id": pending, "payload": '{"signal_id": "x", "symbol": "BTCUSDT"}'},
    )
    await connection.execute(
        text(
            "INSERT INTO shadow_outbox (event_id, stream, payload, dispatched_at) "
            "VALUES (:id, 'shadow.signals.emitted', '{}'::jsonb, now())"
        ),
        {"id": dispatched},
    )

    await connection.execute(text(ABSORB_SHADOW_OUTBOX))

    row = await connection.execute(
        text(
            "SELECT stream, payload -> 'payload' ->> 'signal_id', attempts, last_error, "
            "dispatched_at FROM outbox_events WHERE event_id = :id"
        ),
        {"id": pending},
    )
    stream, signal, attempts, last_error, dispatched_at = row.one()
    assert (stream, signal, attempts, last_error) == (
        "shadow.signals.emitted",
        "x",
        2,
        "timeout",
    )
    assert dispatched_at is None, "an undelivered event must stay pending after the absorption"

    still_pending = await connection.scalar(
        text("SELECT count(*) FROM outbox_events WHERE dispatched_at IS NULL")
    )
    assert still_pending == 1


async def test_an_absorbed_row_is_an_envelope_the_generic_dispatcher_can_publish(
    connection: AsyncConnection,
) -> None:
    """The absorbed row has to survive ``envelope_from_row`` — that is the only
    thing standing between it and the stream.

    ``dispatch_pending`` does exactly two things with a claimed row: rebuild the
    envelope from ``payload`` and ``XADD`` it. A row whose ``payload`` is the
    bare legacy business dict fails the first step with ``ValueError`` and is
    counted unpublishable instead of delivered, which is precisely the silent
    loss the absorption exists to avoid. So the assertion is not "the columns
    match" but "the model parses it, and every envelope field says what it
    should".
    """
    event_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO shadow_outbox (event_id, stream, payload) "
            "VALUES (:id, 'shadow.signals.emitted', CAST(:payload AS jsonb))"
        ),
        {"id": event_id, "payload": '{"signal_id": "s-1", "symbol": "ETHUSDT"}'},
    )
    await connection.execute(text(ABSORB_SHADOW_OUTBOX))

    stored_payload, created_at = (
        await connection.execute(
            text("SELECT payload, created_at FROM outbox_events WHERE event_id = :id"),
            {"id": event_id},
        )
    ).one()

    envelope = envelope_from_row(stored_payload)

    assert envelope.event_id == event_id, "the identity must survive the absorption unchanged"
    assert envelope.type == "shadow.signals.emitted"
    assert envelope.ts == created_at, "created_at is the documented substitute for the lost ts"
    assert envelope.ts.tzinfo is not None
    assert envelope.producer == "strategy-worker.shadow"
    assert envelope.key == "ETHUSDT", "routing must keep S2's payload['symbol'] heuristic"
    assert envelope.payload == {"signal_id": "s-1", "symbol": "ETHUSDT"}
    assert EventEnvelope.from_bytes(envelope.to_bytes()) == envelope


async def test_an_absorbed_row_without_a_symbol_falls_back_to_its_event_id(
    connection: AsyncConnection,
) -> None:
    """S2's key heuristic is ``payload["symbol"] or event_id``; both halves.

    A shadow event that carries no symbol still needs a routing key, and an
    empty string is not one — ``key`` is part of the envelope contract.
    """
    event_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO shadow_outbox (event_id, stream, payload) "
            "VALUES (:id, 'shadow.signals.emitted', '{\"symbol\": \"\"}'::jsonb)"
        ),
        {"id": event_id},
    )
    await connection.execute(text(ABSORB_SHADOW_OUTBOX))

    stored_payload = await connection.scalar(
        text("SELECT payload FROM outbox_events WHERE event_id = :id"), {"id": event_id}
    )
    assert envelope_from_row(stored_payload).key == str(event_id)
