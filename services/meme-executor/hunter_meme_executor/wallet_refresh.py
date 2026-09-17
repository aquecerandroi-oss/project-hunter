"""T4.51 — the wallet's balance is re-read on the kill-switch tick, not only
when an order happens.

Defect (17/09/2026): ``state.wallet_lamports``/``wallet_read_at`` were only
ever written inside ``entries.handle_candidate`` (T4.8), which does not run on
a tick with nothing to admit. With the desk quiet — every position closed —
the last write stood until the next order, hours later: ``hb:meme:executor``
published a balance and an equity from the instant the last position (DOPEY)
was still open, while the chain had already moved and every position was
closed. ``/meme/mesa`` and the two checks that read the heartbeat's numbers
(``wallet_over_max_sol``, the daily loss cap) inherited the same staleness.

This module is the second writer of those two fields, called every
``kill_switch_poll_s`` (10 s, ``main.kill_switch_once`` — a tick that already
runs with or without a candidate, same as the program-identity check it sits
next to). It never competes with the order-time write: both write the same
pair, whichever ran more recently wins, same as ``program_check_once`` and
``check_program_at_boot`` already do for the program identity.

Bounded like ``risk_read.py``'s on-demand read: one call, a hard deadline
(``MEME_WALLET_REFRESH_TIMEOUT_S``), never a retry loop inside this call (the
10 s tick is the retry). A failure — timeout, RPC error — never lowers the
published balance: ``state.wallet_lamports``/``wallet_read_at`` are left
exactly as they were, so the heartbeat's ``wallet_balance_stale_s``
(``heartbeat.py``, computed from ``wallet_read_at``) is how the desk sees the
number aging, never a balance dropping to zero it never held.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["wallet_refresh_once"]

logger = get_logger(__name__)


async def wallet_refresh_once(ctx: ExecutorContext) -> None:
    """Read the wallet's lamports now; keep the last known reading on any failure.

    A signer-less process (paper / inert, no key) has nothing to read — the
    fields stay ``None``, exactly as they were before this module existed.
    """
    if ctx.signer is None:
        return
    pubkey = ctx.signer.pubkey
    try:
        reading = await asyncio.wait_for(
            asyncio.to_thread(ctx.chain.wallet, pubkey),
            timeout=ctx.config.wallet_read_timeout_s,
        )
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning("meme_executor_wallet_refresh_failed", error_type=type(exc).__name__)
        return
    ctx.state.wallet_lamports, ctx.state.wallet_read_at = (
        reading.lamports,
        reading.observed_at,
    )
