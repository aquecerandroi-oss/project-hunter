"""The closed minute, with every source the radar has (T4.2c): the curve
snapshot of the minute (T4.2), the newest holders reading received by the
minute's close (boards or risk read), and the tape of the minute (``swap-api``)
— folded into one ``meme_features_1m`` row per tracked mint, next to the
board rows of the same minute.

Order inside one boundary, and why:

1. the board collector closes its buckets (``close_minute``) — the rows of the
   closed minute exist before anything reads holders from them;
2. the tape is read from ``meme_trades`` with ``received_at <= boundary`` — the
   database is the record, not a cache that may have moved since;
3. every tracked mint gets its row through the same pure ``build_row``.

Nothing here reads a clock but ``utcnow`` for ``received_at`` of the board rows.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.activity import batch_minute
from hunter_meme_worker.config import FEATURES_STREAM
from hunter_meme_worker.features import NOT_POLLED, FeatureRow, MinuteInputs, build_row
from hunter_meme_worker.features_lines import board_standing
from hunter_meme_worker.features_tape import (
    ACTIVITY_1M,
    HoldersObservation,
    TapeTrade,
    holders_for,
    tape_for,
)
from hunter_meme_worker.metrics import meme_features_rows_total, meme_gaps_total
from hunter_meme_worker.repo import GapRow, insert_features, record_gap
from hunter_meme_worker.repo_boards import insert_board_minutes
from hunter_meme_worker.repo_lines import load_line_points
from hunter_meme_worker.repo_tape import load_tape

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.meme.lines import LinePoint
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.tracker import TrackedMint

WORKER_ROLE = "hunter_worker"

logger = get_logger(__name__)


def _readings(ctx: RadarContext, mint: str) -> list[HoldersObservation]:
    readings: list[HoldersObservation] = []
    if ctx.boards is not None:
        readings.extend(ctx.boards.readings(mint))
    if ctx.risk is not None:
        readings.extend(ctx.risk.readings(mint))
    return readings


def _tape_inputs(
    ctx: RadarContext, tracked: TrackedMint, boundary: datetime, tape: dict[str, list[TapeTrade]]
) -> tuple[object, str]:
    if tracked.quote_unsupported:
        return None, "unsupported_quote"
    if ctx.trades is None:
        return None, "no_trade_feed"
    minute = tape_for(
        tape.get(tracked.mint, []),
        end_time=boundary,
        creator=tracked.creator,
        covered_since=ctx.trades.coverage_for(tracked.mint, boundary),
    )
    absence = ctx.trades.absence_reason(tracked.mint, at=boundary)
    if minute is None:
        # T4.2g: the batch route's 1m window, when the per-mint tape did not cover.
        return batch_minute(ctx, tracked.mint, at=boundary, absence=absence)
    return minute, absence


async def fold_minute(ctx: RadarContext, boundary: datetime) -> list[FeatureRow]:
    """Fold ``boundary`` for every tracked mint; write features and board rows."""
    observations, absences = ctx.state.drain()
    tracked_set = ctx.tracker.snapshot()
    board_rows = ctx.boards.close_minute(boundary) if ctx.boards is not None else []
    covered = [
        t.mint
        for t in tracked_set
        if ctx.trades is not None
        and (since := ctx.trades.coverage_for(t.mint, boundary)) is not None
        and since <= boundary
    ]
    tape: dict[str, list[TapeTrade]] = {}
    points: dict[str, list[LinePoint]] = {}
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        if covered:
            tape = await load_tape(session, mints=covered, end_time=boundary)
        # T4.10: the photos the lines may read — received by the close, like the tape.
        points = await load_line_points(
            session, mints=[t.mint for t in tracked_set], end_time=boundary
        )
    rows: list[FeatureRow] = []
    for tracked in tracked_set:
        minute, absence = _tape_inputs(ctx, tracked, boundary, tape)
        rows.append(
            build_row(
                MinuteInputs(
                    mint=tracked.mint,
                    end_time=boundary,
                    created_at=tracked.created_at,
                    initial_real_token_reserves=tracked.initial_real_token_reserves,
                    snapshot=observations.get(tracked.mint),
                    absence_reason=absences.get(tracked.mint, NOT_POLLED),
                    holders=holders_for(_readings(ctx, tracked.mint), end_time=boundary),
                    tape=minute,  # type: ignore[arg-type]
                    tape_absence_reason=absence,
                    line_points=points.get(tracked.mint, []),
                    board=board_standing(board_rows, mint=tracked.mint, end_time=boundary),
                ),
                features_version=ctx.config.features_version,
            )
        )
    if rows or board_rows:
        rows = await _insert_features_resiliently(ctx, rows)
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await insert_board_minutes(session, board_rows)
            await _record_uncovered(ctx, session, boundary, rows)
    covered_rows = sum(1 for row in rows if row.coverage > 0)
    meme_features_rows_total.labels(coverage="covered").inc(covered_rows)
    meme_features_rows_total.labels(coverage="uncovered").inc(len(rows) - covered_rows)
    if ctx.sources is not None:
        # T4.2e: the minute's coverage as the heartbeat reports it — rows with a
        # tape and rows with a progress, over the rows actually written.
        ctx.sources.record_fold(
            boundary,
            rows=len(rows),
            with_tape=sum(1 for row in rows if row.tape_reason is None),
            with_progress=sum(1 for row in rows if row.progress_reason is None),
            with_tape_activity=sum(1 for row in rows if row.tape_source == ACTIVITY_1M),
        )
    return rows


async def _insert_features_resiliently(
    ctx: RadarContext, rows: list[FeatureRow]
) -> list[FeatureRow]:
    """One statement for the minute; if the schema refuses it, one row at a time.

    A single row the CHECKs reject (production, 12/09 10:40Z: a ``top10_share``
    above 1) must cost that row, not the minute and not the process — before this
    the ``IntegrityError`` climbed through the TaskGroup and restarted the worker
    once per minute. Returns the rows that were actually written, so the coverage
    bookkeeping downstream counts only what exists.
    """
    if not rows:
        return rows
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await insert_features(session, rows)
        return rows
    except IntegrityError:
        pass
    written: list[FeatureRow] = []
    for row in rows:
        try:
            async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                await insert_features(session, [row])
            written.append(row)
        except IntegrityError as exc:
            logger.warning(
                "meme_feature_row_rejected",
                mint=row.mint,
                end_time=row.end_time.isoformat(),
                error=str(exc.orig)[:200] if exc.orig is not None else str(exc)[:200],
            )
            meme_features_rows_total.labels(coverage="rejected").inc()
    return written


async def _record_uncovered(
    ctx: RadarContext, session: AsyncSession, boundary: datetime, rows: list[FeatureRow]
) -> None:
    """A minute in which *nothing* was observed is a hole in the whole stream."""
    if not rows or any(row.coverage > 0 for row in rows):
        return
    await record_gap(
        session,
        GapRow(
            stream=FEATURES_STREAM,
            gap_start=boundary - timedelta(minutes=1),
            gap_end=boundary,
            reason="insufficient_coverage",
            detail={"tracked": len(rows)},
        ),
    )
    meme_gaps_total.labels(stream=FEATURES_STREAM, reason="insufficient_coverage").inc()
    if ctx.sources is not None:
        ctx.sources.gaps_60s.add(boundary)
