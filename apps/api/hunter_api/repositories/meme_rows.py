"""Row shapes and mapping helpers for ``repositories/meme.py`` — split out on
its own so that file stays under the 350-line budget. Field names follow the
frozen contract (``.claude/state/notes-T4.2.md`` §"contrato").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

__all__ = [
    "MemeFeatureRow",
    "MemeGapRow",
    "MemeGraduationMatrixRow",
    "MemeSnapshotRow",
    "MemeTokenRow",
    "matrix_row_from",
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
    # 0024 (T4.2d): the four completion signals and the denominator's provenance.
    rest_complete_seen_at: datetime | None = None
    curve_filled_seen_at: datetime | None = None
    graduated_board_seen_at: datetime | None = None
    pool_created_at: datetime | None = None
    pool_created_source: str | None = None
    progress_denominator_source: str | None = None


@dataclass(frozen=True, slots=True)
class MemeGraduationMatrixRow:
    """One row of ``meme_graduation_matrix_v1`` (``0024``): a Brasília day."""

    day_brt: date
    mints: int
    completed: int
    rest_complete: int
    curve_filled: int
    graduated_board: int
    pool_created: int
    signals_1: int
    signals_2: int
    signals_3: int
    signals_4: int
    disagree_rest_filled: int
    disagree_rest_board: int
    disagree_rest_pool: int
    disagree_filled_board: int
    disagree_filled_pool: int
    disagree_board_pool: int
    rest_only_unclassified: int


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
    # 0026 (T4.10): defaults so a row read before the columns existed is still a row.
    mcap_slope_5m: Decimal | None = None
    mcap_slope_15m: Decimal | None = None
    high_15m_sol: Decimal | None = None
    low_15m_sol: Decimal | None = None
    breakout_15m: bool | None = None
    support_line_sol: Decimal | None = None
    support_line_slope: Decimal | None = None
    higher_lows: bool | None = None
    distance_to_support_pct: Decimal | None = None
    line_points: int | None = None
    line_reason: str | None = None
    hype_score: Decimal | None = None
    hype_reason: str | None = None


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


def _signals(r: RowMapping) -> dict[str, Any]:
    """The ``0024`` columns, the same on the view and on ``meme_tokens``."""
    return {
        "rest_complete_seen_at": _optional(r["rest_complete_seen_at"]),
        "curve_filled_seen_at": _optional(r["curve_filled_seen_at"]),
        "graduated_board_seen_at": _optional(r["graduated_board_seen_at"]),
        "pool_created_at": _optional(r["pool_created_at"]),
        "pool_created_source": r["pool_created_source"],
        "progress_denominator_source": r["progress_denominator_source"],
    }


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
        **_signals(r),
    )


def matrix_row_from(r: RowMapping) -> MemeGraduationMatrixRow:
    return MemeGraduationMatrixRow(
        day_brt=r["day_brt"],
        **{
            column: int(r[column])
            for column in (
                "mints",
                "completed",
                "rest_complete",
                "curve_filled",
                "graduated_board",
                "pool_created",
                "signals_1",
                "signals_2",
                "signals_3",
                "signals_4",
                "disagree_rest_filled",
                "disagree_rest_board",
                "disagree_rest_pool",
                "disagree_filled_board",
                "disagree_filled_pool",
                "disagree_board_pool",
                "rest_only_unclassified",
            )
        },
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
        **_signals(r),
    )
