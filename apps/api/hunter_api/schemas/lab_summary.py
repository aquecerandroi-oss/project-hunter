"""``GET /api/v1/lab/shadow/summary`` — SHADOW-LAB.md §9, contract-S3-lab.md.

One object per activated ``strategy_version`` (``draft`` rows never ran an
experiment, so they are excluded). Every metric that can have an empty
denominator carries its own ``reason`` sibling rather than a bare ``null``.
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


class NoEntryCounts(BaseModel):
    total: int
    by_reason: dict[str, int]


class TerminalCounts(BaseModel):
    total: int
    by_result: dict[str, int]


class CensoredCounts(BaseModel):
    total: int
    by_reason: dict[str, int]


class VersionCounts(BaseModel):
    decisions: None = None
    decisions_reason: str = "evaluation_state_not_persisted"
    """``Evaluation.state`` (``packages/core/hunter_core/strategies/base.py``)
    only ever exists as the strategy-worker's own Prometheus counters — never a
    durable row. ``signals_emitted`` below is the only "decision" count this
    API can honestly report (Astra, contract review, must-fix 1)."""
    signals_emitted: int
    pending_entry: int
    entered: int
    """``entry_ts IS NOT NULL`` — includes a tracking later censored while
    active; "entered" is a past fact, independent of how it ended."""
    no_entry: NoEntryCounts
    active: int
    terminal: TerminalCounts
    censored: CensoredCounts
    funding_not_settleable: int
    """Matured, terminal outcomes whose ``r_multiple`` is still ``null`` — a
    funding settlement could not be established (never "inapplicable": a
    proven zero funding charge produces a valid ``r_multiple``)."""


class RExFundingCoverage(BaseModel):
    evaluable_outcomes: int
    r_net_evaluable_outcomes: int


class VersionMetrics(BaseModel):
    target_rate_among_resolved_touches: NullableMetric
    net_profit_rate: NullableMetric
    hypothetical_net_expectancy_r: NullableMetric
    profit_factor: ProfitFactorOut
    sum_of_hypothetical_r: SumOfROut


class RExFundingBlock(BaseModel):
    net_profit_rate: NullableMetric
    hypothetical_net_expectancy_r: NullableMetric
    profit_factor: ProfitFactorOut
    sum_of_hypothetical_r: SumOfROut
    coverage: RExFundingCoverage


class MaturityOut(BaseModel):
    evaluable_outcomes: int
    distinct_days: int
    inconclusive: bool
    """``true`` while ``evaluable_outcomes < 100 OR distinct_days < 30``
    (SHADOW-LAB.md §9's editorial threshold)."""


class AssumedCostsOut(BaseModel):
    assumed_spread_bps: DecimalStr | None
    slippage_bps: DecimalStr | None
    fee_bps: DecimalStr | None
    max_entry_delay_s: int | None


class CoverageOut(BaseModel):
    markets_with_signals: int
    distinct_days: int
    note: str = (
        "counts markets/days that produced at least one signal — evaluations "
        "that never triggered are not observable (Evaluation.state is not "
        "persisted; see counts.decisions_reason)"
    )
    assumed_costs: AssumedCostsOut


class VersionSummaryOut(BaseModel):
    strategy_version_id: uuid.UUID
    strategy_key: str
    version: str
    code_ref: str | None
    status: StrategyVersionStatus
    activated_at: datetime | None
    deprecated_at: datetime | None
    counts: VersionCounts
    metrics: VersionMetrics
    r_ex_funding: RExFundingBlock
    portfolio_pnl: None = None
    portfolio_pnl_reason: str = "not_applicable"
    portfolio_max_drawdown: None = None
    portfolio_max_drawdown_reason: str = "not_applicable"
    maturity: MaturityOut
    coverage: CoverageOut


class SummaryOut(BaseModel):
    as_of: datetime
    window: str
    cohort: str
    label: str = LAB_LABEL
    versions: list[VersionSummaryOut]


__all__ = [
    "AssumedCostsOut",
    "CensoredCounts",
    "CoverageOut",
    "MaturityOut",
    "NoEntryCounts",
    "RExFundingBlock",
    "RExFundingCoverage",
    "SummaryOut",
    "TerminalCounts",
    "VersionCounts",
    "VersionMetrics",
    "VersionSummaryOut",
]
