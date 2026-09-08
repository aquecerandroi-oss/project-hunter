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

__all__ = ["build_scoreboard", "build_scoreboard_row"]


def _r_net_series(gate_rows: list[OutcomeRow]) -> list[Decimal]:
    """Gate-passed rows with a known ``r_multiple``, ordered by ``exit_ts``.

    ``is_evaluable`` guarantees ``exit_ts`` is set on every row it admits, so
    the sort key is never ``None`` in practice; ``cast`` says so to the type
    checker instead of a fallback branch that can never run.
    """
    candidates = [r for r in gate_rows if r.r_multiple is not None]
    candidates.sort(key=lambda r: cast("datetime", r.exit_ts))
    return [cast("Decimal", r.r_multiple) for r in candidates]


def build_scoreboard_row(
    meta: ScoreboardVersionMeta, rows: list[OutcomeRow], as_of: datetime
) -> ScoreboardRowOut:
    gate_rows = [r for r in rows if is_evaluable(r, as_of)]
    series = _r_net_series(gate_rows)

    target_n, stop_n = touch_counts(gate_rows)
    hit_rate_result = rate(target_n, target_n + stop_n, reason_if_empty="no_resolved_touches")

    wins = sum(1 for v in series if v > 0)
    net_profit_result = rate(wins, len(series), reason_if_empty="no_sample")

    expectancy_result = expectancy(series)
    pf_result = profit_factor(series)
    sum_result = sum_of(series)

    evaluable_count = len(series)
    maturity_days = len({r.exit_ts.date() for r in gate_rows if r.exit_ts is not None})
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
    )


def build_scoreboard(*, as_of: datetime, rows: list[ScoreboardRowOut]) -> ScoreboardOut:
    return ScoreboardOut(as_of=as_of, rows=rows)
