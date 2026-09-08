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
from hunter_core.strategies.base import EvaluationState

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_api.repositories.lab_scoreboard import ReplayRunsSummary
    from hunter_api.repositories.lab_summary import OutcomeRow

__all__ = ["DECIDED_STATES", "NO_STATES_REASON", "build_replay_block", "decisions_simulated"]

DECIDED_STATES = (
    EvaluationState.TRIGGERED,
    EvaluationState.NOT_TRIGGERED,
    EvaluationState.REJECTED,
)
"""Os estados em que a estratégia **decidiu** sobre a barra (T3.18c, item 9).

D14 pede massa medida em "barra real avaliada pela estratégia, com a decisão
registrada". ``unavailable`` (warm-up, gap, indicador incalculável) e
``ineligible`` (mercado fora do universo no fechamento) não provam nada em
nenhuma direção — é a mesma distinção que o rearme de slot faz
(``hunter_strategy_worker.episodes``), e somá-las inflaria a meta de 500 mil
por dia com barras que ninguém julgou.
"""

NO_STATES_REASON = "sem_estados_registrados"
"""Recibos antigos (ou de um build sem o mapa) não sabem dizer quantas barras
viraram decisão: o número sai **nulo com motivo**, nunca zero inventado."""


def decisions_simulated(states: dict[str, int]) -> tuple[int | None, str | None]:
    """Decisões registradas e o motivo quando não dá para saber."""
    if not states:
        return None, NO_STATES_REASON
    return sum(states.get(state, 0) for state in DECIDED_STATES), None


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

    decided, decided_reason = decisions_simulated(runs.evaluations_by_state)
    return ReplayBlockOut(
        runs=runs.runs,
        bars_evaluated=runs.bars_evaluated,
        decisions_simulated=decided,
        decisions_simulated_reason=decided_reason,
        evaluations_by_state=dict(runs.evaluations_by_state),
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
