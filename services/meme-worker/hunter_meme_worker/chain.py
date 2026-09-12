"""The chain loop (T4.2f): once a minute, the curve of **every** tracked mint from
the chain — one ``getMultipleAccounts`` per 100 mints plus one ``getBlockTime``
per slot (``hunter_exchanges.pumpfun.rpc_curves``) — persisted through the same
path as a REST photo (``collect.persist_reading``): the ``solana_rpc`` snapshot
with ``slot``, ``commitment`` and the block time as ``observed_at``, the
denominator with its provenance, the completion signals, the tracker, the
minute's fold.

**Why.** After T4.2e the dominant reason a gate row had no progress was
``not_polled`` — 1 267 rows in 15 minutes: the REST mirror's 60 requests a
minute cannot photograph ~130 curves a minute. The chain can, in two calls
(467 ms and 187 ms live, ``t42f_rpc_curves_batch*_raw.json``), and the curve's
address is a pure function of the mint (140/140 against the mirror's own
``bonding_curve``), so a mint discovered by a board with no PumpPortal frame is
read like any other. The REST poll keeps only the identity reads
(``tracker.needs_rest``); when this loop fails, the poll's full plan is the
fallback (``RadarState.chain_covers``).

**What a refusal teaches.** ``unsupported_quote`` drops the mint from the set as
the REST refusal does (23 of 140 fresh coins are not SOL-quoted); ``curve_emptied``
— ``complete`` with every reserve zero — is the chain's own migration signal and
marks the mint finished with its final REST read pending; ``curve_not_found``
(a curve not yet finalized, or another program's coin) and ``malformed`` leave
the minute without a chain photo, ``insufficient_coverage`` unless the mirror
answered. A batch that fails as a whole is counted on the source and the REST
poll takes over next cycle; a ``RateLimited`` names every mint's absence.
"""

from __future__ import annotations

import dataclasses
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.rpc_curves import CURVE_EMPTIED, UNSUPPORTED_QUOTE
from hunter_meme_worker.collect import persist_reading
from hunter_meme_worker.features import INSUFFICIENT_COVERAGE, RATE_LIMITED
from hunter_meme_worker.features import UNSUPPORTED_QUOTE as UNSUPPORTED_QUOTE_REASON
from hunter_meme_worker.metrics import meme_polls_total
from hunter_meme_worker.sources import SOLANA_RPC

if TYPE_CHECKING:
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.tracker import MintTracker

logger = get_logger(__name__)

__all__ = ["ChainReport", "chain_mints", "chain_once"]


@dataclass(frozen=True, slots=True)
class ChainReport:
    tracked: int
    read: int
    calls: int
    refused: dict[str, int] = field(default_factory=dict[str, int])
    emptied: int = 0
    block_time_missing: int = 0
    duration_s: float = 0.0
    failed: bool = False


def chain_mints(tracker: MintTracker) -> list[str]:
    """Every tracked mint the chain can answer for — newest first."""
    return [t.mint for t in tracker.snapshot() if not t.quote_unsupported]


async def chain_once(ctx: RadarContext) -> ChainReport:
    """One photograph of the tracked set from the chain."""
    started = time.monotonic()
    now = utcnow()
    mints = chain_mints(ctx.tracker)
    if not mints:
        ctx.state.chain_ok_at = now
        return ChainReport(tracked=0, read=0, calls=0)
    try:
        batch = await ctx.chain.get_curve_states(mints)
    except Exception as exc:  # the whole batch: counted, and the REST poll takes over
        meme_polls_total.labels(source="solana_rpc", outcome="error").inc()
        limited = isinstance(exc, RateLimited)
        if ctx.sources is not None:
            ctx.sources[SOLANA_RPC].record_spent(now)
            ctx.sources[SOLANA_RPC].record_error(
                now, RATE_LIMITED if limited else type(exc).__name__
            )
        if limited:
            for mint in mints:
                ctx.state.absences.setdefault(mint, RATE_LIMITED)
        logger.warning("meme_chain_batch_failed", mints=len(mints), error=str(exc)[:200])
        return ChainReport(
            tracked=len(mints), read=0, calls=0, duration_s=_elapsed(started), failed=True
        )
    for mint, state in batch.states.items():
        if ctx.tracker.get(mint) is None:  # pruned while the call was in flight
            continue
        await persist_reading(ctx, state, count_request=False)
        meme_polls_total.labels(source="solana_rpc", outcome="ok").inc()
    refused: Counter[str] = Counter(batch.refused.values())
    emptied = 0
    for mint, reason in batch.refused.items():
        tracked = ctx.tracker.get(mint)
        if tracked is None:
            continue
        if reason == UNSUPPORTED_QUOTE:
            ctx.tracker.mark_quote_unsupported(mint)
            ctx.state.absences[mint] = UNSUPPORTED_QUOTE_REASON
            meme_polls_total.labels(source="solana_rpc", outcome="unsupported_quote").inc()
        elif reason == CURVE_EMPTIED:
            emptied += 1
            if not tracked.finished:
                ctx.tracker.observe(
                    dataclasses.replace(tracked, complete=True, final_read_pending=True)
                )
            ctx.state.absences.setdefault(mint, INSUFFICIENT_COVERAGE)
        else:
            ctx.state.absences.setdefault(mint, INSUFFICIENT_COVERAGE)
    ctx.state.chain_ok_at = now
    duration = _elapsed(started)
    if ctx.sources is not None:
        observed = max((s.observed_at for s in batch.states.values()), default=now)
        ctx.sources[SOLANA_RPC].record_ok(observed_at=observed, received_at=now, count=batch.calls)
        ctx.sources.record_chain_cycle(
            now,
            duration_s=duration,
            tracked=len(mints),
            read=len(batch.states),
            calls=batch.calls,
            refused=sum(refused.values()),
            block_time_missing=batch.block_time_missing,
        )
    if refused:
        logger.info("meme_chain_refused", reasons=dict(refused), slots=list(batch.slots))
    return ChainReport(
        tracked=len(mints),
        read=len(batch.states),
        calls=batch.calls,
        refused=dict(refused),
        emptied=emptied,
        block_time_missing=batch.block_time_missing,
        duration_s=duration,
    )


def _elapsed(started: float) -> float:
    return round(time.monotonic() - started, 3)
