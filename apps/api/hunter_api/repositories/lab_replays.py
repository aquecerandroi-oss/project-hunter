"""``GET /api/v1/lab/shadow/replays{,/{run_id}}`` reads — brief T3.25.

Global, no-RLS reads over ``replay_runs`` (DATABASE.md §25.5): the table is
research evidence, one row per **slice**, never per run (§25.1). Every method
here groups slices back into runs the same way the docs describe summing
them — never a second definition of "the run's total".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select, tuple_

from hunter_api.repositories.base import decode_cursor, encode_cursor
from hunter_core.db.models.agents import Strategy, StrategyVersion
from hunter_core.db.models.replay_runs import ReplayRunRow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SliceRow", "RunSummary", "LabReplaysRepository"]


@dataclass(frozen=True, slots=True)
class SliceRow:
    id: uuid.UUID
    window_from: datetime
    window_to: datetime
    markets: list[str]
    started_at: datetime
    finished_at: datetime
    bars_evaluated: int
    signals: int
    outcomes_resolved: int
    outcomes_open: int
    seconds: Decimal
    decision_lag_s: int
    workers: int
    evaluations_by_state: dict[str, int]
    errors: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: uuid.UUID
    cohort: str
    strategy_version_id: uuid.UUID
    version_label: str
    window_from: datetime
    window_to: datetime
    markets: list[str]
    bars_evaluated: int
    seconds: Decimal
    signals: int
    outcomes_resolved: int
    outcomes_open: int
    started_at: datetime
    finished_at: datetime
    slice_count: int


def _summarize(slices: Sequence[ReplayRunRow], *, version_label: str) -> RunSummary:
    """One run from its slices — sums where DATABASE.md §25.2 says to sum,
    the last slice's value (by ``window_to``) where it says "running total"."""
    ordered = sorted(slices, key=lambda row: row.window_to)
    last = ordered[-1]
    markets: set[str] = set()
    for row in ordered:
        markets.update(row.markets)
    return RunSummary(
        run_id=last.run_id,
        cohort=last.cohort,
        strategy_version_id=last.strategy_version_id,
        version_label=version_label,
        window_from=min(row.window_from for row in ordered),
        window_to=max(row.window_to for row in ordered),
        markets=sorted(markets),
        bars_evaluated=sum(row.bars_evaluated for row in ordered),
        seconds=sum((row.seconds for row in ordered), Decimal(0)),
        signals=last.signals,
        outcomes_resolved=last.outcomes_resolved,
        outcomes_open=last.outcomes_open,
        started_at=min(row.started_at for row in ordered),
        finished_at=max(row.finished_at for row in ordered),
        slice_count=len(ordered),
    )


class LabReplaysRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_runs_page(
        self, *, limit: int, cursor: str | None
    ) -> tuple[list[RunSummary], str | None]:
        """Runs newest-first, by their own latest slice's ``finished_at``."""
        agg = (
            select(
                ReplayRunRow.run_id,
                func.max(ReplayRunRow.finished_at).label("finished_at"),
            )
            .group_by(ReplayRunRow.run_id)
            .subquery()
        )
        stmt = select(agg.c.run_id, agg.c.finished_at)
        after = decode_cursor(cursor)
        if after is not None:
            after_finished_at, after_run_id = after
            stmt = stmt.where(
                tuple_(agg.c.finished_at, agg.c.run_id) < (after_finished_at, after_run_id)
            )
        stmt = stmt.order_by(agg.c.finished_at.desc(), agg.c.run_id.desc()).limit(limit + 1)
        page_ids = (await self.session.execute(stmt)).all()
        has_more = len(page_ids) > limit
        page_ids = page_ids[:limit]
        if not page_ids:
            return [], None

        run_ids = [row_id for row_id, _ in page_ids]
        rows = (
            await self.session.execute(
                select(ReplayRunRow, Strategy.key, StrategyVersion.version)
                .join(StrategyVersion, StrategyVersion.id == ReplayRunRow.strategy_version_id)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(ReplayRunRow.run_id.in_(run_ids))
            )
        ).all()
        by_run: dict[uuid.UUID, list[ReplayRunRow]] = {}
        labels: dict[uuid.UUID, str] = {}
        for row, key, version in rows:
            by_run.setdefault(row.run_id, []).append(row)
            labels[row.run_id] = f"{key} {version}"

        summaries = [
            _summarize(by_run[run_id], version_label=labels[run_id])
            for run_id in run_ids
            if run_id in by_run
        ]
        next_cursor = (
            encode_cursor(page_ids[-1][1], page_ids[-1][0]) if has_more and page_ids else None
        )
        return summaries, next_cursor

    async def run_detail(self, run_id: uuid.UUID) -> tuple[RunSummary, list[SliceRow]] | None:
        rows = (
            await self.session.execute(
                select(ReplayRunRow, Strategy.key, StrategyVersion.version)
                .join(StrategyVersion, StrategyVersion.id == ReplayRunRow.strategy_version_id)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(ReplayRunRow.run_id == run_id)
                .order_by(ReplayRunRow.window_from)
            )
        ).all()
        if not rows:
            return None
        version_label = f"{rows[0][1]} {rows[0][2]}"
        slice_rows = [row for row, _, _ in rows]
        summary = _summarize(slice_rows, version_label=version_label)
        slices = [
            SliceRow(
                id=row.id,
                window_from=row.window_from,
                window_to=row.window_to,
                markets=list(row.markets),
                started_at=row.started_at,
                finished_at=row.finished_at,
                bars_evaluated=row.bars_evaluated,
                signals=row.signals,
                outcomes_resolved=row.outcomes_resolved,
                outcomes_open=row.outcomes_open,
                seconds=row.seconds,
                decision_lag_s=row.decision_lag_s,
                workers=row.workers,
                evaluations_by_state=dict(row.evaluations_by_state or {}),
                errors=row.errors,
                created_at=row.created_at,
            )
            for row in slice_rows
        ]
        return summary, slices

    async def population_by_state(self, run_id: uuid.UUID) -> dict[str, int]:
        """Sum of every slice's ``evaluations_by_state`` — a per-slice count,
        not a running total (DATABASE.md §25.2), so summing is the only way
        to get the run's population."""
        rows = (
            await self.session.execute(
                select(ReplayRunRow.evaluations_by_state).where(ReplayRunRow.run_id == run_id)
            )
        ).scalars()
        totals: dict[str, int] = {}
        for evaluations in rows:
            for state, count in (evaluations or {}).items():
                totals[state] = totals.get(state, 0) + int(count)
        return totals
