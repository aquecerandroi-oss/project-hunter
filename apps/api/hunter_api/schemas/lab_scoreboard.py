"""``GET /api/v1/lab/shadow/scoreboard`` — brief T3.18.

One row per ``strategy_version`` that has ever emitted a signal, with the
mechanical verdict SHADOW-LAB.md §10 defines. Money is deliberately absent:
the web applies the T3.17 ruler over ``sum_r``/``expectancy_r`` — this API
only ever returns R multiples and counts.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from hunter_api.schemas.lab_common import (
    LAB_LABEL,
    DecimalStr,
    NullableMetric,
    ProfitFactorOut,
    SumOfROut,
)
from hunter_core.domain.enums import StrategyVersionStatus


class RateWithCountsOut(BaseModel):
    """A rate that always shows its own numerator/denominator (brief item 1)."""

    value: DecimalStr | None
    reason: str | None = None
    numerator: int
    denominator: int


class MaturityThresholdOut(BaseModel):
    outcomes: int = 100
    days: int = 30


class ScoreboardMaturityOut(BaseModel):
    evaluable: int
    days: int
    threshold: MaturityThresholdOut
    mature: bool


class ScoreboardVersionOut(BaseModel):
    id: uuid.UUID
    strategy_key: str
    version: str
    purpose: str
    status: StrategyVersionStatus
    activated_at: datetime | None
    code_ref: str | None


class ScoreboardRowOut(BaseModel):
    version: ScoreboardVersionOut
    emitted: int
    evaluable: int
    """Terminal, horizon-matured outcomes with a known ``r_multiple`` — the
    same population ``maturity.evaluable`` counts (``is_evaluable()`` gate,
    ``lab_summary_metrics.py``, then filtered to ``r_multiple is not None``)."""
    pending: int
    no_entry: int
    censored: int
    distinct_days: int
    """Distinct decision days across **every** emitted signal — the version's
    observation window, wider than ``maturity.days`` on purpose."""
    distinct_markets: int
    hit_rate: RateWithCountsOut
    """Alvo entre toques resolvidos: ``target / (target + stop)``."""
    net_profit_rate: RateWithCountsOut
    """Lucro líquido entre avaliáveis: ``count(r_multiple > 0) / evaluable``."""
    expectancy_r: NullableMetric
    profit_factor: ProfitFactorOut
    sum_r: SumOfROut
    worst_streak: int
    max_drawdown_r: DecimalStr
    maturity: ScoreboardMaturityOut
    verdict: str


class ScoreboardOut(BaseModel):
    as_of: datetime
    label: str = LAB_LABEL
    rows: list[ScoreboardRowOut]


__all__ = [
    "MaturityThresholdOut",
    "RateWithCountsOut",
    "ScoreboardMaturityOut",
    "ScoreboardOut",
    "ScoreboardRowOut",
    "ScoreboardVersionOut",
]
