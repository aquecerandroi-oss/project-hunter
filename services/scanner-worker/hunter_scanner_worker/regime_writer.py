"""One ``market_regimes`` row per hour, idempotent on ``(exchange, ts)``.

Three decisions, each of them a fork somebody would otherwise take differently.

**The row is closed, always.** ``start_time = ts``, ``end_time = ts + 1h``. The
partial index ``uq_market_regimes_open_per_scope`` forbids a second *open* row
per scope, and the live ``regime_v0`` engine is the one that keeps an open row
(on ``scope = global``). An hourly series that left its newest row open would be
racing that invariant every hour for nothing: the reader of this series joins by
interval containment, not by "the open one".

**The scope is ``btc``, and that is a decision, not a detail.** ``regime_v0``
owns ``global`` with open-ended intervals; writing hourly rows into the same
scope would make two classifiers produce overlapping intervals in one series, and
``hunter_strategy_worker.repo.regime_at`` — which orders by ``start_time`` — would
silently pick whichever one moved last. ``btc`` was unused (nothing but an API
test ever wrote it) and is what this engine actually measures: BTC structure,
with the universe's breadth and funding as context. Readers select on
``classifier_version`` as well, so the two engines never merge by accident.

**Idempotency without a unique index.** ``market_regimes`` has no ``exchange``
column and no unique constraint on ``(scope, start_time)``, so the key is
enforced by the job: look the hour up (scope + version + exchange, the exchange
living in ``supporting_features`` until the column exists), compare the digest of
what we would write, and then do nothing, update in place, or insert. Update and
not delete-then-insert because ``agent_signals.regime_id``,
``trade_proposals.regime_id`` and ``paper_trades.regime_id`` point at these ids
with ``ON DELETE SET NULL``: deleting a row to rewrite it would quietly erase the
regime of every decision that referenced it. The race that a unique index would
close (two producers, same hour, same second) is closed by the producer lock
instead, and the missing index is on record — ``.claude/state/brief-T3.43-db-market-regimes-hourly.md``.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.analysis import MarketRegimeRow
from hunter_core.domain.enums import RegimeScope
from hunter_core.domain.types import uuid7
from hunter_core.strategies.canonical import canonical_json
from hunter_scanner_worker.rows import jsonable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.regime import HourlyThresholds, RegimeSnapshot

INSERTED = "inserted"
UPDATED = "updated"
UNCHANGED = "unchanged"

HOURLY_SCOPE = RegimeScope.BTC
"""The scope this engine owns. ``regime_v0`` owns ``global``; see the module
docstring for why they may not share one."""

__all__ = ["HOURLY_SCOPE", "INSERTED", "UNCHANGED", "UPDATED", "existing_hours", "write_snapshot"]

_EXISTING = text(
    "SELECT id, start_time, supporting_features ->> 'digest' AS digest "
    "  FROM market_regimes "
    " WHERE scope = CAST(:scope AS regime_scope)"
    "   AND classifier_version = :version"
    "   AND supporting_features ->> 'exchange' = :exchange"
    "   AND start_time >= :first AND start_time <= :last"
)


def supporting_features(
    snapshot: RegimeSnapshot,
    *,
    exchange: str,
    thresholds: HourlyThresholds,
) -> tuple[dict[str, Any], str]:
    """``(the JSONB the row holds, its digest)``.

    The digest covers the snapshot, the exchange and every threshold — and
    **not** ``computed_at``: a rerun of the same hour over the same candles has
    to compare equal, or every pass would rewrite thirty-one days of rows.
    """
    payload: dict[str, Any] = {
        **snapshot.as_wire(),
        "exchange": exchange,
        "thresholds": thresholds.as_wire(),
    }
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()[:32]
    return jsonable({**payload, "digest": digest}), digest


async def existing_hours(
    session: AsyncSession,
    *,
    exchange: str,
    version: str,
    first: datetime,
    last: datetime,
) -> dict[datetime, str | None]:
    """``hour -> digest`` for the rows this producer already wrote in the window."""
    rows = await session.execute(
        _EXISTING,
        {
            "scope": HOURLY_SCOPE.value,
            "version": version,
            "exchange": exchange,
            "first": first,
            "last": last,
        },
    )
    return {row.start_time: row.digest for row in rows}


async def write_snapshot(
    session: AsyncSession,
    snapshot: RegimeSnapshot,
    *,
    exchange: str,
    thresholds: HourlyThresholds,
    known: Mapping[datetime, str | None] | None = None,
) -> str:
    """Insert, update or recognise the row for ``snapshot.ts``. Returns which."""
    features, digest = supporting_features(snapshot, exchange=exchange, thresholds=thresholds)
    if known is not None and known.get(snapshot.ts) == digest:
        return UNCHANGED
    current = (
        await session.execute(
            _EXISTING,
            {
                "scope": HOURLY_SCOPE.value,
                "version": snapshot.version,
                "exchange": exchange,
                "first": snapshot.ts,
                "last": snapshot.ts,
            },
        )
    ).first()
    if current is not None:
        if current.digest == digest:
            return UNCHANGED
        await session.execute(
            text(
                "UPDATE market_regimes SET regime = CAST(:regime AS market_regime), "
                "confidence = :confidence, end_time = :end_time, "
                "supporting_features = CAST(:features AS jsonb) WHERE id = :id"
            ),
            {
                "regime": snapshot.regime.value,
                "confidence": snapshot.confidence,
                "end_time": snapshot.valid_until,
                "features": canonical_json(features).decode(),
                "id": str(current.id),
            },
        )
        return UPDATED
    await session.execute(
        pg_insert(MarketRegimeRow).values(
            [
                {
                    "id": uuid7(),
                    "scope": HOURLY_SCOPE,
                    "regime": snapshot.regime,
                    "confidence": snapshot.confidence,
                    "start_time": snapshot.ts,
                    "end_time": snapshot.valid_until,
                    "supporting_features": features,
                    "classifier_version": snapshot.version,
                }
            ]
        )
    )
    return INSERTED
