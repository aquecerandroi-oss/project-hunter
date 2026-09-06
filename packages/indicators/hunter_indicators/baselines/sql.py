"""The SQL adapter of :class:`BaselineStore` — two statements, no cleverness.

``feature_baselines`` is an append-only archive guarded by the
``feature_baselines_immutable`` trigger (``docs/DATABASE.md`` §17.2), so this
adapter can only do two things: ``INSERT ... ON CONFLICT DO NOTHING`` and read
the current projection under the causal cut. There is no ``UPDATE`` path to
write, and no ``DELETE`` — retention is T2.8's, and it has to declare itself with
``SET LOCAL app.baseline_retention``.

Both halves of the cut and the version compatibility go **into the WHERE**,
before the ``DISTINCT ON`` chooses: filtering after selecting would let a
revision that is not admissible yet hide an older one that is (Astra, T2.3 design
review, item 1). The ordering mirrors ``StoredBaseline.selection_key`` exactly —
Postgres compares ``uuid`` byte-wise and Python compares ``UUID.int``, which is
the same order, so the two stores cannot disagree about which revision wins.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import Select, Table, and_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.dml import ReturningInsert

from hunter_core.db.models.analysis_baselines import FeatureBaseline
from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_core.domain.types import ensure_utc, uuid7
from hunter_indicators.baselines.projection import BaselineCut
from hunter_indicators.baselines.revision import (
    ALGO_VERSION,
    BaselineKey,
    BaselineRevision,
    StoredBaseline,
)
from hunter_indicators.baselines.store import BaselineRequest

_REVISION_CONSTRAINT = "uq_feature_baselines_revision"

_TABLE: Table = cast("Table", FeatureBaseline.__table__)


def select_projection(
    requests: Sequence[BaselineRequest],
    *,
    cut: BaselineCut,
    algo_version: str,
    sampling: BaselineSampling,
) -> Select[Any]:
    """The newest admissible revision of each requested bucket, one row per bucket.

    The ``DISTINCT ON`` key names ``feature_version`` and ``algo_version`` as well:
    ``InMemoryBaselineStore._candidates`` matches on both, so leaving them out
    would make one batch asking for two versions of a feature return two rows in
    memory and one from Postgres — the same projection disagreeing with itself
    depending on which adapter the caller happens to hold.
    """
    buckets = [
        (request.market_id, request.feature, request.feature_version, request.hour_of_day)
        for request in requests
    ]
    return (
        select(_TABLE)
        .where(
            and_(
                tuple_(
                    _TABLE.c.market_id,
                    _TABLE.c.feature,
                    _TABLE.c.feature_version,
                    _TABLE.c.hour_of_day,
                ).in_(buckets),
                _TABLE.c.algo_version == algo_version,
                _TABLE.c.sampling == sampling,
                _TABLE.c.available_at <= cut.as_of,
                _TABLE.c.window_end < cut.observation_ts,
            )
        )
        .distinct(
            _TABLE.c.market_id,
            _TABLE.c.feature,
            _TABLE.c.feature_version,
            _TABLE.c.algo_version,
            _TABLE.c.hour_of_day,
        )
        .order_by(
            _TABLE.c.market_id,
            _TABLE.c.feature,
            _TABLE.c.feature_version,
            _TABLE.c.algo_version,
            _TABLE.c.hour_of_day,
            _TABLE.c.available_at.desc(),
            _TABLE.c.window_end.desc(),
            _TABLE.c.id.desc(),
        )
    )


def insert_revisions(
    revisions: Sequence[BaselineRevision], *, ids: Sequence[uuid.UUID]
) -> ReturningInsert[Any]:
    """``INSERT ... ON CONFLICT DO NOTHING`` over the revision constraint.

    A retry of the same refresh job carries the same ``input_fingerprint`` and
    collides; a recomputation over a changed sample carries a different one and
    lands as a new revision. Neither path ever rewrites a published number.
    """
    rows = [
        {"id": row_id, **revision.as_row()} for row_id, revision in zip(ids, revisions, strict=True)
    ]
    return (
        insert(_TABLE)
        .values(rows)
        .on_conflict_do_nothing(constraint=_REVISION_CONSTRAINT)
        .returning(_TABLE.c.id, _TABLE.c.input_fingerprint)
    )


def _revision_from_row(row: Mapping[Any, Any]) -> StoredBaseline:
    return StoredBaseline(
        baseline_id=row["id"],
        revision=BaselineRevision(
            key=BaselineKey(
                market_id=row["market_id"],
                feature=row["feature"],
                hour_of_day=int(row["hour_of_day"]),
            ),
            feature_version=int(row["feature_version"]),
            algo_version=row["algo_version"],
            sampling=BaselineSampling(row["sampling"]),
            source=BaselineSource(row["source"]),
            window_start=ensure_utc(row["window_start"]),
            window_end=ensure_utc(row["window_end"]),
            available_at=ensure_utc(row["available_at"]),
            median=row["median"],
            mad=row["mad"],
            sample_size=int(row["sample_size"]),
            expected_size=int(row["expected_size"]),
            distinct_days=int(row["distinct_days"]),
            coverage=row["coverage"],
            input_fingerprint=row["input_fingerprint"],
        ),
    )


class SqlBaselineStore:
    """:class:`BaselineStore` over one ``AsyncConnection``. Never calls an exchange."""

    def __init__(
        self,
        connection: AsyncConnection,
        *,
        algo_version: str = ALGO_VERSION,
        sampling: BaselineSampling = BaselineSampling.PER_MINUTE,
    ) -> None:
        self._connection = connection
        self.algo_version = algo_version
        self.sampling = sampling

    async def append(self, revisions: Sequence[BaselineRevision]) -> tuple[StoredBaseline, ...]:
        """Insert and return **what is stored**, resolving collisions by fingerprint.

        A collision returns the row that is already in the archive, rebuilt from
        the database — not the revision this call attempted. The two differ in
        exactly the field that matters: ``available_at`` is not part of the
        identity, so a retry an hour later carries a later one, and announcing it
        would make a projection reject a baseline that had in fact been usable
        since the original publication (Astra, T2.3 diff review, must-fix 3).
        """
        if not revisions:
            return ()
        ids = [uuid7() for _ in revisions]
        result = await self._connection.execute(insert_revisions(revisions, ids=ids))
        by_fingerprint: dict[str, StoredBaseline] = {}
        inserted = {row["input_fingerprint"]: row["id"] for row in result.mappings()}
        for revision in revisions:
            row_id = inserted.get(revision.input_fingerprint)
            if row_id is not None:
                by_fingerprint[revision.input_fingerprint] = StoredBaseline(
                    baseline_id=row_id, revision=revision
                )
        missing = [
            revision.input_fingerprint
            for revision in revisions
            if revision.input_fingerprint not in by_fingerprint
        ]
        if missing:
            existing = await self._connection.execute(
                select(_TABLE).where(_TABLE.c.input_fingerprint.in_(missing))
            )
            for row in existing.mappings():
                entry = _revision_from_row(row)
                by_fingerprint[entry.revision.input_fingerprint] = entry
        stored: list[StoredBaseline] = []
        for revision in revisions:
            entry = by_fingerprint.get(revision.input_fingerprint)
            if entry is None:
                raise RuntimeError(
                    f"baseline revision {revision.key} was neither inserted nor found: "
                    "an envelope must never name an id that is not in the archive"
                )
            stored.append(entry)
        return tuple(stored)

    async def load(
        self, requests: Sequence[BaselineRequest], *, cut: BaselineCut
    ) -> tuple[StoredBaseline, ...]:
        if not requests:
            return ()
        result = await self._connection.execute(
            select_projection(
                requests,
                cut=cut,
                algo_version=self.algo_version,
                sampling=self.sampling,
            )
        )
        return tuple(_revision_from_row(row) for row in result.mappings())

    async def load_ids(self, ids: Sequence[uuid.UUID]) -> tuple[StoredBaseline, ...]:
        if not ids:
            return ()
        result = await self._connection.execute(select(_TABLE).where(_TABLE.c.id.in_(list(ids))))
        return tuple(_revision_from_row(row) for row in result.mappings())


__all__ = ["SqlBaselineStore", "insert_revisions", "select_projection"]
