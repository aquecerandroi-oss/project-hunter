"""The rows and the two on-demand reads behind one admission's
:class:`~hunter_risk_meme.MemeContext` (T4.45).

Split out of ``entries.py`` when the executor stopped decaring a coin unreadable
just because the radar had not written the row yet. Both reads exist for the same
measured reason (16/09/2026, 58 real orders, **0** fills): 36 of the 39 in-window
orders were refused ``bundled_share_unmeasurable`` and 27 ``creator_flow_unknown``
— not because the answers were bad, but because they did not exist **yet** at the
instant the executor asked.

Both reads are *fallbacks for silence*, and both fail closed:

1. **the rug numbers** (``risk_read``) — only when ``meme_risk_snapshots`` holds
   nothing fresh for the mint; a failure leaves ``bundled_share`` ``None`` and
   check 11 refuses exactly as before;
2. **the creator's flow** (``creator_flow``) — when the 1-minute fold's
   ``creator_sold`` has not seen a sale (``NULL`` or, since T4.56, ``false``)
   *and* the creation instant's allocation was recorded (``0048``); a failure
   leaves the chain silent, so the tape's ``false`` fills in (``+1``) or, with
   the tape ``NULL`` too, check 10 refuses ``creator_flow_unknown`` as before.
   T4.56 (COVER, R56 §3.2): a chain read that says "sold" beats a tape
   ``false``, and the sighting is remembered per mint for 30 min
   (``ExecutorState.creator_sold_on_chain``) so the lagging tape never re-opens
   the coin; the verdict and every source that spoke go into ``creator_verdict``.

Nothing here can make a check pass on missing data: a read that fails produces the
same ``None`` the table produced, and the engine's own rule (``unavailable``
refuses) is untouched. What each read produced — or why it did not — is written
into the order's ``admission`` JSON, so a refusal and a pass are both auditable
from the row alone.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_executor.admission import context_from
from hunter_meme_executor.creator_flow import (
    CHAIN_FLOW_SOURCE,
    CreatorFlow,
    creator_flow_from_chain,
    needs_chain_creator_flow,
    resolve_creator_flow,
)
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import (
    OpenPosition,
    PendingAttempt,
    TokenContext,
    open_positions,
    participation_used_sol,
    pending_attempts,
    token_context,
)
from hunter_meme_executor.risk_read import read_risk_snapshot_on_demand

if TYPE_CHECKING:
    from hunter_meme_executor.chain import CurveRead
    from hunter_meme_executor.context import ExecutorContext
    from hunter_risk_meme import MemeContext

__all__ = ["AdmissionContext", "build_admission_context", "read_creator_flow"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    context: MemeContext
    positions: list[OpenPosition]
    pending: list[PendingAttempt]
    extras: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    """What goes into the order's ``admission`` JSON beside the decision: the
    provenance of anything this module read itself."""


async def read_creator_flow(
    ctx: ExecutorContext, token: TokenContext, mint: str, *, token_program: str, now: datetime
) -> tuple[CreatorFlow | None, dict[str, Any]]:
    """The creator's ATA for this mint, against his recorded allocation.

    One account read, ``confirmed`` (the commitment the whole admission decides
    on — §8.2: ``processed`` never decides), behind the same deadline as the REST
    read. The call is synchronous (``ChainReader`` is the submitter's client), so
    it runs in a thread; on timeout this coroutine stops waiting and the
    admission proceeds **without** the flow — the thread's late answer is
    discarded, never applied to a decision that already happened.
    """
    creator = token.creator
    initial = token.creator_initial_tokens
    if creator is None or initial is None:
        return None, {}
    timeout_s = ctx.config.risk_read_timeout_s
    try:
        async with asyncio.timeout(timeout_s):
            account = await asyncio.to_thread(ctx.chain.token_account, creator, mint, token_program)
    except (TimeoutError, asyncio.CancelledError):
        logger.warning("meme_executor_creator_ata_timeout", mint=mint, timeout_s=timeout_s)
        return None, {"creator_flow": {"source": CHAIN_FLOW_SOURCE, "read_failed": "timeout"}}
    except Exception as exc:
        logger.warning("meme_executor_creator_ata_failed", mint=mint, error_type=type(exc).__name__)
        return None, {
            "creator_flow": {"source": CHAIN_FLOW_SOURCE, "read_failed": type(exc).__name__}
        }
    flow = creator_flow_from_chain(
        initial_tokens=initial,
        # An account that does not exist holds nothing. With a recorded
        # allocation that is a dump, not an unmeasured balance (``creator_flow``).
        balance_subunits=account.amount if account.exists else 0,
        tolerance_pct=ctx.config.creator_sell_tolerance_pct,
        observed_at=now,
    )
    return flow, {"creator_flow": {**flow.as_json(), "ata_exists": str(account.exists).lower()}}


async def build_admission_context(
    ctx: ExecutorContext, mint: str, curve: CurveRead, *, now: datetime
) -> AdmissionContext:
    """Every row the admission needs, plus the two reads that keep a missing row
    from becoming a refusal the market did not earn."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        token = await token_context(session, mint, now=now)
        positions = await open_positions(session)
        pending = await pending_attempts(session)
        used = await participation_used_sol(session, mint, now=now)
    extras: dict[str, Any] = {}
    if token.bundled_share is None and await read_risk_snapshot_on_demand(ctx, mint, now=now):
        # The row is in the database now; re-read it rather than hand-building a
        # context from the response, so the admission sees exactly what it would
        # have seen had the radar written it a minute earlier.
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            token = await token_context(session, mint, now=now)
        extras["risk_read"] = {
            "source": "executor_on_demand",
            "bundled_share": "" if token.bundled_share is None else str(token.bundled_share),
        }
    flow: CreatorFlow | None = None
    memory = ctx.state.creator_sold_on_chain
    remembered = memory.seen_at(mint, now=now)
    # T4.56: a mint this process already saw dumped on chain is settled — no
    # second RPC read, and no tape ``false`` re-opens it (COVER, 17/09/2026).
    if remembered is None and needs_chain_creator_flow(token):
        flow, creator_extras = await read_creator_flow(
            ctx, token, mint, token_program=curve.token_program, now=now
        )
        extras.update(creator_extras)
        if flow is not None and flow.sold:
            memory.remember(mint, flow.observed_at)
    verdict = resolve_creator_flow(
        tape_sold=token.creator_sold, flow=flow, remembered_at=remembered
    )
    extras["creator_verdict"] = verdict.as_json()
    return AdmissionContext(
        context=context_from(
            mint,
            token,
            participation_used_sol=used,
            now=now,
            creator_flow=flow,
            creator_sold_remembered_at=remembered,
        ),
        positions=positions,
        pending=pending,
        extras=extras,
    )
