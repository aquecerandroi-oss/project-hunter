"""The periodic loops of the curve: poll, reconcile, fold, prune.

- **poll** spends the 60 requests/60 s of ``frontend-api-v3.pump.fun`` on the
  tracked set in the declared priority (``tracker.py``: open paper bets, final
  reads of finished curves, the ``graduating`` board, the ``new`` board, the
  young tier, the rest — least recently polled first inside each). Whatever the
  budget does not reach is written as a ``meme_ingest_gaps`` row — one row per
  cycle naming the count, not one per mint, because a hundred rows saying the
  same thing is noise, not evidence. A curve quoted in something other than SOL
  is dropped from the set on the first refusal (T4.2c: it cost 2–4 requests a
  minute for a reading the adapter will never produce);
- **reconcile** reads the top-K tracked mints by market cap from the chain. The
  REST mirror is undocumented and best effort (T4-MEME-RADAR.md §2: never a single
  source of truth), so the mints where being wrong costs most are checked against
  the RPC — and both readings are kept, distinguished by
  ``meme_curve_snapshots.source``, rather than one overwriting the other;
- **fold** writes one ``meme_features_1m`` row per tracked mint per closed minute
  (``fold.py``, since T4.2c with the boards and the tape), with a NULL and a
  reason wherever a source cannot answer;
- **prune** applies ``MEME_RETENTION_DAYS`` to ``meme_tokens`` — the one table
  retention cannot prune by dropping a partition — in batches, behind the declared
  ``app.meme_retention`` marker.

Every loop is a plain ``while True`` with its own sleep, supervised by the
``TaskGroup`` in ``main.py``: a raised exception takes the process down rather than
leaving a radar that looks alive and collects nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.normalize import UnsupportedQuote
from hunter_meme_worker.config import CURVE_STREAM
from hunter_meme_worker.features import (
    NOT_POLLED,
    RATE_LIMITED,
    UNSUPPORTED_QUOTE,
    CurveObservation,
    FeatureRow,
)
from hunter_meme_worker.fold import fold_minute
from hunter_meme_worker.metrics import (
    meme_budget_skipped_total,
    meme_gaps_total,
    meme_polls_total,
    meme_tokens_pruned_total,
    meme_tracked_mints,
)
from hunter_meme_worker.repo import (
    GapRow,
    SnapshotRow,
    TokenRow,
    insert_snapshot,
    prune_tokens,
    record_gap,
    upsert_token,
)
from hunter_meme_worker.repo_tape import open_bet_mints
from hunter_meme_worker.sources import PUMPFUN_REST, SOLANA_RPC
from hunter_meme_worker.tracker import TIER_OPEN_BET, TrackedMint

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.models import NormalizedCurveState
    from hunter_meme_worker.context import RadarContext

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
BUDGET_REASON = "budget_exhausted"


def snapshot_row(state: NormalizedCurveState) -> SnapshotRow:
    """A normalized reading -> one row. ``mcap_sol`` is not here: the database
    generates it, so no producer can write a market cap that disagrees with the
    reserves next to it."""
    return SnapshotRow(
        observed_at=state.observed_at,
        mint=state.mint,
        source=state.source,
        virtual_sol_reserves=state.virtual_sol_reserves,
        virtual_token_reserves=state.virtual_token_reserves,
        real_sol_reserves=state.real_sol_reserves,
        real_token_reserves=state.real_token_reserves,
        total_supply=state.total_supply,
        complete=state.complete,
        slot=state.slot,
        commitment=state.commitment,
        mayhem_enabled=state.mayhem_enabled,
        mayhem_state=state.mayhem_state,
        mayhem_mode=state.mayhem_mode,
    )


def token_row_from_curve(state: NormalizedCurveState) -> TokenRow:
    """What a curve reading teaches the dimension — including, **once**, the
    progress denominator and, once, ``completed_at``.

    ``initial_real_token_reserves`` is only claimed when ``real_sol_reserves`` is
    zero: a curve nobody has bought yet is the one moment its real token reserve
    *is* the initial one. That is an observation (T4-MEME-RADAR.md §3), not the
    793,1 M constant blogs quote — and when the radar never sees that moment, the
    denominator stays unknown and progress is NULL with ``denominator_unknown``.
    """
    untouched = state.real_sol_reserves == 0 and not state.complete
    return TokenRow(
        mint=state.mint,
        first_seen_source=state.source,
        first_seen_at=state.observed_at,
        last_seen_at=state.observed_at,
        total_supply=state.total_supply,
        initial_real_token_reserves=state.real_token_reserves if untouched else None,
        mayhem_enabled=state.mayhem_enabled,
        mayhem_mode=state.mayhem_mode,
        mayhem_state=state.mayhem_state,
        completed_at=state.observed_at if state.complete else None,
    )


async def _persist_reading(ctx: RadarContext, state: NormalizedCurveState) -> None:
    """One transaction: the snapshot, what it teaches the token, and the tracker."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await insert_snapshot(session, snapshot_row(state))
        await upsert_token(session, token_row_from_curve(state))
    tracked = ctx.tracker.get(state.mint)
    ctx.tracker.observe(
        TrackedMint(
            mint=state.mint,
            first_seen_at=tracked.first_seen_at if tracked else state.observed_at,
            created_at=tracked.created_at if tracked else None,
            bonding_curve=tracked.bonding_curve if tracked else None,
            mayhem_state=state.mayhem_state,
            initial_real_token_reserves=(
                state.real_token_reserves
                if state.real_sol_reserves == 0 and not state.complete
                else None
            ),
            complete=state.complete,
            mcap_sol=state.market_cap_sol,
        )
    )
    ctx.tracker.mark_polled(state.mint, state.observed_at, mcap_sol=state.market_cap_sol)
    ctx.state.observe(
        state.mint,
        CurveObservation(
            observed_at=state.observed_at,
            source=state.source,
            real_token_reserves=state.real_token_reserves,
            mcap_sol=state.market_cap_sol,
            complete=state.complete,
        ),
    )
    if ctx.sources is not None:
        name = SOLANA_RPC if state.source == "solana_rpc" else PUMPFUN_REST
        ctx.sources[name].record_ok(observed_at=state.observed_at, received_at=state.received_at)
        ctx.sources.record_snapshot(observed_at=state.observed_at, received_at=state.received_at)


async def refresh_open_bets(ctx: RadarContext) -> frozenset[str]:
    """The Lab's open bets, from the rows — the top of every priority list."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        ctx.state.open_bets = await open_bet_mints(session)
    return ctx.state.open_bets


async def poll_once(ctx: RadarContext) -> int:
    """One pass of the REST budget. Returns how many curves were read."""
    now = utcnow()
    aged_out, capped = ctx.tracker.prune(now)
    meme_tracked_mints.set(len(ctx.tracker))
    open_bets = await refresh_open_bets(ctx)
    plan = ctx.tracker.plan(
        now,
        ctx.config.rest_budget_per_minute,
        boosted={mint: TIER_OPEN_BET for mint in open_bets},
    )
    read = 0
    for mint in plan.selected:
        try:
            state = await ctx.curves.get_curve_state(mint)
        except UnsupportedQuote:
            ctx.tracker.mark_quote_unsupported(mint)
            ctx.state.absences[mint] = UNSUPPORTED_QUOTE
            meme_polls_total.labels(source="pumpfun_rest", outcome="unsupported_quote").inc()
            _spent(ctx, now, "unsupported_quote")
            logger.info("meme_curve_quote_unsupported", mint=mint)
            continue
        except Exception as exc:  # one mint's failure is not the cycle's
            ctx.state.absences.setdefault(mint, RATE_LIMITED)
            meme_polls_total.labels(source="pumpfun_rest", outcome="error").inc()
            _spent(ctx, now, "rate_limited" if isinstance(exc, RateLimited) else type(exc).__name__)
            logger.warning("meme_curve_poll_failed", mint=mint, error=str(exc))
            continue
        await _persist_reading(ctx, state)
        meme_polls_total.labels(source="pumpfun_rest", outcome="ok").inc()
        read += 1
    for mint in plan.skipped:
        ctx.state.absences.setdefault(mint, NOT_POLLED)
    if plan.skipped or capped:
        await _record_budget_gap(ctx, now, plan.skipped_count, len(capped), len(aged_out))
    return read


def _spent(ctx: RadarContext, at: datetime, error: str) -> None:
    if ctx.sources is not None:
        ctx.sources[PUMPFUN_REST].record_spent(at)
        ctx.sources[PUMPFUN_REST].record_error(at, error)


async def _record_budget_gap(
    ctx: RadarContext, now: datetime, skipped: int, capped: int, aged_out: int
) -> None:
    """One row per cycle, not one per mint: the count is the fact."""
    meme_budget_skipped_total.inc(skipped + capped)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await record_gap(
            session,
            GapRow(
                stream=CURVE_STREAM,
                gap_start=now - timedelta(seconds=ctx.config.poll_cycle_s),
                gap_end=now,
                reason=BUDGET_REASON,
                detail={
                    "skipped": skipped,
                    "evicted_by_cap": capped,
                    "aged_out": aged_out,
                    "tracked": len(ctx.tracker),
                    "budget": ctx.config.rest_budget_per_minute,
                },
            ),
        )
    meme_gaps_total.labels(stream=CURVE_STREAM, reason=BUDGET_REASON).inc()
    if ctx.sources is not None:
        ctx.sources.gaps_60s.add(now)


async def reconcile_once(ctx: RadarContext) -> int:
    """Read the top-K by market cap from the chain. Both readings are kept."""
    read = 0
    for mint in ctx.tracker.top_by_mcap(ctx.config.rpc_top_k):
        tracked = ctx.tracker.get(mint)
        if tracked is None or tracked.bonding_curve is None:
            # The RPC reads an *account*, so a mint whose bonding curve address we
            # never observed cannot be reconciled. Declared, not guessed: deriving
            # the PDA is T4.2b's job and the adapter refuses to guess it either.
            continue
        try:
            state = await ctx.chain.get_curve_state(mint, tracked.bonding_curve)
        except Exception as exc:
            meme_polls_total.labels(source="solana_rpc", outcome="error").inc()
            if ctx.sources is not None:
                ctx.sources[SOLANA_RPC].record_error(utcnow(), type(exc).__name__)
            logger.warning("meme_chain_read_failed", mint=mint, error=str(exc))
            continue
        await _persist_reading(ctx, state)
        meme_polls_total.labels(source="solana_rpc", outcome="ok").inc()
        read += 1
    return read


def minute_end(now: datetime) -> datetime:
    """The instant the minute that contains ``now`` began — i.e. the end of the
    minute before it, which is the one that has actually closed."""
    return now.replace(second=0, microsecond=0)


async def fold_once(ctx: RadarContext) -> list[FeatureRow]:
    """Fold the closed minute if one has closed since the last fold."""
    boundary = minute_end(utcnow())
    if ctx.state.last_folded_minute is not None and boundary <= ctx.state.last_folded_minute:
        return []
    if ctx.state.last_folded_minute is None:
        # First boundary this process sees: record it and fold from the next one.
        # Folding now would write a minute we only watched part of, and coverage
        # would claim a completeness the process cannot honestly report.
        ctx.state.last_folded_minute = boundary
        return []
    rows = await fold_minute(ctx, boundary)
    ctx.state.last_folded_minute = boundary
    return rows


async def prune_once(ctx: RadarContext) -> int:
    """Apply ``MEME_RETENTION_DAYS`` to the dimension, in batches."""
    cutoff = utcnow() - timedelta(days=ctx.config.retention_days)
    total = 0
    while True:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            deleted = await prune_tokens(session, cutoff=cutoff, batch=ctx.config.retention_batch)
        total += deleted
        if deleted < ctx.config.retention_batch:
            break
    if total:
        meme_tokens_pruned_total.inc(total)
        logger.info("meme_tokens_pruned", rows=total, cutoff=cutoff.isoformat())
    return total


async def forever[ContextT](
    name: str,
    interval_s: float,
    step: Callable[[ContextT], Awaitable[object]],
    ctx: ContextT,
) -> None:
    """Run one step on a fixed cadence until cancelled.

    A failure is **not** swallowed: it is logged and re-raised, so the TaskGroup in
    ``main.py`` takes the process down instead of leaving a radar whose ``/ready``
    is green and whose collection stopped hours ago.
    """
    while True:
        try:
            await step(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("meme_loop_failed", loop=name)
            raise
        await asyncio.sleep(interval_s)
