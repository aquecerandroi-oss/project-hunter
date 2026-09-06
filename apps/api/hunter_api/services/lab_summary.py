"""Assembling ``GET /api/v1/lab/shadow/summary`` — SHADOW-LAB.md §9.

The pure math lives in ``lab_summary_metrics.py``; this module is the funnel
counting and the wiring into the response schema.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from hunter_api.schemas.lab_common import NullableMetric, ProfitFactorOut, SumOfROut
from hunter_api.schemas.lab_summary import (
    AssumedCostsOut,
    CensoredCounts,
    CoverageOut,
    MaturityOut,
    NoEntryCounts,
    RExFundingBlock,
    RExFundingCoverage,
    SummaryOut,
    TerminalCounts,
    VersionCounts,
    VersionMetrics,
    VersionSummaryOut,
)
from hunter_api.services.lab_summary_metrics import (
    NO_ENTRY_REASONS,
    ProfitFactorResult,
    RateResult,
    SumResult,
    bucket_censored_reason,
    expectancy,
    is_evaluable,
    profit_factor,
    r_ex_funding_of,
    rate,
    sum_of,
    touch_counts,
)
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

if TYPE_CHECKING:
    from hunter_api.repositories.lab_summary import OutcomeRow, VersionMeta

__all__ = ["WINDOWS", "build_summary", "build_version_summary", "window_since"]

WINDOWS: dict[str, timedelta | None] = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}

MATURITY_MIN_OUTCOMES = 100
MATURITY_MIN_DAYS = 30

_TERMINAL_RESULTS = tuple(r for r in OutcomeResult if r is not OutcomeResult.OPEN)


def window_since(window: str, as_of: datetime) -> datetime | None:
    delta = WINDOWS[window]
    return None if delta is None else as_of - delta


def _terminal_by_result(rows: list[OutcomeRow]) -> dict[str, int]:
    terminal = [r for r in rows if r.tracking_state is ShadowTrackingState.TERMINAL]
    return {
        result.value: sum(1 for r in terminal if r.result is result) for result in _TERMINAL_RESULTS
    }


def _no_entry_by_reason(rows: list[OutcomeRow]) -> dict[str, int]:
    no_entry = [r for r in rows if r.tracking_state is ShadowTrackingState.NO_ENTRY]
    by_reason = {reason: 0 for reason in NO_ENTRY_REASONS}
    other = 0
    for r in no_entry:
        if r.no_entry_reason in by_reason:
            by_reason[r.no_entry_reason] += 1
        else:
            other += 1
    if other:
        by_reason["other"] = other
    return by_reason


def _censored_by_reason(rows: list[OutcomeRow]) -> dict[str, int]:
    censored = [r for r in rows if r.tracking_state is ShadowTrackingState.CENSORED]
    by_reason: dict[str, int] = {}
    for r in censored:
        bucket = bucket_censored_reason(r.censored_reason)
        by_reason[bucket] = by_reason.get(bucket, 0) + 1
    return by_reason


def _counts(rows: list[OutcomeRow], evaluable: list[OutcomeRow]) -> VersionCounts:
    return VersionCounts(
        signals_emitted=len(rows),
        pending_entry=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.PENDING_ENTRY),
        entered=sum(1 for r in rows if r.entry_ts is not None),
        no_entry=NoEntryCounts(
            total=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.NO_ENTRY),
            by_reason=_no_entry_by_reason(rows),
        ),
        active=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.ACTIVE),
        terminal=TerminalCounts(
            total=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.TERMINAL),
            by_result=_terminal_by_result(rows),
        ),
        censored=CensoredCounts(
            total=sum(1 for r in rows if r.tracking_state is ShadowTrackingState.CENSORED),
            by_reason=_censored_by_reason(rows),
        ),
        funding_not_settleable=sum(1 for r in evaluable if r.r_multiple is None),
    )


def _nullable(result: RateResult) -> NullableMetric:
    return NullableMetric(value=result.value, reason=result.reason)


def _profit_factor_out(result: ProfitFactorResult) -> ProfitFactorOut:
    return ProfitFactorOut(
        value=result.value,
        reason=result.reason,
        sum_positive=result.sum_positive,
        sum_negative_abs=result.sum_negative_abs,
        sample_size=result.sample_size,
    )


def _sum_out(result: SumResult) -> SumOfROut:
    return SumOfROut(value=result.value, reason=result.reason, count=result.count)


def _r_net_series(evaluable: list[OutcomeRow]) -> list[Decimal]:
    """``evaluable`` rows always have ``exit_ts`` set (``is_evaluable`` requires
    it), so the sort key is never ``None`` in practice; ``cast`` says so to the
    type checker instead of writing a fallback that can never run.
    """
    candidates = [r for r in evaluable if r.r_multiple is not None]
    candidates.sort(key=lambda r: cast("datetime", r.exit_ts))
    return [cast("Decimal", r.r_multiple) for r in candidates]


def _r_ex_funding_series(evaluable: list[OutcomeRow]) -> list[Decimal]:
    pairs = [
        (cast("datetime", r.exit_ts), v) for r in evaluable if (v := r_ex_funding_of(r)) is not None
    ]
    pairs.sort(key=lambda pair: pair[0])
    return [value for _, value in pairs]


def _metrics(evaluable: list[OutcomeRow]) -> VersionMetrics:
    target_n, stop_n = touch_counts(evaluable)
    target_rate = rate(target_n, target_n + stop_n, reason_if_empty="no_resolved_touches")
    series = _r_net_series(evaluable)
    wins = sum(1 for v in series if v > 0)
    return VersionMetrics(
        target_rate_among_resolved_touches=_nullable(target_rate),
        net_profit_rate=_nullable(rate(wins, len(series), reason_if_empty="no_sample")),
        hypothetical_net_expectancy_r=_nullable(expectancy(series)),
        profit_factor=_profit_factor_out(profit_factor(series)),
        sum_of_hypothetical_r=_sum_out(sum_of(series)),
    )


def _r_ex_funding_block(evaluable: list[OutcomeRow]) -> RExFundingBlock:
    series = _r_ex_funding_series(evaluable)
    wins = sum(1 for v in series if v > 0)
    r_net_n = sum(1 for r in evaluable if r.r_multiple is not None)
    return RExFundingBlock(
        net_profit_rate=_nullable(rate(wins, len(series), reason_if_empty="no_sample")),
        hypothetical_net_expectancy_r=_nullable(expectancy(series)),
        profit_factor=_profit_factor_out(profit_factor(series)),
        sum_of_hypothetical_r=_sum_out(sum_of(series)),
        coverage=RExFundingCoverage(
            evaluable_outcomes=len(series), r_net_evaluable_outcomes=r_net_n
        ),
    )


def _maturity(evaluable: list[OutcomeRow]) -> MaturityOut:
    r_net_rows = [r for r in evaluable if r.r_multiple is not None]
    distinct_days = len({r.exit_ts.date() for r in r_net_rows if r.exit_ts is not None})
    n = len(r_net_rows)
    return MaturityOut(
        evaluable_outcomes=n,
        distinct_days=distinct_days,
        inconclusive=n < MATURITY_MIN_OUTCOMES or distinct_days < MATURITY_MIN_DAYS,
    )


def _assumed_costs(params: dict[str, Any]) -> AssumedCostsOut:
    def dec(key: str) -> Decimal | None:
        value = params.get(key)
        return None if value is None else Decimal(str(value))

    delay = params.get("max_entry_delay_s")
    return AssumedCostsOut(
        assumed_spread_bps=dec("assumed_spread_bps"),
        slippage_bps=dec("slippage_bps"),
        fee_bps=dec("fee_bps"),
        max_entry_delay_s=None if delay is None else int(str(delay)),
    )


def _coverage(rows: list[OutcomeRow], default_parameters: dict[str, Any]) -> CoverageOut:
    return CoverageOut(
        markets_with_signals=len({r.market_id for r in rows}),
        distinct_days=len({r.decision_at.date() for r in rows}),
        assumed_costs=_assumed_costs(default_parameters),
    )


def build_version_summary(
    meta: VersionMeta, rows: list[OutcomeRow], as_of: datetime
) -> VersionSummaryOut:
    evaluable = [r for r in rows if is_evaluable(r, as_of)]
    return VersionSummaryOut(
        strategy_version_id=meta.id,
        strategy_key=meta.strategy_key,
        version=meta.version,
        code_ref=meta.code_ref,
        status=meta.status,
        activated_at=meta.activated_at,
        deprecated_at=meta.deprecated_at,
        counts=_counts(rows, evaluable),
        metrics=_metrics(evaluable),
        r_ex_funding=_r_ex_funding_block(evaluable),
        maturity=_maturity(evaluable),
        coverage=_coverage(rows, meta.default_parameters),
    )


def build_summary(
    *, as_of: datetime, window: str, cohort: str, versions: list[VersionSummaryOut]
) -> SummaryOut:
    return SummaryOut(as_of=as_of, window=window, cohort=cohort, versions=versions)
