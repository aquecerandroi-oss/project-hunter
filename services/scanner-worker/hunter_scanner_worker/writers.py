"""The statements. One function per table, each saying why it is shaped that way.

Split out of ``persist.py`` for the 350-line budget, and the seam is meaningful:
this module knows SQL and nothing about cycles, while ``persist.py`` knows the
transaction and nothing about column lists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import orjson
from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import ProgrammingError

from hunter_core.db.models.analysis import (
    Anomaly,
    FeatureSnapshot,
    MarketRegimeRow,
    Opportunity,
    OpportunityHistory,
)
from hunter_core.domain.types import uuid7
from hunter_core.logging import get_logger
from hunter_indicators.baselines import insert_revisions

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.baselines import BaselineRevision
    from hunter_scanner_worker.persist import WriteBatch

logger = get_logger(__name__)

__all__ = [
    "dedupe",
    "probe_baseline_lock",
    "surviving_baselines",
    "touch_episodes",
    "write_anomalies",
    "write_history",
    "write_opportunities",
    "write_regime",
    "write_revisions",
    "write_snapshots",
]


_LOCKED = text("SELECT id FROM feature_baselines WHERE id = ANY(:ids) FOR SHARE")
_UNLOCKED = text("SELECT id FROM feature_baselines WHERE id = ANY(:ids)")

_lock_denied = False
"""Whether this database refuses the row lock. Decided **once, at startup**
(:func:`probe_baseline_lock`) and never inside a batch: a statement that fails
on privilege aborts the transaction it is in, so discovering this lazily would
cost a whole cycle of writes to learn a fact that never changes."""


async def probe_baseline_lock(session: AsyncSession) -> bool:
    """Find out whether ``SELECT ... FOR SHARE`` is permitted here.

    ``0003`` granted ``hunter_worker`` ``SELECT, INSERT, DELETE`` on
    ``feature_baselines`` and deliberately no ``UPDATE``, while PostgreSQL
    requires ``UPDATE`` for a row lock: the locked statement failed with
    *permission denied* and the retention protocol of ``docs/DATABASE.md``
    section 17.2 -- which has the writer take ``FOR SHARE`` before referencing a
    revision -- could not be honoured as written. That was T2.5's BUG-1, and
    **``0005_baseline_lock_grant`` fixed it**: the grant is in, immutability
    stays where it always was (the ``feature_baselines_immutable`` trigger
    refuses every ``UPDATE`` for every role, owner included).

    The probe stays, because it answers a question about *this* deployment and
    not about the migration history: a database still at ``0004`` degrades to a
    plain existence check with an ``error`` in the log instead of losing a batch
    to a privilege failure inside a transaction.
    """
    global _lock_denied
    try:
        await session.execute(_LOCKED, {"ids": []})
    except ProgrammingError as exc:
        if "permission denied" not in str(exc).lower():
            raise
        _lock_denied = True
        logger.error(
            "scanner_baseline_lock_denied",
            detail=(
                "hunter_worker lacks UPDATE on feature_baselines, so SELECT ... FOR SHARE is "
                "refused; envelopes are still refused when a baseline vanished, but the write "
                "is no longer serialised against a concurrent retention DELETE"
            ),
        )
        return False
    _lock_denied = False
    return True


async def surviving_baselines(session: AsyncSession, ids: set[UUID]) -> set[UUID]:
    """Report which of ``ids`` still exist, locking them when the grant allows.

    Either way the property that protects the score holds: a sample whose
    baseline is gone is not written. What the lock adds -- and what is lost
    without it -- is the serialisation against retention (see
    :func:`probe_baseline_lock`).
    """
    if not ids:
        return set()
    statement = _UNLOCKED if _lock_denied else _LOCKED
    result = await session.execute(statement, {"ids": [str(item) for item in ids]})
    return {UUID(str(row[0])) for row in result}


def dedupe(rows_: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    """Collapse rows that share a conflict key, keeping the **last** one.

    ``ON CONFLICT DO UPDATE`` refuses to touch the same row twice in one
    statement (``CardinalityViolationError``), and one batch legitimately holds
    several evaluations of the same market: the persist cycle flushes once a
    second while the evaluation loop wakes four times, and the snapshot minute is
    only promoted *after* the commit -- so the same closed minute is rebuilt by
    every evaluation until it lands. The last one is kept because it is the one
    computed from the freshest hot state; the earlier ones describe the same
    minute seen less completely.

    Found in the operational proof, as a direct consequence of deferring that
    promotion (which is itself the fix for losing a minute when a batch fails).
    """
    collapsed: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows_:
        collapsed[tuple(row[key] for key in keys)] = row
    return list(collapsed.values())


async def write_snapshots(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    statement = pg_insert(FeatureSnapshot).values(dedupe(rows, "market_id", "ts"))
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["market_id", "ts"],
            set_={
                "feature_set_version": statement.excluded.feature_set_version,
                "features": statement.excluded.features,
            },
        )
    )


async def write_anomalies(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    statement = pg_insert(Anomaly).values(dedupe(rows, "id"))
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["id"],
            # ``excluded`` is keyed by **column** name while ``values()`` above is
            # keyed by ORM attribute, and the two differ for exactly one column:
            # the attribute is ``meta`` because ``metadata`` is taken by
            # SQLAlchemy's own declarative namespace.
            set_={
                key: statement.excluded[key]
                for key in (
                    "severity",
                    "confidence",
                    "resolved_at",
                    "status",
                    "evaluation_state",
                    "baseline",
                    "current_value",
                    "deviation",
                    "unit",
                    "detector_version",
                    "metadata",
                )
            },
        )
    )


async def write_opportunities(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    statement = pg_insert(Opportunity).values(dedupe(rows, "id"))
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                key: statement.excluded[key]
                for key in (
                    "direction",
                    "score",
                    "confidence",
                    "peak_score",
                    "status",
                    "decomposition",
                    "weights_version",
                    "regime_id",
                    "anomaly_ids",
                    "stage",
                    "explanation",
                    "below_40_since",
                    "feature_snapshot",
                    "last_updated_at",
                    "expired_at",
                )
            },
        )
    )


async def touch_episodes(session: AsyncSession, rows_: list[dict[str, Any]]) -> None:
    """Move only the durable counters of an open episode, by identity."""
    for row in rows_:
        await session.execute(
            update(Opportunity)
            .where(Opportunity.id == row["id"])
            .values(
                below_40_since=row["below_40_since"],
                status=row["status"],
                expired_at=row["expired_at"],
                last_updated_at=row["last_updated_at"],
            )
        )


async def write_history(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    await session.execute(
        pg_insert(OpportunityHistory)
        .values(dedupe(rows, "opportunity_id", "ts"))
        .on_conflict_do_nothing(index_elements=["opportunity_id", "ts"])
    )


async def write_regime(session: AsyncSession, batch: WriteBatch) -> None:
    if batch.regime_close is not None:
        regime_id, end_time = batch.regime_close
        await session.execute(
            text("UPDATE market_regimes SET end_time = :end_time WHERE id = :id"),
            {"end_time": end_time, "id": str(regime_id)},
        )
    if batch.regime_open is not None:
        await session.execute(pg_insert(MarketRegimeRow).values([batch.regime_open]))
    if batch.regime_touch is not None:
        regime_id, supporting = batch.regime_touch
        await session.execute(
            text(
                "UPDATE market_regimes SET supporting_features = CAST(:features AS jsonb) "
                "WHERE id = :id"
            ),
            {"features": _json(supporting), "id": str(regime_id)},
        )


def _json(value: dict[str, Any]) -> str:

    return orjson.dumps(value).decode()


async def write_revisions(session: AsyncSession, revisions: list[BaselineRevision]) -> None:
    """Append-only baseline revisions, inside the same transaction as everything else."""
    if not revisions:
        return

    ids = [uuid7() for _ in revisions]
    await session.execute(insert_revisions(revisions, ids=ids))
