"""Assembling ``GET /api/v1/lab/shadow/scoreboard`` — brief T3.18.

Reuses every metric definition from ``lab_summary_metrics.py`` (``is_evaluable``,
``rate``, ``expectancy``, ``profit_factor``, ``sum_of``, ``touch_counts``) and
the maturity threshold from ``lab_summary.py`` — this module only adds the
worst-streak/drawdown/verdict wiring that is new to this brief
(``lab_scoreboard_metrics.py``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

from hunter_api.schemas.lab_common import NullableMetric, ProfitFactorOut, SumOfROut
from hunter_api.schemas.lab_scoreboard import (
    MaturityThresholdOut,
    RateWithCountsOut,
    ScoreboardMaturityOut,
    ScoreboardOut,
    ScoreboardRowOut,
    ScoreboardVersionOut,
)
from hunter_api.services.lab_scoreboard_metrics import compute_verdict, max_drawdown_r, worst_streak
from hunter_api.services.lab_summary import MATURITY_MIN_DAYS, MATURITY_MIN_OUTCOMES
from hunter_api.services.lab_summary_metrics import (
    expectancy,
    is_evaluable,
    profit_factor,
    rate,
    sum_of,
    touch_counts,
)
from hunter_core.domain.enums import ShadowTrackingState

if TYPE_CHECKING:
    from decimal import Decimal

    from hunter_api.repositories.lab_scoreboard import ScoreboardVersionMeta
    from hunter_api.repositories.lab_summary import OutcomeRow
    from hunter_api.schemas.lab_replication import ReplicationBlockOut
    from hunter_api.schemas.lab_scoreboard import ReplayBlockOut

__all__ = ["build_scoreboard", "build_scoreboard_row"]


def _evaluable_rows(gate_rows: list[OutcomeRow]) -> list[OutcomeRow]:
    """Gate-passed rows with a known ``r_multiple``, ordered by ``exit_ts``.

    **Esta** é a população avaliável — a que conta resultados, dias de saída,
    expectancy, PF e veredito, e a mesma que a replicação carrega
    (``repositories/lab_replication.py``, T3.18c item 2). Uma linha que passou
    no portão mas não tem R (funding não apurável, ``SHADOW-LAB.md`` §3) não é
    avaliável, e por isso também não empresta um dia à régua: enquanto ela
    emprestava, ``maturity.days`` contava dias de uma população maior do que
    ``maturity.evaluable``.

    ``is_evaluable`` guarantees ``exit_ts`` is set on every row it admits, so
    the sort key is never ``None`` in practice; ``cast`` says so to the type
    checker instead of a fallback branch that can never run.
    """
    candidates = [r for r in gate_rows if r.r_multiple is not None]
    candidates.sort(key=lambda r: cast("datetime", r.exit_ts))
    return candidates


def build_scoreboard_row(
    meta: ScoreboardVersionMeta,
    rows: list[OutcomeRow],
    as_of: datetime,
    *,
    replay: ReplayBlockOut | None = None,
    replication: ReplicationBlockOut | None = None,
) -> ScoreboardRowOut:
    gate_rows = [r for r in rows if is_evaluable(r, as_of)]
    evaluable_rows = _evaluable_rows(gate_rows)
    series = [cast("Decimal", r.r_multiple) for r in evaluable_rows]

    target_n, stop_n = touch_counts(gate_rows)
    hit_rate_result = rate(target_n, target_n + stop_n, reason_if_empty="no_resolved_touches")

    wins = sum(1 for v in series if v > 0)
    net_profit_result = rate(wins, len(series), reason_if_empty="no_sample")

    expectancy_result = expectancy(series)
    pf_result = profit_factor(series)
    sum_result = sum_of(series)

    evaluable_count = len(series)
    maturity_days = len({cast("datetime", r.exit_ts).date() for r in evaluable_rows})
    mature = evaluable_count >= MATURITY_MIN_OUTCOMES and maturity_days >= MATURITY_MIN_DAYS

    verdict = compute_verdict(
        mature=mature,
        expectancy_r=expectancy_result.value,
        profit_factor=pf_result.value,
        pf_reason=pf_result.reason,
    )

    return ScoreboardRowOut(
        version=ScoreboardVersionOut(
            id=meta.id,
            strategy_key=meta.strategy_key,
            version=meta.version,
            purpose=meta.purpose,
            status=meta.status,
            activated_at=meta.activated_at,
            code_ref=meta.code_ref,
        ),
        emitted=len(rows),
        evaluable=evaluable_count,
        pending=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.PENDING_ENTRY),
        no_entry=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.NO_ENTRY),
        censored=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.CENSORED),
        distinct_days=len({r.decision_at.date() for r in rows}),
        distinct_markets=len({r.market_id for r in rows}),
        hit_rate=RateWithCountsOut(
            value=hit_rate_result.value,
            reason=hit_rate_result.reason,
            numerator=target_n,
            denominator=target_n + stop_n,
        ),
        net_profit_rate=RateWithCountsOut(
            value=net_profit_result.value,
            reason=net_profit_result.reason,
            numerator=wins,
            denominator=len(series),
        ),
        expectancy_r=NullableMetric(value=expectancy_result.value, reason=expectancy_result.reason),
        profit_factor=ProfitFactorOut(
            value=pf_result.value,
            reason=pf_result.reason,
            sum_positive=pf_result.sum_positive,
            sum_negative_abs=pf_result.sum_negative_abs,
            sample_size=pf_result.sample_size,
        ),
        sum_r=SumOfROut(value=sum_result.value, reason=sum_result.reason, count=sum_result.count),
        worst_streak=worst_streak(series),
        max_drawdown_r=max_drawdown_r(series),
        maturity=ScoreboardMaturityOut(
            evaluable=evaluable_count,
            days=maturity_days,
            threshold=MaturityThresholdOut(),
            mature=mature,
        ),
        verdict=verdict,
        replay=replay,
        replication=replication,
    )


def build_scoreboard(*, as_of: datetime, rows: list[ScoreboardRowOut]) -> ScoreboardOut:
    return ScoreboardOut(as_of=as_of, rows=rows)
