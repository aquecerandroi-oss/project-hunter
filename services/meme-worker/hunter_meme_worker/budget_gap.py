"""Recording the poll's own budget gap — split out of ``collect.py`` for the
350-line budget (T4.97b/R80): the counters and the one ``meme_ingest_gaps``
row per cycle are their own responsibility, not the polling loop's. One row
per cycle, not one per mint: the count is the fact, never a hole left silent.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_meme_worker.config import CURVE_STREAM
from hunter_meme_worker.metrics import meme_budget_skipped_total, meme_gaps_total
from hunter_meme_worker.repo import GapRow, record_gap

if TYPE_CHECKING:
    from hunter_meme_worker.context import RadarContext

__all__ = ["BUDGET_REASON", "record_budget_gap"]

WORKER_ROLE = "hunter_worker"
BUDGET_REASON = "budget_exhausted"


async def record_budget_gap(
    ctx: RadarContext,
    now: datetime,
    *,
    skipped: int,
    capped: int,
    aged_out: int,
    poll_cycle_s: float,
    rest_budget_per_minute: int,
    chain_covered: bool,
    breaker_suspended: int = 0,
) -> None:
    """``chain_covered``/the budget are passed in, never recomputed here —
    ``poll_once`` (``collect.py``) already knows them for this exact cycle,
    and importing ``chain_covered`` back from there would be circular."""
    meme_budget_skipped_total.inc(skipped + capped)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await record_gap(
            session,
            GapRow(
                stream=CURVE_STREAM,
                gap_start=now - timedelta(seconds=poll_cycle_s),
                gap_end=now,
                reason=BUDGET_REASON,
                detail={
                    "skipped": skipped,
                    "evicted_by_cap": capped,
                    "aged_out": aged_out,
                    "tracked": len(ctx.tracker),
                    "budget": rest_budget_per_minute,
                    "chain_covered": chain_covered,
                    # T4.97b: mints the identity breaker suspended this cycle —
                    # never attempted, distinct from the budget's own skip.
                    "breaker_suspended": breaker_suspended,
                },
            ),
        )
    meme_gaps_total.labels(stream=CURVE_STREAM, reason=BUDGET_REASON).inc()
    if ctx.sources is not None:
        ctx.sources.gaps_60s.add(now)
