"""T4.45 — when the rug read the admission needs has not landed, the executor
reads it **itself**, once, with a hard deadline.

**The measurement** (16/09/2026, R5 +
``obsidian/03-TRADING/Meme/Balanco-2026-09-16-mesa-real.md``): the
``meme_risk_snapshots`` row of a mint landed a median **103 s after** the
decision that needed it, and 36 of the 39 in-window real orders had no bundle
measured. T4.28g answered that by **waiting** (``risk_snapshot_pending``): better
than burning the proposal, but the desk's proposal lives 180 s and the robot's
own window is 60 s, so waiting often means not trading a coin whose number was
one HTTP call away.

This module makes the executor the second reader of the very endpoint the radar
polls (``GET /in-memory-coin/{mint}``), on the admission path only, and persists
the answer through **the same writer** the radar uses
(``hunter_core.db.meme_risk_snapshots``) so the row is indistinguishable except
for its ``source``.

**What it deliberately does not do:**

- it never lets a failure pass anything. A timeout, an HTTP error, a rate limit
  or a reading that came back **without** ``bundled_share`` all return ``False``
  and the admission goes on to refuse ``bundled_share_unmeasurable`` exactly as
  before (§4, check 11). "Never a pass on missing data" is the whole point;
- it never retries in a loop. One attempt per mint per
  :data:`ON_DEMAND_MIN_INTERVAL_S`, counted in memory **including failures** —
  without that, a mint the endpoint refuses would be re-read every second by the
  1 s entry loop, which is how a shared 60 req/min budget disappears;
- it never blocks the loop past :data:`DEFAULT_TIMEOUT_S`. The entry loop also
  owns exits and the kill-switch re-read; a slow third party must cost one
  admission, not the process;
- it never reads while the kill switch blocks entries. The answer would be
  discarded by check 1 anyway, and the budget it spends is the radar's too.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from hunter_core.db.meme_risk_snapshots import insert_risk_snapshot
from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import RISK_SNAPSHOT_MAX_AGE_S

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.board_models import NormalizedRiskSnapshot
    from hunter_meme_executor.context import ExecutorContext, ExecutorState

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ON_DEMAND_MIN_INTERVAL_S",
    "ON_DEMAND_SOURCE",
    "RiskSource",
    "due_for_on_demand_read",
    "ensure_snapshots",
    "fetch_risk_snapshot",
    "read_risk_snapshot_on_demand",
]

logger = get_logger(__name__)

DEFAULT_TIMEOUT_S = 1.5
"""``MEME_RISK_READ_TIMEOUT_S``. Chosen against the clock that matters: the desk
proposes 3–10 s before the executor sees the row and the robot's own window is
60 s, so a second and a half is affordable; ten would not be, because the same
loop owes the exits their 5 s tick."""

ON_DEMAND_MIN_INTERVAL_S = RISK_SNAPSHOT_MAX_AGE_S
"""At most one on-demand read per mint per 600 s — the same window the admission
accepts a row for. A second read inside it could not change any answer (the first
row is still fresh), so it would be spend without information."""

ON_DEMAND_SOURCE = "indexer_rest:/in-memory-coin:executor_on_demand"
"""Same endpoint, same parser, a reader that names itself. ``meme_risk_snapshots``
only constrains ``source`` to be non-empty, and no consumer filters on it
(checked across the repo), so this row is read by the admission exactly like the
radar's — it just says who asked. The closed list of
``meme_tokens.pool_created_source`` is **not** touched: the executor writes the
snapshot row and nothing else (the radar's ``_pool_row`` path is the worker's)."""


class RiskSource(Protocol):
    """``AdvancedIndexerClient`` — the adapter the radar's ``RiskReader`` drives."""

    async def get_risk_snapshot(self, mint: str) -> NormalizedRiskSnapshot: ...


def due_for_on_demand_read(
    state: ExecutorState, mint: str, *, now: datetime, min_interval_s: float
) -> bool:
    """Has this process not already tried this mint recently?

    In memory, and that is deliberate: the persisted row cannot bound a
    **failed** read (it does not exist), and the failure mode being bounded here
    is a 1 s loop hammering an endpoint that is down. A restart forgets — one
    extra call per mint after a restart, which is the cheap side of the trade.
    """
    last = state.risk_read_attempts.get(mint)
    return last is None or (now - last) >= timedelta(seconds=min_interval_s)


def _forget_old_attempts(state: ExecutorState, *, now: datetime, min_interval_s: float) -> None:
    """The book of attempts is bounded by its own window, not by the number of
    mints the desk ever proposed (an executor runs for days)."""
    cutoff = now - timedelta(seconds=min_interval_s)
    stale = [mint for mint, at in state.risk_read_attempts.items() if at < cutoff]
    for mint in stale:
        del state.risk_read_attempts[mint]


async def fetch_risk_snapshot(
    client: RiskSource, mint: str, *, timeout_s: float
) -> NormalizedRiskSnapshot | None:
    """One read, or ``None`` — never an exception out of this function.

    Every failure is the same answer to the caller ("no fresh reading"), because
    every failure has the same consequence: the admission refuses by name. The
    kind of failure is logged and counted, not branched on.
    """
    try:
        async with asyncio.timeout(timeout_s):
            return await client.get_risk_snapshot(mint)
    except (TimeoutError, asyncio.CancelledError):
        logger.warning("meme_executor_risk_read_timeout", mint=mint, timeout_s=timeout_s)
        return None
    except Exception as exc:
        logger.warning("meme_executor_risk_read_failed", mint=mint, error_type=type(exc).__name__)
        return None


async def read_risk_snapshot_on_demand(ctx: ExecutorContext, mint: str, *, now: datetime) -> bool:
    """Read and persist the mint's rug numbers now; ``True`` only when the row
    that landed carries the ``bundled_share`` check 11 needs.

    ``False`` means "decide with what the tables already hold", which is a
    refusal by name for a mint whose bundle is unmeasured — the pre-T4.45
    behaviour, unchanged.
    """
    client = ctx.risk_client
    state = ctx.state
    if client is None or ctx.kill.blocks_entries:
        # A switch that blocks entries refuses this candidate by name a few lines
        # later (check 1), so the read could only be thrown away - and the
        # ``/in-memory-coin`` budget it spends is shared with the radar, which is
        # still marking the open positions this switch does **not** stop.
        return False
    _forget_old_attempts(state, now=now, min_interval_s=ON_DEMAND_MIN_INTERVAL_S)
    if not due_for_on_demand_read(state, mint, now=now, min_interval_s=ON_DEMAND_MIN_INTERVAL_S):
        return False
    state.risk_read_attempts[mint] = now
    snapshot = await fetch_risk_snapshot(client, mint, timeout_s=ctx.config.risk_read_timeout_s)
    if snapshot is None:
        state.risk_reads_on_demand_failed += 1
        return False
    stamped = snapshot.model_copy(update={"source": ON_DEMAND_SOURCE})
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await insert_risk_snapshot(session, stamped)
    state.risk_reads_on_demand += 1
    if stamped.bundled_share is None:
        # A reading that answered without the bundle is still evidence (it is
        # persisted), but it is not the input check 11 asks for. Reporting it as
        # measured would put back the refusal this module exists to remove.
        state.risk_reads_on_demand_failed += 1
        logger.warning("meme_executor_risk_read_without_bundle", mint=mint)
        return False
    logger.info(
        "meme_executor_risk_read_on_demand",
        mint=mint,
        bundled_share=str(stamped.bundled_share),
        dev_share="" if stamped.dev_share is None else str(stamped.dev_share),
    )
    return True


async def ensure_snapshots(
    ctx: ExecutorContext, mints: Sequence[str], measured: frozenset[str], *, now: datetime
) -> frozenset[str]:
    """``measured`` plus whichever of ``mints`` this call could read on the spot.

    Stage 1's read-first path (T4.45): the planner is first asked who it *would*
    open if the rug read were there, and only those mints are read. Spending the
    call on a proposal that is too old, on a busy mint or on one in refusal
    cooldown would buy a number nothing is going to use — and the endpoint's
    budget is shared with the radar.
    """
    added: set[str] = set()
    for mint in mints:
        if mint not in measured and await read_risk_snapshot_on_demand(ctx, mint, now=now):
            added.add(mint)
    return measured | added if added else measured
