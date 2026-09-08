"""Assembling ``GET /api/v1/lab/shadow/replays{,/{run_id}}`` — brief T3.25."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.lab_replays import ReplayRunDetailOut, ReplayRunOut, ReplaySliceOut

if TYPE_CHECKING:
    from hunter_api.repositories.lab_replays import RunSummary, SliceRow


def _bars_per_second(summary: RunSummary) -> Decimal | None:
    if summary.seconds == 0:
        return None
    return Decimal(summary.bars_evaluated) / summary.seconds


def build_run_out(summary: RunSummary) -> ReplayRunOut:
    return ReplayRunOut(
        run_id=summary.run_id,
        cohort=summary.cohort,
        strategy_version_id=summary.strategy_version_id,
        version_label=summary.version_label,
        window_from=summary.window_from,
        window_to=summary.window_to,
        market_count=len(summary.markets),
        bars_evaluated=summary.bars_evaluated,
        seconds=summary.seconds,
        bars_per_second=_bars_per_second(summary),
        signals=summary.signals,
        outcomes_resolved=summary.outcomes_resolved,
        outcomes_open=summary.outcomes_open,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        slice_count=summary.slice_count,
    )


def build_runs_page(
    summaries: list[RunSummary], next_cursor: str | None
) -> CursorPage[ReplayRunOut]:
    return CursorPage(
        items=[build_run_out(summary) for summary in summaries], next_cursor=next_cursor
    )


def build_run_detail(
    summary: RunSummary, slices: list[SliceRow], population_by_state: dict[str, int]
) -> ReplayRunDetailOut:
    return ReplayRunDetailOut(
        run=build_run_out(summary),
        population_by_state=population_by_state,
        slices=[
            ReplaySliceOut(
                id=row.id,
                window_from=row.window_from,
                window_to=row.window_to,
                markets=row.markets,
                started_at=row.started_at,
                finished_at=row.finished_at,
                bars_evaluated=row.bars_evaluated,
                signals=row.signals,
                outcomes_resolved=row.outcomes_resolved,
                outcomes_open=row.outcomes_open,
                seconds=row.seconds,
                decision_lag_s=row.decision_lag_s,
                workers=row.workers,
                evaluations_by_state=row.evaluations_by_state,
                errors=row.errors,
                created_at=row.created_at,
            )
            for row in slices
        ],
    )
