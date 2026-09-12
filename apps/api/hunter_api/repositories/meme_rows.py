"""Row shapes and mapping helpers for ``repositories/meme.py`` — split out on
its own so that file stays under the 350-line budget. Field names follow the
frozen contract (``.claude/state/notes-T4.2.md`` §"contrato").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

__all__ = [
    "MemeFeatureRow",
    "MemeGapRow",
    "MemeSnapshotRow",
    "MemeTokenRow",
    "row_from_token_only",
    "row_from_view",
]


@dataclass(frozen=True, slots=True)
class MemeTokenRow:
    mint: str
    name: str | None
    symbol: str | None
    creator: str | None
    created_at: datetime | None
    mayhem_enabled: bool | None
    mayhem_state: str | None
    completed_at: datetime | None
    migrated_at: datetime | None
    mcap_sol: Decimal | None
    curve_progress_pct: Decimal | None
    snapshot_observed_at: datetime | None
    snapshot_source: str | None


@dataclass(frozen=True, slots=True)
class MemeSnapshotRow:
    observed_at: datetime
    source: str
    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal
    real_sol_reserves: Decimal
    real_token_reserves: Decimal
    complete: bool
    mcap_sol: Decimal | None


@dataclass(frozen=True, slots=True)
class MemeFeatureRow:
    end_time: datetime
    age_minutes: int | None
    curve_progress_pct: Decimal | None
    progress_reason: str | None
    mcap_sol: Decimal | None
    curve_reason: str | None
    unique_buyers: int | None
    unique_buyers_reason: str | None
    buy_sell_ratio: Decimal | None
    buy_sell_ratio_reason: str | None
    top10_share: Decimal | None
    top10_share_reason: str | None
    creator_sold: bool | None
    creator_sold_reason: str | None
    coverage: Decimal
    features_version: str


@dataclass(frozen=True, slots=True)
class MemeGapRow:
    id: uuid.UUID
    stream: str
    mint: str | None
    gap_start: datetime
    gap_end: datetime
    detected_at: datetime
    reason: str | None
    generation: int | None
    detail: dict[str, Any] | None


def _optional(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


def row_from_view(r: RowMapping) -> MemeTokenRow:
    return MemeTokenRow(
        mint=r["mint"],
        name=r["name"],
        symbol=r["symbol"],
        creator=r["creator"],
        created_at=_optional(r["token_created_at"]),
        mayhem_enabled=r["mayhem_enabled"],
        mayhem_state=r["mayhem_state"],
        completed_at=_optional(r["completed_at"]),
        migrated_at=_optional(r["migrated_at"]),
        mcap_sol=r["mcap_sol"],
        curve_progress_pct=r["curve_progress_pct"],
        snapshot_observed_at=_optional(r["snapshot_observed_at"]),
        snapshot_source=r["snapshot_source"],
    )


def row_from_token_only(r: RowMapping) -> MemeTokenRow:
    """A mint the collector has recorded (``meme_tokens``) but never computed
    a ``meme_features_1m`` row for yet -- every curve/progress field is an
    honest ``None``, never a fabricated zero."""
    return MemeTokenRow(
        mint=r["mint"],
        name=r["name"],
        symbol=r["symbol"],
        creator=r["creator"],
        created_at=_optional(r["created_at"]),
        mayhem_enabled=r["mayhem_enabled"],
        mayhem_state=r["mayhem_state"],
        completed_at=_optional(r["completed_at"]),
        migrated_at=_optional(r["migrated_at"]),
        mcap_sol=None,
        curve_progress_pct=None,
        snapshot_observed_at=None,
        snapshot_source=None,
    )
