"""The Mayhem loop (T4.2e): once a minute, every tracked Mayhem mint still
without a denominator has its four accounts read from the chain in one
``getMultipleAccounts`` per 25 mints, reconciled
(``hunter_exchanges.pumpfun.mayhem_state``) and — when the identity holds and
the ``/global-params`` record is known — written as
``initial_real_token_reserves`` with ``progress_denominator_source =
mayhem_state`` (``0025``). The curve account of the same finalized slot is
persisted as a ``solana_rpc`` snapshot on the way (``collect.persist_reading``),
so the minute's fold sees a chain reading of the coin too.

**Budget.** The public RPC allows ~10 req/s and 40 calls per method per 10 s;
a batch of 25 mints is one call, and a mint leaves the pending set the moment
its denominator is written (write-once in ``meme_tokens``, remembered by the
tracker), so the loop costs about one call per 25 *new* Mayhem coins — not one
per tracked coin per minute. A refusal (``not_mayhem``, ``identity_failed``,
``reserve_above_record``, ``no_record``…) is counted by name in the heartbeat
and retried next cycle: an agent flow that does not reconcile is not a number.

**Why the denominator is the record's, in one line:** on the coin this loop
was built on, ``822 644 036,902123 = 793 100 000 + 29 544 036,902123`` — the
curve's reserve is the record's initial plus the agent's net sells, to the
subunit (``docs/PUMPFUN-ONCHAIN.md`` §3.5).
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.normalize import curve_state_from_rpc_account
from hunter_meme_worker.collect import persist_reading
from hunter_meme_worker.graduation import mayhem_denominator
from hunter_meme_worker.metrics import meme_polls_total
from hunter_meme_worker.repo import TokenRow, upsert_token
from hunter_meme_worker.sources import SOLANA_RPC

if TYPE_CHECKING:
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.tracker import MintTracker, TrackedMint

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
NO_RECORD = "no_record"
RESERVE_ABOVE_RECORD = "reserve_above_record"


@dataclass(frozen=True, slots=True)
class MayhemReport:
    pending: int
    requested: int
    written: int
    calls: int
    refused: dict[str, int] = field(default_factory=dict[str, int])


def pending_mayhem(tracker: MintTracker) -> list[TrackedMint]:
    """Tracked mints the site calls Mayhem (``mayhem_state`` set) that have no
    denominator yet — newest first, the tracker's own order."""
    return [
        tracked
        for tracked in tracker.snapshot()
        if tracked.initial_real_token_reserves is None
        and tracked.mayhem_state is not None
        and not tracked.quote_unsupported
    ]


async def mayhem_once(ctx: RadarContext) -> MayhemReport:
    """One batch of the pending Mayhem mints against the chain."""
    pending = pending_mayhem(ctx.tracker)
    if ctx.sources is not None:
        ctx.sources.mayhem_pending = len(pending)
    if not pending:
        return MayhemReport(pending=0, requested=0, written=0, calls=0)
    mints = [tracked.mint for tracked in pending[: ctx.config.mayhem_batch]]
    now = utcnow()
    try:
        batch = await ctx.chain.get_mayhem_flows(mints)
    except Exception as exc:  # one failed batch is a counted absence, not a crash
        meme_polls_total.labels(source="solana_rpc", outcome="error").inc()
        if ctx.sources is not None:
            ctx.sources[SOLANA_RPC].record_spent(now)
            ctx.sources[SOLANA_RPC].record_error(now, type(exc).__name__)
        logger.warning("meme_mayhem_read_failed", mints=len(mints), error=str(exc)[:200])
        return MayhemReport(pending=len(pending), requested=len(mints), written=0, calls=0)
    refused: Counter[str] = Counter(batch.refused.values())
    if ctx.sources is not None and batch.calls:
        ctx.sources[SOLANA_RPC].record_ok(observed_at=now, received_at=now, count=batch.calls)
    written = 0
    for mint, flow in batch.flows.items():
        tracked = ctx.tracker.get(mint)
        if tracked is None:
            continue
        state = curve_state_from_rpc_account(mint, flow.curve).model_copy(
            update={"slot": flow.slot, "commitment": flow.commitment}
        )
        await persist_reading(ctx, state, count_request=False)
        meme_polls_total.labels(source="solana_rpc", outcome="ok").inc()
        params = None
        if ctx.params is not None:
            params = await ctx.params.resolve(tracked.created_at, now=now)
        denominator = mayhem_denominator(flow, params)
        if denominator.value is None:
            refused[NO_RECORD if params is None else RESERVE_ABOVE_RECORD] += 1
            continue
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await upsert_token(
                session,
                TokenRow(
                    mint=mint,
                    first_seen_source=state.source,
                    first_seen_at=state.observed_at,
                    last_seen_at=state.observed_at,
                    initial_real_token_reserves=denominator.value,
                    progress_denominator_source=denominator.source,
                    mayhem_enabled=True,
                    total_supply=state.total_supply,
                ),
            )
        current = ctx.tracker.get(mint) or tracked
        ctx.tracker.observe(
            dataclasses.replace(current, initial_real_token_reserves=denominator.value)
        )
        written += 1
    if ctx.sources is not None:
        ctx.sources.mayhem_written_60s.add(now, written)
        ctx.sources.mayhem_refused_1h.add(now, sum(refused.values()))
        ctx.sources.mayhem_pending = len(pending) - written
    if refused:
        logger.info("meme_mayhem_refused", reasons=dict(refused), slot=batch.slot)
    return MayhemReport(
        pending=len(pending),
        requested=len(mints),
        written=written,
        calls=batch.calls,
        refused=dict(refused),
    )


__all__ = ["NO_RECORD", "RESERVE_ABOVE_RECORD", "MayhemReport", "mayhem_once", "pending_mayhem"]
