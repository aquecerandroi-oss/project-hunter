"""``ScoreboardRowOut.replication`` — brief T3.18b, item 2.

Field-for-field the payload ``docs/plans/REPLICATION.md`` §6 documents as the
*real* output of ``hunter_indicators.replication.protocol.ReplicationReport
.to_jsonable()`` — every model here ``model_validate``s straight off that
dict (``services/lab_replication.py``), so this module never re-derives a
number the pure package already computed. The one field the JSON contract
does not carry is ``SiblingArmOut.evidence`` (D15): whether an arm's
maturity population came from its own live cohort, from a replay of it, or
both — the API's own bookkeeping, not the protocol's statistics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr

Evidence = Literal["prospective", "replay", "mixed"]


class PopulationStatsOut(BaseModel):
    """``hunter_indicators.replication.stats.PopulationStats.to_jsonable()``."""

    evaluable: int
    days: int
    markets: int
    expectancy_r: DecimalStr | None
    profit_factor: DecimalStr | None
    profit_factor_reason: str | None
    sum_r: DecimalStr | None
    wins: int
    losses: int


class ReplicationParentOut(PopulationStatsOut):
    verdict: str
    """``inconclusivo|validada|reprovada`` — the scoreboard's own ruler
    (§2), recomputed here over the same ``prospective`` population so the
    two never quietly disagree."""


class OutOfSampleBlockOut(PopulationStatsOut):
    """Bloco 1 — REPLICATION.md §3.1. Always ``prospective`` (D15)."""

    passed: bool | None
    reason: str | None
    mature: bool


class SiblingArmOut(PopulationStatsOut):
    k: int
    version: str
    mature: bool
    positive: bool
    evidence: Evidence | None
    """``null`` when the arm has produced zero outcomes yet; otherwise which
    cohort(s) its population came from (D15: replay may count toward this
    block's maturity, labelled)."""
    window_from: datetime | None = None
    """Início da janela replayada deste braço (``replay_runs.window_from``,
    recibos com ``finished_at <= as_of``) — ``null`` quando o braço não conta
    replay. REPLICATION.md §3.5 item 4 exige a janela ao lado do rótulo."""
    window_to: datetime | None = None
    duplicates_dropped: int = 0
    """Resultados de replay descartados por repetirem uma (mercado, decisão)
    que a coorte viva — ou outra corrida — já trazia (T3.18c, item 3)."""


class SiblingsBlockOut(BaseModel):
    """Bloco 2 — REPLICATION.md §3.2."""

    passed: bool | None
    reason: str | None
    n: int
    """Braços que **existem**."""
    expected: int
    """Braços que a rodada prevê (``IRMAS_N`` = 10)."""
    pool: int
    """``max(n, expected)`` — o denominador da regra 7-em-10. Enquanto ele era
    ``n``, seis irmãs perfeitas viravam "refutada: 0 negativas" (T3.18c, item
    4)."""
    required: int
    mature: int
    positive: int
    label: str | None = None
    """``"siblings: replay sobre <janela>"`` quando qualquer braço amadureceu
    com replay (D15 a, REPLICATION.md §3.5 item 4); ``null`` quando o bloco é
    inteiramente prospectivo."""
    arms: list[SiblingArmOut]


class MarketHalfOut(BaseModel):
    half: str
    markets: int
    evaluable: int
    expectancy_r: DecimalStr | None
    mature: bool
    reason: str | None


class MarketHalvesBlockOut(BaseModel):
    """Bloco 3 — REPLICATION.md §3.3."""

    passed: bool | None
    reason: str | None
    a: MarketHalfOut
    b: MarketHalfOut


class BootstrapIntervalOut(BaseModel):
    """One ``BootstrapResult.to_jsonable()`` — i.i.d. or per-day-cluster."""

    n: int
    mean: DecimalStr | None
    ci_low: DecimalStr | None
    ci_high: DecimalStr | None
    resamples: int
    seed: int
    confidence: DecimalStr
    method: str
    groups: int | None
    refused_reason: str | None
    seed_source: str = "derivada_do_id"
    """``registrada`` (lida do evento ``strategy_version_replicated`` da
    rodada) ou ``derivada_do_id`` (nenhuma rodada registrada; semente
    determinística derivada do id da versão). T3.18c, item 6."""


class SignTestOut(BaseModel):
    positives: int
    negatives: int
    zeros: int
    p_sign: DecimalStr | None
    method: str
    refused_reason: str | None


class BootstrapBlockOut(BootstrapIntervalOut):
    """Bloco 4 — REPLICATION.md §3.4. The i.i.d. interval's own fields sit at
    the top level (matching ``to_jsonable()``'s flattening) with the
    day-cluster interval and the sign test nested beside it."""

    passed: bool | None
    reason: str | None
    day_cluster: BootstrapIntervalOut
    sign_test: SignTestOut


class ReplicationBlockOut(BaseModel):
    """The whole ``replication`` block — REPLICATION.md §6."""

    status: str
    reason: str | None
    promising_at: datetime | None
    parent: ReplicationParentOut
    out_of_sample: OutOfSampleBlockOut
    siblings: SiblingsBlockOut
    market_halves: MarketHalvesBlockOut
    bootstrap: BootstrapBlockOut


__all__ = [
    "BootstrapBlockOut",
    "BootstrapIntervalOut",
    "Evidence",
    "MarketHalfOut",
    "MarketHalvesBlockOut",
    "OutOfSampleBlockOut",
    "PopulationStatsOut",
    "ReplicationBlockOut",
    "ReplicationParentOut",
    "SiblingArmOut",
    "SiblingsBlockOut",
    "SignTestOut",
]
