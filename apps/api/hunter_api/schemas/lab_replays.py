"""``GET /api/v1/lab/shadow/replays{,/{run_id}}`` — brief T3.25.

Backtests = replay. One run is one or more ``replay_runs`` slices
(DATABASE.md §25.1); this module's shapes reflect that split explicitly rather
than hiding it — a client that only ever wants the run's totals reads
``ReplayRunOut``, one that wants the throughput history reads ``slices``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.lab_common import DecimalStr


class ReplayRunOut(BaseModel):
    """One run, aggregated across every slice it has (DATABASE.md §25.2)."""

    run_id: uuid.UUID
    cohort: str
    strategy_version_id: uuid.UUID
    version_label: str
    window_from: datetime
    window_to: datetime
    market_count: int
    bars_evaluated: int
    seconds: DecimalStr
    bars_per_second: DecimalStr | None
    signals: int
    outcomes_resolved: int
    outcomes_open: int
    started_at: datetime
    finished_at: datetime
    slice_count: int


class ReplaySliceOut(BaseModel):
    """One ``replay_runs`` row exactly as written — the unit that actually
    happened (DATABASE.md §25.1)."""

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
    seconds: DecimalStr
    decision_lag_s: int
    workers: int
    evaluations_by_state: dict[str, int]
    errors: int
    created_at: datetime


class ReplayRunDetailOut(BaseModel):
    run: ReplayRunOut
    population_by_state: dict[str, int]
    """Sum of every slice's ``evaluations_by_state`` — the run's whole
    population, not one slice's (DATABASE.md §25.2)."""
    slices: list[ReplaySliceOut]


ReplayRunsPage = CursorPage[ReplayRunOut]
