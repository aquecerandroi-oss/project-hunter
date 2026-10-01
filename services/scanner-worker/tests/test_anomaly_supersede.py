"""The anomaly writer keeps the database invariant even when memory forgot a row.

Production, 2026-10-01 (``obsidian/10-PERFORMANCE/Scanner-lag-2026-10-01.md``): the
scanner persisted nothing for 14 hours. One failed flush dropped the batch that
carried the ``RESOLVE``/``EXPIRE`` of an anomaly row *after* the in-memory state
had already moved on (``collect_anomalies`` forgets the id before the commit),
so the next ``OPEN`` carried a fresh id while the old row was still ``active`` in
Postgres. ``uq_anomalies_active_per_market_type`` then rejected **every** batch
that contained that pair -- 200 markets' worth of rows, forever, and the ACKs
that wait for the commit with them.

The writer is the one place that sees both the incoming row and the table, so it
is where "one active row per (market, type)" is enforced: a row the batch does
not mention is superseded in the same transaction, never left to veto it.
Real Postgres, because the index is the thing being proved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from hunter_core.db.models.analysis import Anomaly
from hunter_core.db.session import role_session
from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
)
from hunter_core.domain.types import uuid7
from hunter_indicators.anomalies import AnomalyDirection, AnomalyState
from hunter_scanner_worker import rows as row_builders
from hunter_scanner_worker.persist import WriteBatch, flush_batch
from hunter_scanner_worker.writers import supersede_orphan_anomalies

from .db_helpers import seed_market

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 30, 13, 36, tzinfo=UTC)


class NullRedis:
    async def sadd(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def expire(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def xack(self, *args: Any, **kwargs: Any) -> int:
        return 0


def _state(
    market_id: uuid.UUID,
    *,
    detected_at: datetime,
    observed_at: datetime,
    status: AnomalyStatus = AnomalyStatus.ACTIVE,
    kind: AnomalyType = AnomalyType.MOMENTUM_SHIFT,
    reason: str | None = None,
) -> AnomalyState:
    closed = status is not AnomalyStatus.ACTIVE
    return AnomalyState(
        market_id=market_id,
        type=kind,
        status=status,
        evaluation_state=AnomalyEvaluationState.OK,
        detected_at=detected_at,
        observation_ts=observed_at,
        severity=Decimal("26.68"),
        confidence=Decimal("0.9100"),
        baseline=Decimal("1.0000000000"),
        current_value=Decimal("4.7000000000"),
        deviation=Decimal("6.1000"),
        direction=AnomalyDirection.UP,
        unit="atr",
        detector_version="momentum_shift_v1",
        normalization_version="mad_piecewise_v1@v2",
        resolved_at=observed_at if closed else None,
        reason=reason,
    )


async def _write(factory: Any, state: AnomalyState, anomaly_id: uuid.UUID) -> None:
    batch = WriteBatch(anomalies=[row_builders.anomaly_row(state, anomaly_id=anomaly_id)])
    await flush_batch(factory, cast("Any", NullRedis()), batch, now=NOW)


async def _rows(factory: Any, market_id: uuid.UUID) -> dict[uuid.UUID, Anomaly]:
    async with role_session(factory, db_role="hunter_worker") as session:
        found = (
            (await session.execute(select(Anomaly).where(Anomaly.market_id == market_id)))
            .scalars()
            .all()
        )
    return {row.id: row for row in found}


async def test_open_with_a_new_id_supersedes_an_orphan_active_row(db_session_factory: Any) -> None:
    """The wedge itself: memory forgot X, the table still has it ``active``."""
    market_id = await seed_market(db_session_factory, "sup-a", "BTCUSDT")
    orphan, fresh = uuid7(), uuid7()
    first = NOW - timedelta(hours=5)
    await _write(
        db_session_factory, _state(market_id, detected_at=first, observed_at=first), orphan
    )

    opened = _state(market_id, detected_at=NOW, observed_at=NOW)
    await _write(db_session_factory, opened, fresh)  # raised IntegrityError before the fix

    stored = await _rows(db_session_factory, market_id)
    assert stored[fresh].status is AnomalyStatus.ACTIVE
    assert stored[orphan].status is AnomalyStatus.EXPIRED
    assert stored[orphan].resolved_at == NOW
    assert stored[orphan].meta["superseded_by"] == str(fresh)
    assert stored[orphan].meta["state"]["status"] == "expired"


async def test_a_batch_that_closes_the_old_row_itself_keeps_its_own_verdict(
    db_session_factory: Any,
) -> None:
    """Normal path: ``[X resolved, Y open]`` in one statement. X must stay resolved."""
    market_id = await seed_market(db_session_factory, "sup-b", "BTCUSDT")
    old, fresh = uuid7(), uuid7()
    first = NOW - timedelta(hours=1)
    await _write(db_session_factory, _state(market_id, detected_at=first, observed_at=first), old)

    resolved = _state(market_id, detected_at=first, observed_at=NOW, status=AnomalyStatus.RESOLVED)
    opened = _state(market_id, detected_at=NOW, observed_at=NOW)
    batch = WriteBatch(
        anomalies=[
            row_builders.anomaly_row(resolved, anomaly_id=old),
            row_builders.anomaly_row(opened, anomaly_id=fresh),
        ]
    )
    await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    stored = await _rows(db_session_factory, market_id)
    assert stored[old].status is AnomalyStatus.RESOLVED
    assert "superseded_by" not in stored[old].meta
    assert stored[fresh].status is AnomalyStatus.ACTIVE


async def test_updating_the_active_row_by_its_own_id_supersedes_nothing(
    db_session_factory: Any,
) -> None:
    market_id = await seed_market(db_session_factory, "sup-c", "BTCUSDT")
    anomaly_id = uuid7()
    first = NOW - timedelta(minutes=10)
    await _write(
        db_session_factory, _state(market_id, detected_at=first, observed_at=first), anomaly_id
    )
    await _write(
        db_session_factory, _state(market_id, detected_at=first, observed_at=NOW), anomaly_id
    )

    stored = await _rows(db_session_factory, market_id)
    assert list(stored) == [anomaly_id]
    assert stored[anomaly_id].status is AnomalyStatus.ACTIVE
    assert "superseded_by" not in stored[anomaly_id].meta


async def test_open_listed_before_the_close_in_the_same_batch_still_commits(
    db_session_factory: Any,
) -> None:
    """The index is checked row by row, so the writer puts closes before opens."""
    market_id = await seed_market(db_session_factory, "sup-d", "BTCUSDT")
    old, fresh = uuid7(), uuid7()
    first = NOW - timedelta(hours=1)
    await _write(db_session_factory, _state(market_id, detected_at=first, observed_at=first), old)

    resolved = _state(market_id, detected_at=first, observed_at=NOW, status=AnomalyStatus.RESOLVED)
    opened = _state(market_id, detected_at=NOW, observed_at=NOW)
    batch = WriteBatch(
        anomalies=[
            row_builders.anomaly_row(opened, anomaly_id=fresh),
            row_builders.anomaly_row(resolved, anomaly_id=old),
        ]
    )
    await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    stored = await _rows(db_session_factory, market_id)
    assert stored[old].status is AnomalyStatus.RESOLVED
    assert stored[fresh].status is AnomalyStatus.ACTIVE


async def test_a_late_batch_never_expires_a_newer_episode(db_session_factory: Any) -> None:
    """A stale X must keep failing loudly; it may not kill the newer Y that replaced it."""
    market_id = await seed_market(db_session_factory, "sup-e", "BTCUSDT")
    newer, stale = uuid7(), uuid7()
    await _write(db_session_factory, _state(market_id, detected_at=NOW, observed_at=NOW), newer)

    older = NOW - timedelta(hours=2)
    with pytest.raises(IntegrityError, match="uq_anomalies_active_per_market_type"):
        await _write(
            db_session_factory, _state(market_id, detected_at=older, observed_at=older), stale
        )

    stored = await _rows(db_session_factory, market_id)
    assert list(stored) == [newer]
    assert stored[newer].status is AnomalyStatus.ACTIVE


async def test_supersede_reports_what_it_closed_and_is_idempotent(db_session_factory: Any) -> None:
    market_id = await seed_market(db_session_factory, "sup-f", "BTCUSDT")
    orphan, fresh = uuid7(), uuid7()
    first = NOW - timedelta(hours=5)
    await _write(
        db_session_factory, _state(market_id, detected_at=first, observed_at=first), orphan
    )
    incoming = [
        row_builders.anomaly_row(
            _state(market_id, detected_at=NOW, observed_at=NOW), anomaly_id=fresh
        )
    ]

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert await supersede_orphan_anomalies(session, incoming) == 1
        assert await supersede_orphan_anomalies(session, incoming) == 0  # nothing left to close

    row = (await _rows(db_session_factory, market_id))[orphan]
    assert row.status is AnomalyStatus.EXPIRED
    assert row.resolved_at == NOW
    assert row.meta["state"]["reason"] == "superseded"
    assert row.meta["state"]["resolved_at"] is not None


async def test_two_active_ids_for_one_pair_in_one_batch_still_fail_loudly(
    db_session_factory: Any,
) -> None:
    """A caller bug the writer must not paper over: both rows claim the same slot."""
    market_id = await seed_market(db_session_factory, "sup-g", "BTCUSDT")
    one, two = uuid7(), uuid7()
    batch = WriteBatch(
        anomalies=[
            row_builders.anomaly_row(
                _state(market_id, detected_at=NOW, observed_at=NOW), anomaly_id=one
            ),
            row_builders.anomaly_row(
                _state(market_id, detected_at=NOW, observed_at=NOW), anomaly_id=two
            ),
        ]
    )
    with pytest.raises(IntegrityError, match="uq_anomalies_active_per_market_type"):
        await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)
    assert await _rows(db_session_factory, market_id) == {}


async def test_only_the_pair_with_an_orphan_is_touched(db_session_factory: Any) -> None:
    """Isolation: another market, and another type in the same market, stay ``active``."""
    market_a = await seed_market(db_session_factory, "sup-h", "BTCUSDT")
    market_b = await seed_market(db_session_factory, "sup-i", "BTCUSDT")
    first = NOW - timedelta(hours=5)
    orphan_a, other_type, other_market, fresh = uuid7(), uuid7(), uuid7(), uuid7()
    seed = WriteBatch(
        anomalies=[
            row_builders.anomaly_row(
                _state(market_a, detected_at=first, observed_at=first), anomaly_id=orphan_a
            ),
            row_builders.anomaly_row(
                _state(
                    market_a, detected_at=first, observed_at=first, kind=AnomalyType.VOLUME_SPIKE
                ),
                anomaly_id=other_type,
            ),
            row_builders.anomaly_row(
                _state(market_b, detected_at=first, observed_at=first), anomaly_id=other_market
            ),
        ]
    )
    await flush_batch(db_session_factory, cast("Any", NullRedis()), seed, now=NOW)

    # One batch, two pairs: market_a/MOMENTUM_SHIFT has an orphan, market_b's pair is
    # simply updated by its own id (nothing to supersede there).
    batch = WriteBatch(
        anomalies=[
            row_builders.anomaly_row(
                _state(market_a, detected_at=NOW, observed_at=NOW), anomaly_id=fresh
            ),
            row_builders.anomaly_row(
                _state(market_b, detected_at=first, observed_at=NOW), anomaly_id=other_market
            ),
        ]
    )
    await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    stored_a = await _rows(db_session_factory, market_a)
    assert stored_a[orphan_a].status is AnomalyStatus.EXPIRED
    assert stored_a[fresh].status is AnomalyStatus.ACTIVE
    assert stored_a[other_type].status is AnomalyStatus.ACTIVE
    assert "superseded_by" not in stored_a[other_type].meta
    stored_b = await _rows(db_session_factory, market_b)
    assert stored_b[other_market].status is AnomalyStatus.ACTIVE
    assert "superseded_by" not in stored_b[other_market].meta


async def test_resolved_at_in_metadata_is_utc_and_the_previous_reason_survives(
    db_session_factory: Any,
) -> None:
    market_id = await seed_market(db_session_factory, "sup-j", "BTCUSDT")
    orphan, fresh = uuid7(), uuid7()
    first = NOW - timedelta(hours=5)
    await _write(
        db_session_factory,
        _state(market_id, detected_at=first, observed_at=first, reason="stale"),
        orphan,
    )
    incoming = [
        row_builders.anomaly_row(
            _state(market_id, detected_at=NOW, observed_at=NOW), anomaly_id=fresh
        )
    ]

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("SET LOCAL TIME ZONE 'America/Sao_Paulo'"))
        assert await supersede_orphan_anomalies(session, incoming) == 1

    state = (await _rows(db_session_factory, market_id))[orphan].meta["state"]
    assert state["resolved_at"] == "2026-09-30T13:36:00.000000+00:00"
    assert datetime.fromisoformat(state["resolved_at"]) == NOW
    assert state["reason"] == "superseded"
    assert state["previous_reason"] == "stale"


async def test_an_equal_detected_at_is_not_superseded_and_fails_loudly(
    db_session_factory: Any,
) -> None:
    """Documents the boundary: ``old.detected_at < incoming.at`` is strict.

    Two active episodes of one pair born at the same instant cannot be ordered, so
    neither may close the other; the writer leaves the index to refuse (no
    behaviour change -- this pins it).
    """
    market_id = await seed_market(db_session_factory, "sup-k", "BTCUSDT")
    existing, rival = uuid7(), uuid7()
    await _write(db_session_factory, _state(market_id, detected_at=NOW, observed_at=NOW), existing)

    with pytest.raises(IntegrityError, match="uq_anomalies_active_per_market_type"):
        await _write(db_session_factory, _state(market_id, detected_at=NOW, observed_at=NOW), rival)

    stored = await _rows(db_session_factory, market_id)
    assert list(stored) == [existing]
    assert stored[existing].status is AnomalyStatus.ACTIVE
