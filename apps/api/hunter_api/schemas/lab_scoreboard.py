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
from hunter_api.schemas.lab_replication import ReplicationBlockOut
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


REPLAY_LABEL = "replay — não conta para o veredito"
"""Fixed label on every ``ReplayBlockOut`` (brief T3.18b, item 1; D15).

The block is evidence, never the ruler: ``ScoreboardRowOut.verdict`` and
``.maturity`` are computed over ``prospective`` alone, and this string is the
one place a client is told so in the payload itself, not only in a doc.
"""


class ReplayBlockOut(BaseModel):
    """The D14 "mass vs. evidence" pair for one version's replay cohorts,
    kept apart from the prospective block on purpose (D15): a replay may be
    positive while the prospective verdict is negative, or vice-versa, and
    neither number is allowed to leak into the other.
    """

    runs: int
    """Distinct replay runs (``replay_runs.run_id``) recorded for this version,
    com ``finished_at <= as_of`` (T3.18c, item 7)."""
    bars_evaluated: int
    """Soma de ``replay_runs.bars_evaluated`` — barras **varridas**."""
    decisions_simulated: int | None
    """As barras em que a estratégia registrou decisão (``triggered +
    not_triggered + rejected``) — o contador de **massa** da D14, agora medido
    contra decisões e não contra barras (T3.18c, item 9). ``null`` com motivo
    quando os recibos não trazem o mapa de estados."""
    decisions_simulated_reason: str | None = None
    evaluations_by_state: dict[str, int] = {}
    """O mapa somado, publicado inteiro: quem duvidar do numerador consegue
    refazê-lo."""
    operations_closed: int
    """Evaluable outcomes (the same gate as the prospective block's
    ``evaluable``) across every ``replay:<uuid>`` cohort of this version —
    the D14 **evidence** counter."""
    expectancy_r: NullableMetric
    net_profit_rate: RateWithCountsOut
    profit_factor: ProfitFactorOut
    distinct_days: int
    distinct_markets: int
    window_from: datetime | None
    """``min(replay_runs.window_from)`` over every run — ``null`` when
    ``runs == 0``."""
    window_to: datetime | None
    """``max(replay_runs.window_to)`` over every run — ``null`` when
    ``runs == 0``."""
    label: str = REPLAY_LABEL


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
    """Computed over ``prospective`` alone, always — ``replay`` and
    ``replication`` below never move it (D15)."""
    replay: ReplayBlockOut | None
    """``null`` when this version has no replay evidence at all (``runs == 0``
    and zero replay-cohort outcomes) — brief T3.18b, item 1."""
    replication: ReplicationBlockOut | None
    """``null`` when the version was never called ``validada`` by the ruler
    above (``ReplicationReport.status == "none"``) — the protocol has not
    started. Brief T3.18b, item 2; ``docs/plans/REPLICATION.md`` §6."""


class ScoreboardOut(BaseModel):
    as_of: datetime
    label: str = LAB_LABEL
    rows: list[ScoreboardRowOut]


__all__ = [
    "REPLAY_LABEL",
    "MaturityThresholdOut",
    "RateWithCountsOut",
    "ReplayBlockOut",
    "ScoreboardMaturityOut",
    "ScoreboardOut",
    "ScoreboardRowOut",
    "ScoreboardVersionOut",
]
