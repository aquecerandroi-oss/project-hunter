"""One transaction, against a real Postgres. Rows and events, or neither.

Testcontainers because the three things being proved only exist in a database:
the partial unique index that keys episode identity, the biconditional CHECK
between ``status`` and ``expired_at``, and the ``FOR SHARE`` that serialises an
envelope against retention. A fake session would compile the statements and
prove none of it.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import delete, func, select

from hunter_core.db.models.analysis import (
    Anomaly,
    FeatureSnapshot,
    Opportunity,
    OpportunityHistory,
)
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)
from hunter_core.domain.types import uuid7
from hunter_core.events.streams import Streams
from hunter_indicators.anomalies import AnomalyDirection, AnomalyState
from hunter_scanner_worker import rows as row_builders
from hunter_scanner_worker.persist import WriteBatch, flush_batch
from hunter_scanner_worker.repo import load_open_anomalies, load_open_episodes

from .db_helpers import seed_market

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


class NullRedis:
    """The batch acks through Redis; nothing here has anything to ack."""

    async def sadd(self, *args: Any, **kwargs: Any) -> int:
        return 0

    async def expire(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def xack(self, *args: Any, **kwargs: Any) -> int:
        return 0


def _anomaly_state(market_id: uuid.UUID, *, severity: str = "82.00") -> AnomalyState:
    return AnomalyState(
        market_id=market_id,
        type=AnomalyType.VOLUME_SPIKE,
        status=AnomalyStatus.ACTIVE,
        evaluation_state=AnomalyEvaluationState.OK,
        detected_at=NOW - timedelta(minutes=5),
        observation_ts=NOW,
        severity=Decimal(severity),
        confidence=Decimal("0.9100"),
        baseline=Decimal("1.0000000000"),
        current_value=Decimal("4.7000000000"),
        deviation=Decimal("6.1000"),
        direction=AnomalyDirection.UP,
        unit="ratio",
        detector_version="volume_spike_v1",
        normalization_version="mad_piecewise_v1@v2",
        below_hold_since=None,
        below_hold_readings=0,
    )


def _opportunity_row(market_id: uuid.UUID, opportunity_id: uuid.UUID, **overrides: Any) -> Any:
    row: dict[str, Any] = {
        "id": opportunity_id,
        "market_id": market_id,
        "direction": TradeDirection.LONG,
        "score": Decimal("72.50"),
        "confidence": Decimal("0.9603"),
        "peak_score": Decimal("72.50"),
        "status": OpportunityStatus.WATCHING,
        "decomposition": {"score": "72.50"},
        "weights_version": "v2",
        "regime_id": None,
        "anomaly_ids": [],
        "stage": OpportunityStage.DEVELOPING,
        "explanation": {"frases": []},
        "below_40_since": None,
        "feature_snapshot": {"features": {"values": {"atr_14_pct": {"value": "0.004"}}}},
        "first_seen_at": NOW,
        "last_updated_at": NOW,
        "expired_at": None,
    }
    row.update(overrides)
    return row


async def _clear(factory: Any) -> None:
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(delete(OutboxEvent))


async def test_rows_and_the_events_that_describe_them_commit_together(
    db_session_factory: Any,
) -> None:
    market_id = await seed_market(db_session_factory, "scan-a", "BTCUSDT")
    await _clear(db_session_factory)
    opportunity_id = uuid7()
    anomaly_id = uuid7()
    state = _anomaly_state(market_id)
    batch = WriteBatch(
        snapshots=[
            {
                "market_id": market_id,
                "ts": NOW,
                "feature_set_version": "abc",
                "features": {"values": {}},
            }
        ],
        anomalies=[row_builders.anomaly_row(state, anomaly_id=anomaly_id)],
        opportunities=[_opportunity_row(market_id, opportunity_id)],
    )
    from hunter_core.events.outbox import build_envelope, event_id_for

    batch.events.append(
        build_envelope(
            Streams.ANOMALIES_DETECTED,
            event_id_for(Streams.ANOMALIES_DETECTED, anomaly_id, NOW, "open"),
            row_builders.anomaly_event_payload(state, anomaly_id=anomaly_id, action="open"),
            producer="scanner-worker@test",
            key="scan-a:BTCUSDT",
            ts=NOW,
        )
    )

    await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(FeatureSnapshot)
                .where(FeatureSnapshot.market_id == market_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(Anomaly).where(Anomaly.id == anomaly_id)
            )
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


async def test_replaying_the_same_batch_writes_nothing_twice(db_session_factory: Any) -> None:
    market_id = await seed_market(db_session_factory, "scan-b", "BTCUSDT")
    await _clear(db_session_factory)
    opportunity_id = uuid7()
    anomaly_id = uuid7()
    state = _anomaly_state(market_id)

    def make_batch() -> WriteBatch:
        from hunter_core.events.outbox import build_envelope, event_id_for

        batch = WriteBatch(
            snapshots=[
                {
                    "market_id": market_id,
                    "ts": NOW,
                    "feature_set_version": "abc",
                    "features": {"values": {}},
                }
            ],
            anomalies=[row_builders.anomaly_row(state, anomaly_id=anomaly_id)],
            opportunities=[_opportunity_row(market_id, opportunity_id)],
            history=[
                {
                    "opportunity_id": opportunity_id,
                    "ts": NOW,
                    "score": Decimal("72.50"),
                    "confidence": Decimal("0.9603"),
                    "status": OpportunityStatus.WATCHING,
                    "stage": OpportunityStage.DEVELOPING,
                    "decomposition": {},
                    "envelope": {},
                }
            ],
        )
        batch.events.append(
            build_envelope(
                Streams.OPPORTUNITIES_UPDATED,
                event_id_for(Streams.OPPORTUNITIES_UPDATED, opportunity_id, NOW, "open"),
                {"opportunity_id": str(opportunity_id)},
                producer="scanner-worker@test",
                key="scan-b:BTCUSDT",
                ts=NOW,
            )
        )
        return batch

    await flush_batch(db_session_factory, cast("Any", NullRedis()), make_batch(), now=NOW)
    await flush_batch(db_session_factory, cast("Any", NullRedis()), make_batch(), now=NOW)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        # A redelivery is a no-op on every table, because every effect has a
        # unique key: the snapshot's (market_id, ts), the row ids, the history
        # sample's (opportunity_id, ts) and the deterministic ``event_id``.
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OpportunityHistory)
                .where(OpportunityHistory.opportunity_id == opportunity_id)
            )
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Opportunity)
                .where(Opportunity.market_id == market_id)
            )
            == 1
        )


async def test_a_vanished_baseline_drops_the_sample_instead_of_stripping_the_id(
    db_session_factory: Any,
) -> None:
    from hunter_scanner_worker.writers import probe_baseline_lock

    market_id = await seed_market(db_session_factory, "scan-c", "BTCUSDT")
    await _clear(db_session_factory)
    # Production probes at startup (``main.run_scanner``); the batch path must
    # never be the thing that discovers a missing privilege, because a failed
    # statement takes the whole transaction with it.
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await probe_baseline_lock(session)
    opportunity_id = uuid7()
    batch = WriteBatch(opportunities=[_opportunity_row(market_id, opportunity_id)])
    ghost = uuid7()
    batch.reference(market_id, [ghost])

    invalidated = await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    assert invalidated == {market_id}
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        # The score was computed against evidence that is no longer there.
        # Writing it with the id quietly removed would store a number nobody can
        # reproduce (DATABASE.md 17.2, item 2).
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Opportunity)
                .where(Opportunity.id == opportunity_id)
            )
            == 0
        )


async def test_an_episode_is_rehydrated_from_the_envelope_it_stored(
    db_session_factory: Any,
) -> None:
    market_id = await seed_market(db_session_factory, "scan-d", "BTCUSDT")
    opportunity_id = uuid7()
    episode_wire = {
        "status": OpportunityStatus.WATCHING.value,
        "first_seen_at": (NOW - timedelta(hours=1)).isoformat(),
        "observation_ts": NOW.isoformat(),
        "score": "45.00",
        "peak_score": "80.00",
        "stage": OpportunityStage.DEVELOPING.value,
        "direction": TradeDirection.LONG.value,
        "confidence": "0.9000",
        "below_floor_since": None,
        "below_floor_readings": 7,
        "expired_at": None,
    }
    batch = WriteBatch(
        opportunities=[
            _opportunity_row(
                market_id,
                opportunity_id,
                feature_snapshot={"state_out": {"status": episode_wire}},
            )
        ]
    )
    await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        episodes = await load_open_episodes(session, [market_id])

    restored = episodes[market_id].episode
    # ``below_floor_readings`` has no column: without the envelope a restart
    # would forget how much of the fifteen minutes was actually observed.
    assert restored.below_floor_readings == 7
    assert restored.peak_score == Decimal("80.00")
    assert episodes[market_id].opportunity_id == opportunity_id


async def test_a_closed_anomaly_is_reloaded_so_an_old_evaluation_cannot_reopen_it(
    db_session_factory: Any,
) -> None:
    market_id = await seed_market(db_session_factory, "scan-e", "BTCUSDT")
    state = _anomaly_state(market_id)
    resolved = dataclasses.replace(state, status=AnomalyStatus.RESOLVED, resolved_at=NOW)
    anomaly_id = uuid7()
    await flush_batch(
        db_session_factory,
        cast("Any", NullRedis()),
        WriteBatch(anomalies=[row_builders.anomaly_row(resolved, anomaly_id=anomaly_id)]),
        now=NOW,
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        loaded = await load_open_anomalies(session, [market_id], since=NOW - timedelta(hours=6))

    stored_id, stored_state = loaded[market_id][AnomalyType.VOLUME_SPIKE]
    assert stored_id == anomaly_id
    assert stored_state.status is AnomalyStatus.RESOLVED
    # The lifecycle's ordering guard needs the closed state: reloading only the
    # active rows would let a redelivered evaluation from before the resolution
    # reopen an anomaly that is over.
    assert stored_state.observation_ts == NOW


async def test_the_row_lock_is_taken_now_that_the_grant_exists(
    db_session_factory: Any,
) -> None:
    """PostgreSQL requires ``UPDATE`` to take any row lock, and ``0003`` granted
    none -- reported by T2.5 as BUG-1, which degraded the writer to a plain
    existence check and gave up the serialisation against a concurrent retention
    ``DELETE``. Migration ``0005_baseline_lock_grant`` added exactly that grant
    (immutability stays in the ``feature_baselines_immutable`` trigger, which
    refuses every ``UPDATE`` for every role), so against a database at head the
    protocol of ``docs/DATABASE.md`` section 17.2 is honoured in full.

    This asserts against a **migrated** database on purpose: the probe is the
    scanner's way of finding out what this deployment allows, and the answer here
    is the answer production gets."""
    from hunter_scanner_worker import writers

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        allowed = await writers.probe_baseline_lock(session)
        assert allowed is True
        # And the statement the batch will actually run is the locking one.
        surviving = await writers.surviving_baselines(session, {uuid7()})

    assert surviving == set()


async def test_a_vanished_baseline_drops_every_effect_of_that_evaluation(
    db_session_factory: Any,
) -> None:
    """Not just the opportunity row.

    Dropping only the opportunity would publish ``opportunities.updated`` for a
    row nobody wrote, keep the anomaly it was scored beside, and run the
    post-commit promotions that tell the next cycle the work is done (Astra,
    T2.5 diff review).
    """
    from hunter_core.events.outbox import build_envelope, event_id_for
    from hunter_scanner_worker.writers import probe_baseline_lock

    market_id = await seed_market(db_session_factory, "scan-f", "BTCUSDT")
    await _clear(db_session_factory)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await probe_baseline_lock(session)

    opportunity_id, anomaly_id, ghost = uuid7(), uuid7(), uuid7()
    promoted: list[str] = []
    batch = WriteBatch(
        opportunities=[_opportunity_row(market_id, opportunity_id)],
        anomalies=[row_builders.anomaly_row(_anomaly_state(market_id), anomaly_id=anomaly_id)],
        history=[
            {
                "opportunity_id": opportunity_id,
                "ts": NOW,
                "score": Decimal("72.50"),
                "confidence": Decimal("0.9603"),
                "status": OpportunityStatus.WATCHING,
                "stage": OpportunityStage.DEVELOPING,
                "decomposition": {},
                "envelope": {},
            }
        ],
    )
    announcement = build_envelope(
        Streams.OPPORTUNITIES_UPDATED,
        event_id_for(Streams.OPPORTUNITIES_UPDATED, opportunity_id, NOW, "open"),
        {"opportunity_id": str(opportunity_id)},
        producer="scanner-worker@test",
        key="scan-f:BTCUSDT",
        ts=NOW,
    )
    batch.events.append(announcement)
    batch.event_market[announcement.event_id] = market_id
    batch.after_commit.append((market_id, lambda: promoted.append("history_mark")))
    batch.reference(market_id, [ghost])

    invalidated = await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    assert invalidated == {market_id}
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Opportunity)
                .where(Opportunity.id == opportunity_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(Anomaly).where(Anomaly.id == anomaly_id)
            )
            == 0
        )
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
    assert promoted == [], "a promotion for a sample that was not written must not run"


async def test_one_batch_with_the_same_minute_twice_commits_once(
    db_session_factory: Any,
) -> None:
    """The persist cycle flushes once a second while the evaluation loop wakes
    four times, and the snapshot minute is only promoted after the commit -- so
    one batch legitimately holds the same closed minute several times.
    ``ON CONFLICT DO UPDATE`` refuses to touch a row twice in one statement, and
    the operational proof hit exactly that (``CardinalityViolationError``)."""
    market_id = await seed_market(db_session_factory, "scan-g", "BTCUSDT")
    opportunity_id = uuid7()
    row = {
        "market_id": market_id,
        "ts": NOW,
        "feature_set_version": "abc",
        "features": {"values": {"n": 1}},
    }
    fresher = {**row, "features": {"values": {"n": 2}}}
    batch = WriteBatch(
        snapshots=[row, fresher],
        opportunities=[
            _opportunity_row(market_id, opportunity_id),
            _opportunity_row(market_id, opportunity_id, score=Decimal("81.00")),
        ],
    )

    await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=NOW)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        stored = await session.scalar(
            select(FeatureSnapshot.features).where(
                FeatureSnapshot.market_id == market_id, FeatureSnapshot.ts == NOW
            )
        )
        score = await session.scalar(
            select(Opportunity.score).where(Opportunity.id == opportunity_id)
        )
    # The **last** one wins: it is the one computed from the freshest hot state.
    assert stored == {"values": {"n": 2}}
    assert score == Decimal("81.00")
