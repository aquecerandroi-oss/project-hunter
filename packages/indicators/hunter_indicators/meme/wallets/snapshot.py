"""The daily ranking snapshot and the rule for which one is in force (§2.1).

A snapshot of day D is cut at ``D 00:00 UTC``, written once and immutable,
with ``published_at``. A decision at instant ``t`` reads the most recent
snapshot with ``published_at ≤ t`` **and** ``cut ≤ t``; between 00:00 and the
publication, D−1's is in force. An unpublished snapshot is never in force.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime

from hunter_indicators.meme.wallets.entities import Entities
from hunter_indicators.meme.wallets.metrics import EntityMetrics

__all__ = ["RankRow", "Snapshot", "current_snapshot"]


@dataclass(frozen=True, slots=True)
class RankRow:
    entity: str
    reasons: tuple[str, ...]
    """Every failed eligibility check; empty = eligible."""
    rank: int | None
    followed: bool
    c_pnl_lamports: int
    metrics: EntityMetrics | None = None

    @property
    def eligible(self) -> bool:
        return not self.reasons


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: str
    day: date
    cut: datetime
    published_at: datetime | None
    entities: Entities
    rows: Mapping[str, RankRow]
    manifest: Mapping[str, str]

    def row(self, entity: str) -> RankRow | None:
        return self.rows.get(entity)

    def published(self, at: datetime) -> Snapshot:
        """The same snapshot, stamped once. Re-publishing is refused."""
        if self.published_at is not None:
            raise ValueError("a snapshot is published once")
        if at < self.cut:
            raise ValueError("a snapshot cannot be published before its cut")
        return replace(self, published_at=at)


def current_snapshot(snapshots: Iterable[Snapshot], t: datetime) -> Snapshot | None:
    """The snapshot in force at ``t``: latest ``published_at ≤ t`` with ``cut ≤ t``."""
    live = [
        s for s in snapshots if s.published_at is not None and s.published_at <= t and s.cut <= t
    ]
    return max(live, key=lambda s: (s.cut, s.published_at or s.cut), default=None)
