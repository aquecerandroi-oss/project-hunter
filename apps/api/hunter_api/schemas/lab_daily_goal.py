"""``GET /api/v1/orgs/{org_id}/lab/daily-goal`` — brief T3.78.

Frozen shape lives in ``.claude/state/notes-T3.78.md``. Every money/ratio
field is ``DecimalStr`` (never a bare float over the wire); every "no value"
is ``None`` **with a reason**, the same discipline ``lab_common.py`` already
uses for the rest of the Lab API.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr
from hunter_api.schemas.lab_scoreboard import RateWithCountsOut

__all__ = [
    "AxisOut",
    "DailyGoalOut",
    "PortfolioReferenceOut",
    "ProgressOut",
    "SeriesPointOut",
    "ValueOfOneROut",
]


class AxisOut(BaseModel):
    used: str = "r_net"
    """The only R this endpoint sums — ``signal_outcomes.r_multiple``,
    net of assumed costs. Never mixed with a recomputed ``r_ex_funding``."""
    pooled_funding_null: int
    """Terminal outcomes that day (every version) with ``r_multiple IS NULL``
    (T3.75's funding-NULL problem) — excluded from ``pooled_r``, not zeroed."""
    unique_funding_null: int
    """Same count, but over deduped bets (each bet's winning row)."""


class PortfolioReferenceOut(BaseModel):
    equity_usdt: DecimalStr | None
    source: str
    """``"equity_snapshot"``, ``"opening_anchor"`` or ``"no_portfolio"``."""


class ValueOfOneROut(BaseModel):
    label_brl: DecimalStr
    """``risk_per_trade_pct x R$100.000`` — the onboarding promise."""
    real_brl_p10: DecimalStr | None
    real_brl_p50: DecimalStr | None
    real_brl_p90: DecimalStr | None
    sample_size: int
    """How many of the day's unique bets could be priced at all."""
    reason: str | None = None
    """Set (and every ``real_brl_*`` above ``None``) when ``sample_size == 0``
    — ``"no_bets"`` or ``"no_priceable_bets"``."""


class ProgressOut(BaseModel):
    real_brl: DecimalStr | None
    """``unique_r x real_brl_p50`` — ``None`` when ``real_brl_p50`` is."""
    label_brl: DecimalStr
    """``unique_r x label_brl`` — always computable."""
    distance_to_goal_real_brl: DecimalStr | None
    distance_to_goal_label_brl: DecimalStr
    required_1r_brl: DecimalStr | None
    """``goal_brl / unique_r`` — ``None`` when ``unique_r <= 0``."""
    required_unique_r: DecimalStr | None
    """``goal_brl / real_brl_p50`` — ``None`` when ``real_brl_p50`` is
    ``None`` or not positive."""


class SeriesPointOut(BaseModel):
    day: date
    unique_r: DecimalStr
    pooled_r: DecimalStr


class DailyGoalOut(BaseModel):
    day: date
    """The Sao Paulo calendar day this row describes."""
    as_of: datetime
    axis: AxisOut
    dedupe_order: str = "activated_at asc, strategy_version_id asc, signal_id asc"
    unique_bets: int
    pooled_bets: int
    unique_r: DecimalStr
    pooled_r: DecimalStr
    hit_rate: RateWithCountsOut
    r_per_unique_bet: DecimalStr | None
    """``unique_r / unique_bets`` — ``None`` (never a division by zero) when
    ``unique_bets == 0``."""
    value_of_1r: ValueOfOneROut
    goal_brl: DecimalStr
    progress: ProgressOut
    portfolio: PortfolioReferenceOut
    fx_reason: str | None = None
    """Set when no USDTBRL observation was available by ``as_of`` — every
    ``real_brl_*``/``progress.*_real_brl`` field is then ``None`` for that
    reason, never a stale or default rate."""
    series_30d: list[SeriesPointOut]
