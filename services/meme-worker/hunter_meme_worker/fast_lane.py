"""The fast lane (T4.16): every 15 s, the curve of every tracked mint younger
than five minutes from the chain — one ``getMultipleAccounts`` per 100 mints
plus one ``getBlockTime`` per slot, the same call and the same persistence
path as the minute loop (``chain.py`` → ``collect.persist_reading``) — and
then one ``meme_features_15s`` row per mint, folded from what had reached us
by the instant (``features_fast.build_fast_row``).

**Why.** The study of the 21 bets of 12/09 measured the entry: the gate read
closed minutes (``end_time <= now − 1 min``) and the fill waited for the next
photo, so a coin was bought 99–289 s after its birth and the dev had already
sold in 5 of 8 probes. A coin's first five minutes are where it lives or
dies; a minute is too coarse a clock for them. The public RPC allows it: 130
tracked mints are two calls a read, four reads a minute, eight calls — and
the young subset is smaller than that.

**Budget, declared.** ``fast_lane_max_age_s = 300`` bounds the subset;
``get_curve_states`` spends ≤ 2 ``getMultipleAccounts`` + ≤ 2 ``getBlockTime``
per read, ≤ 16 calls a minute on top of the minute loop's ~4; the RPC's own
per-method window (10/10 s, T4.2f) is respected by the client's spacing.
The heartbeat says ``fast_lane_mints``, ``fast_lane_reads_60s``,
``fast_lane_calls_60s``, ``fast_lane_cycle_s``.

**What a refusal teaches** is what it teaches the minute loop
(``chain.py``): ``unsupported_quote`` drops the mint, ``curve_emptied`` marks
it finished, the rest leaves the instant without a chain photo — and the
15-second row then says ``no_snapshot`` / ``too_few_points`` by name.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.rpc_curves import CURVE_EMPTIED, UNSUPPORTED_QUOTE
from hunter_meme_worker.activity import batch_minute
from hunter_meme_worker.collect import persist_reading
from hunter_meme_worker.features import UNSUPPORTED_QUOTE as UNSUPPORTED_QUOTE_REASON
from hunter_meme_worker.features_fast import Fast15sRow, FastInputs, build_fast_row
from hunter_meme_worker.features_tape import HoldersObservation, TapeTrade, tape_for
from hunter_meme_worker.metrics import meme_polls_total, meme_rows_total
from hunter_meme_worker.repo_fast import insert_fast_rows, load_fast_points
from hunter_meme_worker.repo_tape import load_tape
from hunter_meme_worker.sources import SOLANA_RPC

if TYPE_CHECKING:
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.tracker import MintTracker, TrackedMint

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"

__all__ = ["FastReport", "fast_once", "fold_fast", "young_mints"]


@dataclass(frozen=True, slots=True)
class FastReport:
    mints: int
    read: int
    calls: int
    rows: int
    duration_s: float = 0.0
    failed: bool = False


def young_mints(tracker: MintTracker, now: datetime, *, max_age_s: int) -> list[TrackedMint]:
    """Tracked mints with a **known** creation time younger than ``max_age_s``,
    still on the curve, quoted in SOL — newest first. A mint whose age is
    unknown is not young; it is unknown, and the minute loop reads it."""
    limit = timedelta(seconds=max_age_s)
    return [
        t
        for t in tracker.snapshot()
        if t.created_at is not None
        and not t.quote_unsupported
        and not t.finished
        and timedelta(0) <= now - t.created_at < limit
    ]


def _readings(ctx: RadarContext, mint: str) -> list[HoldersObservation]:
    readings: list[HoldersObservation] = []
    if ctx.boards is not None:
        readings.extend(ctx.boards.readings(mint))
    if ctx.risk is not None:
        readings.extend(ctx.risk.readings(mint))
    return readings


async def fold_fast(
    ctx: RadarContext, tracked: list[TrackedMint], *, as_of: datetime
) -> list[Fast15sRow]:
    """One ``meme_features_15s`` row per mint from what had reached us by ``as_of``."""
    if not tracked:
        return []
    mints = [t.mint for t in tracked]
    covered = [
        t.mint
        for t in tracked
        if ctx.trades is not None
        and (since := ctx.trades.coverage_for(t.mint, as_of)) is not None
        and since <= as_of
    ]
    tape: dict[str, list[TapeTrade]] = {}
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        points = await load_fast_points(session, mints=mints, as_of=as_of)
        if covered:
            tape = await load_tape(session, mints=covered, end_time=as_of)
    rows: list[Fast15sRow] = []
    for t in tracked:
        minute = None
        absence = UNSUPPORTED_QUOTE_REASON if t.quote_unsupported else "no_trade_feed"
        if ctx.trades is not None and not t.quote_unsupported:
            minute = tape_for(
                tape.get(t.mint, []),
                end_time=as_of,
                creator=t.creator,
                covered_since=ctx.trades.coverage_for(t.mint, as_of),
            )
            absence = ctx.trades.absence_reason(t.mint, at=as_of)
            if minute is None:  # T4.2g: the batch's 1m window, at most 60 s before the instant
                minute, absence = batch_minute(ctx, t.mint, at=as_of, absence=absence)
        rows.append(
            build_fast_row(
                FastInputs(
                    mint=t.mint,
                    as_of=as_of,
                    created_at=t.created_at,
                    initial_real_token_reserves=t.initial_real_token_reserves,
                    points=points.points.get(t.mint, []),
                    snapshot_source=points.newest_source.get(t.mint),
                    readings=_readings(ctx, t.mint),
                    tape=minute,
                    tape_absence_reason=absence,
                ),
                features_version=ctx.config.features_15s_version,
            )
        )
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await insert_fast_rows(session, rows)
    meme_rows_total.labels(table="meme_features_15s").inc(len(rows))
    return rows


async def fast_once(ctx: RadarContext) -> FastReport:
    """One read of the young subset from the chain, then one row per mint."""
    started = time.monotonic()
    now = utcnow()
    tracked = young_mints(ctx.tracker, now, max_age_s=ctx.config.fast_lane_max_age_s)
    if not tracked:
        _record(ctx, now, mints=0, read=0, calls=0, started=started)
        return FastReport(mints=0, read=0, calls=0, rows=0, duration_s=_elapsed(started))
    try:
        batch = await ctx.chain.get_curve_states([t.mint for t in tracked])
    except Exception as exc:  # the whole read: counted, the minute loop still covers
        meme_polls_total.labels(source="solana_rpc", outcome="error").inc()
        if ctx.sources is not None:
            ctx.sources[SOLANA_RPC].record_spent(now)
            ctx.sources[SOLANA_RPC].record_error(now, type(exc).__name__)
        logger.warning("meme_fast_lane_failed", mints=len(tracked), error=str(exc)[:200])
        return FastReport(
            mints=len(tracked), read=0, calls=0, rows=0, duration_s=_elapsed(started), failed=True
        )
    for mint, state in batch.states.items():
        if ctx.tracker.get(mint) is None:
            continue
        await persist_reading(ctx, state, count_request=False)
        meme_polls_total.labels(source="solana_rpc", outcome="ok").inc()
    for mint, reason in batch.refused.items():
        current = ctx.tracker.get(mint)
        if current is None:
            continue
        if reason == UNSUPPORTED_QUOTE:
            ctx.tracker.mark_quote_unsupported(mint)
            ctx.state.absences[mint] = UNSUPPORTED_QUOTE_REASON
        elif reason == CURVE_EMPTIED and not current.finished:
            ctx.tracker.observe(
                dataclasses.replace(current, complete=True, final_read_pending=True)
            )
    if ctx.sources is not None:
        ctx.sources[SOLANA_RPC].record_ok(
            observed_at=max((s.observed_at for s in batch.states.values()), default=now),
            received_at=now,
            count=batch.calls,
        )
    as_of = utcnow()
    rows = await fold_fast(
        ctx, young_mints(ctx.tracker, as_of, max_age_s=ctx.config.fast_lane_max_age_s), as_of=as_of
    )
    _record(
        ctx, now, mints=len(tracked), read=len(batch.states), calls=batch.calls, started=started
    )
    return FastReport(
        mints=len(tracked),
        read=len(batch.states),
        calls=batch.calls,
        rows=len(rows),
        duration_s=_elapsed(started),
    )


def _record(
    ctx: RadarContext, at: datetime, *, mints: int, read: int, calls: int, started: float
) -> None:
    if ctx.sources is not None:
        ctx.sources.record_fast_cycle(
            at, mints=mints, read=read, calls=calls, duration_s=_elapsed(started)
        )


def _elapsed(started: float) -> float:
    return round(time.monotonic() - started, 3)
