"""The identity sweep: ``GET /coins`` sorted by creation, not by mint.

T4.97/R80 (`.claude/state/notes-R80.md` §1, `KB-0160`): ``frontend-api-v3.pump.fun``
``GET /coins/{mint}`` — the only call ``poll_once`` (``collect.py``) spent on a
mint's ``twitter``/``telegram``/``website`` — answers ``404 Cannot GET`` for
**every** mint tried live on 2026-09-26, old and freshly created (a brand-new one
from the listing below, and one already tracked for hours). ``meme_curve_snapshots``
shows the last successful ``pumpfun_rest`` row at 2026-09-25 17:13:16Z — the last
*observed* success, not necessarily the instant the route broke — with no ``429``/
``418`` in the logs available for this diagnosis. This reads as a by-mint route
pump.fun withdrew or broke, not a rate limit; a single ``404`` does not by itself
prove the route is gone for good (RFC 9110 §15.5.5), so ``poll_once`` is left
retrying it unchanged rather than assumed dead here. The chain loop (T4.2f) still
answers every tracked curve's reserves once a minute, so market cap and marks were
not degraded by this — only identity, because since T4.2f the REST poll narrows to
identity-only reads while the chain is healthy (``tracker.needs_rest``), and every
one of those reads has failed since.

``GET /coins?sort=created_timestamp&order=DESC`` was not affected and answers the
identical raw shape (confirmed against the same live capture, T4.97's own fixture)
— including the identity fields a by-mint read would have. One call now answers up
to 50 mints' identity for the request a single by-mint read used to cost one mint.

Restricted to mints the tracker already knows (the WS discovery loop adds a mint
within milliseconds of its ``create`` frame — ``discovery.py``) and that still
:meth:`MintTracker.needs_rest`. **Known gap** (Astra's review of this task): the
tracker evicts by age, cap and completion, so this is not yet "identity collection
independent of tracking" — a mint the tracker has already dropped stays without
identity even if this sweep's page still names it. It is a recovery of the
existing per-mint identity read's *value*, at a fraction of its cost, not the
"instant of its own, independent of an open bet" instrumentation R80 asks for as
its own next step; ``poll_once``'s per-mint identity reads are left running and
still spend budget failing on mints outside this sweep's newest-50 page, which
this task also does not fix (a per-source circuit breaker on
``consecutive_failures`` — ``source_stats.py`` — is the natural next step, left
undone here to keep this diff to the one operational recovery).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.collect import persist_reading
from hunter_meme_worker.metrics import meme_polls_total
from hunter_meme_worker.sources import PUMPFUN_REST

if TYPE_CHECKING:
    from hunter_meme_worker.context import RadarContext

logger = get_logger(__name__)

#: 1..50 (the endpoint's own ceiling, ``rest.py``): the widest sweep the one
#: request can carry.
IDENTITY_SWEEP_LIMIT = 50

#: Three calls a minute on the one bucket this client shares with every other
#: pump.fun REST call (``rest.py``'s 60/60 s) — cheap beside the per-mint reads
#: it stands in for, and frequent enough that a mint created between two sweeps
#: still gets a chance at the next one (best effort: only the newest 50).
IDENTITY_SWEEP_CYCLE_S = 20.0

__all__ = ["IDENTITY_SWEEP_CYCLE_S", "IDENTITY_SWEEP_LIMIT", "identity_sweep_once"]


async def identity_sweep_once(ctx: RadarContext) -> int:
    """One ``/coins`` listing call; returns how many identity reads it wrote.

    One HTTP request however many mints it feeds ``persist_reading`` for, so
    the source's own budget/success bookkeeping (``record_ok``) is charged
    once here — never once per mint (``count_request=False`` below) — the
    same discipline ``persist_reading`` already applies to the Mayhem batch.
    """
    now = utcnow()
    try:
        states = await ctx.curves.list_recent(limit=IDENTITY_SWEEP_LIMIT)
    except Exception as exc:  # the listing call itself failed — next cycle retries
        if ctx.sources is not None:
            ctx.sources[PUMPFUN_REST].record_spent(now)
            ctx.sources[PUMPFUN_REST].record_error(now, str(exc)[:200])
        meme_polls_total.labels(source="pumpfun_rest", outcome="error").inc()
        logger.warning("meme_identity_sweep_failed", error=str(exc))
        return 0
    if ctx.sources is not None:
        ctx.sources[PUMPFUN_REST].record_ok(observed_at=now, received_at=now)
    written = 0
    for state in states:
        tracked = ctx.tracker.get(state.mint)
        if tracked is None or not ctx.tracker.needs_rest(tracked, now, {}):
            continue
        await persist_reading(ctx, state, count_request=False)
        meme_polls_total.labels(source="pumpfun_rest", outcome="ok").inc()
        written += 1
    return written
