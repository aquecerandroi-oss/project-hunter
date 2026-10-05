"""Rollback -> retry against the real unique index.

The unit tests in ``test_flush_lane.py`` prove the lane *keeps* a failed batch; this
one proves what the retry does to the table. Production, 30/09 and 02/10: the
``RESOLVE``/``EXPIRE`` of row X was lost with a discarded batch and the next ``OPEN``
(Y) was refused by the partial unique index for good. Here the batch ``[X resolved,
Y open]`` fails *after* its anomaly statement, inside the transaction, so Postgres
rolls it back; the lane retries the same batch and the table ends with X resolved
and exactly one active row -- without the supersede reconciliation having to
intervene (``scanner_anomalies_superseded`` would mean the retry was not enough).

Real Postgres (``integration`` marker; skipped when Docker is unreachable).
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from hunter_core.domain.enums import AnomalyStatus
from hunter_core.domain.types import uuid7
from hunter_scanner_worker import rows as row_builders
from hunter_scanner_worker import writers
from hunter_scanner_worker.cycle_health import CycleHealth
from hunter_scanner_worker.flush_lane import FlushLane

from . import test_anomaly_supersede as seeding
from .db_helpers import seed_market

_rows = seeding._rows  # pyright: ignore[reportPrivateUsage]
_state = seeding._state  # pyright: ignore[reportPrivateUsage]
_write = seeding._write  # pyright: ignore[reportPrivateUsage]
NOW, NullRedis = seeding.NOW, seeding.NullRedis

pytestmark = pytest.mark.integration


async def test_a_rolled_back_batch_is_retried_whole_and_leaves_one_active_row(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_id = await seed_market(db_session_factory, "retry-a", "BTCUSDT")
    old, fresh = uuid7(), uuid7()
    first = NOW.replace(hour=11)
    await _write(db_session_factory, _state(market_id, detected_at=first, observed_at=first), old)

    resolved = _state(market_id, detected_at=first, observed_at=NOW, status=AnomalyStatus.RESOLVED)
    opened = _state(market_id, detected_at=NOW, observed_at=NOW)
    cycle = CycleHealth()
    lane = FlushLane(db_session_factory, cast("Any", NullRedis()), cycle)
    lane.batch.anomalies.extend(
        [
            row_builders.anomaly_row(resolved, anomaly_id=old),
            row_builders.anomaly_row(opened, anomaly_id=fresh),
        ]
    )

    real_write_regime = writers.write_regime
    attempts: list[int] = []

    async def failing_once(session: Any, batch: Any) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("connection reset after the anomaly statement")
        await real_write_regime(session, batch)

    monkeypatch.setattr(writers, "write_regime", failing_once)

    assert await lane.flush(now=NOW) is False
    stored = await _rows(db_session_factory, market_id)
    assert stored[old].status is AnomalyStatus.ACTIVE, "the failed attempt was rolled back whole"
    assert fresh not in stored

    assert await lane.flush(now=NOW) is True

    stored = await _rows(db_session_factory, market_id)
    assert stored[old].status is AnomalyStatus.RESOLVED, "X keeps its own verdict"
    assert "superseded_by" not in stored[old].meta, "the retry sufficed; nothing was reconciled"
    assert stored[fresh].status is AnomalyStatus.ACTIVE
    assert [row.status for row in stored.values()].count(AnomalyStatus.ACTIVE) == 1
    assert cycle.failures == 0 and cycle.failures_total == 1
    assert cycle.last_commit_at is not None


async def test_a_stale_watchdog_touch_never_overwrites_a_newer_evaluation(
    db_session_factory: Any,
) -> None:
    """The touches are applied after the opportunities in one flush; a retained batch
    can hold one collected *before* an evaluation that has since moved the episode."""
    from decimal import Decimal

    from sqlalchemy import select

    from hunter_core.db.models.analysis import Opportunity
    from hunter_core.db.session import role_session
    from hunter_core.domain.enums import OpportunityStatus
    from hunter_scanner_worker.persist import WriteBatch, flush_batch

    from .test_persistence import (
        _opportunity_row,  # pyright: ignore[reportPrivateUsage]
    )

    market_id = await seed_market(db_session_factory, "retry-b", "BTCUSDT")
    opportunity_id = uuid7()
    older, newer = NOW, NOW.replace(minute=40)
    hot = _opportunity_row(
        market_id,
        opportunity_id,
        status=OpportunityStatus.HOT,
        score=Decimal("81.00"),
        last_updated_at=newer,
    )
    stale_touch = {
        "id": opportunity_id,
        "market_id": market_id,
        "below_40_since": None,
        "status": OpportunityStatus.NORMAL,
        "expired_at": None,
        "last_updated_at": older,
    }
    batch = WriteBatch(opportunities=[hot], episode_touches=[stale_touch])

    await flush_batch(db_session_factory, cast("Any", NullRedis()), batch, now=newer)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        stored = (
            await session.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
        ).scalar_one()
    assert stored.status is OpportunityStatus.HOT
    assert stored.last_updated_at == newer
