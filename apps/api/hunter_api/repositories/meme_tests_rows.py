"""Row shapes of the test record (T4.13) — split out of
``repositories/meme_tests.py`` for the 350-line budget, the way
``meme_desk_rows.py`` backs ``meme_desk.py``. Plain dataclasses and the two
mappers that build them; no session, no table name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_api.repositories.meme_desk_rows import (
    BetRow,
    ProposalRow,
    RuleSetRow,
    TokenIdentity,
)
from hunter_api.schemas.meme_tests import WalletsSource
from hunter_core.domain.types import ensure_utc

__all__ = [
    "PREFERRED_FEATURES_VERSION",
    "BetRecord",
    "CurvePointRow",
    "DayTotalsRow",
    "FeaturesAtMinute",
    "WalletPositionsRead",
    "features_from_mapping",
    "prefer_version",
]

PREFERRED_FEATURES_VERSION = "meme_features_v3"
"""The version whose rows carry the line and hype columns (``0026``); an older
minute is read as it is, with its own ``features_version`` named."""


@dataclass(frozen=True, slots=True)
class BetRecord:
    bet: BetRow
    proposal: ProposalRow | None
    token: TokenIdentity | None
    rule_set: RuleSetRow | None


@dataclass(frozen=True, slots=True)
class FeaturesAtMinute:
    mint: str
    end_time: datetime
    features_version: str
    line_reason: str | None
    support_line_sol: Decimal | None
    distance_to_support_pct: Decimal | None
    higher_lows: bool | None
    breakout_15m: bool | None
    hype_score: Decimal | None
    hype_reason: str | None
    creator_sold: bool | None
    creator_sold_reason: str | None
    curve_progress_pct: Decimal | None
    progress_reason: str | None
    age_minutes: int | None
    unique_buyers: int | None
    mcap_sol: Decimal | None


@dataclass(frozen=True, slots=True)
class DayTotalsRow:
    bets: int
    closed: int
    open: int
    wins: int
    losses: int
    pnl_sol: Decimal
    provisional_pnl_sol: Decimal
    pnl_usd: Decimal | None
    unpriced_usd: int
    r_sum: Decimal


@dataclass(frozen=True, slots=True)
class CurvePointRow:
    observed_at: datetime
    source: str
    mcap_sol: Decimal | None
    complete: bool


@dataclass(frozen=True, slots=True)
class WalletPositionsRead:
    """``rows`` as the table returned them (columns are T4.12's, read
    tolerantly downstream) and the honest state of the source."""

    rows: list[dict[str, Any]]
    source: WalletsSource


def features_from_mapping(r: Any) -> FeaturesAtMinute:
    return FeaturesAtMinute(
        mint=r["mint"],
        end_time=ensure_utc(r["end_time"]),
        features_version=r["features_version"],
        line_reason=r["line_reason"],
        support_line_sol=r["support_line_sol"],
        distance_to_support_pct=r["distance_to_support_pct"],
        higher_lows=r["higher_lows"],
        breakout_15m=r["breakout_15m"],
        hype_score=r["hype_score"],
        hype_reason=r["hype_reason"],
        creator_sold=r["creator_sold"],
        creator_sold_reason=r["creator_sold_reason"],
        curve_progress_pct=r["curve_progress_pct"],
        progress_reason=r["progress_reason"],
        age_minutes=r["age_minutes"],
        unique_buyers=r["unique_buyers"],
        mcap_sol=r["mcap_sol"],
    )


def prefer_version(candidate: str, current: str) -> bool:
    """The preferred version wins; otherwise the newest name (``v3`` > ``v2``)."""
    if candidate == PREFERRED_FEATURES_VERSION:
        return True
    if current == PREFERRED_FEATURES_VERSION:
        return False
    return candidate > current
