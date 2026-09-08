"""Assembling ``ScoreboardRowOut.replay`` — brief T3.18b, item 1 (D14/D15).

Same metric functions the prospective block uses
(``services/lab_summary_metrics.py``'s ``is_evaluable``/``rate``/
``expectancy``/``profit_factor``), only the cohort filter differs — the
brief's "reuse, do not reinvent". No maturity, no verdict, no worst-streak or
drawdown: D15 keeps this block pure evidence, never the ruler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_api.schemas.lab_common import NullableMetric, ProfitFactorOut
from hunter_api.schemas.lab_scoreboard import RateWithCountsOut, ReplayBlockOut
from hunter_api.services.lab_summary_metrics import expectancy, is_evaluable, profit_factor, rate

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_api.repositories.lab_scoreboard import ReplayRunsSummary
    from hunter_api.repositories.lab_summary import OutcomeRow

__all__ = ["build_replay_block"]


def build_replay_block(
    *, rows: list[OutcomeRow], runs: ReplayRunsSummary, as_of: datetime
) -> ReplayBlockOut | None:
    """``None`` when there is no replay evidence at all for this version —
    zero receipted runs and zero replay-cohort outcome rows."""
    if runs.runs == 0 and not rows:
        return None

    gate_rows = [r for r in rows if is_evaluable(r, as_of)]
    series = [r.r_multiple for r in gate_rows if r.r_multiple is not None]

    wins = sum(1 for v in series if v > 0)
    net_profit_result = rate(wins, len(series), reason_if_empty="no_sample")
    expectancy_result = expectancy(series)
    pf_result = profit_factor(series)

    return ReplayBlockOut(
        runs=runs.runs,
        decisions_simulated=runs.bars_evaluated,
        operations_closed=len(series),
        expectancy_r=NullableMetric(value=expectancy_result.value, reason=expectancy_result.reason),
        net_profit_rate=RateWithCountsOut(
            value=net_profit_result.value,
            reason=net_profit_result.reason,
            numerator=wins,
            denominator=len(series),
        ),
        profit_factor=ProfitFactorOut(
            value=pf_result.value,
            reason=pf_result.reason,
            sum_positive=pf_result.sum_positive,
            sum_negative_abs=pf_result.sum_negative_abs,
            sample_size=pf_result.sample_size,
        ),
        distinct_days=len({r.decision_at.date() for r in rows}),
        distinct_markets=len({r.market_id for r in rows}),
        window_from=runs.window_from,
        window_to=runs.window_to,
    )
