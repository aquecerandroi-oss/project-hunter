"""KB-0172 — the second look before a ``spot/1`` stop or target is sold (Open
Bugs "decide stop/alvo numa cotação só", 01/10/2026). The mark is one Jupiter
quote of the lot; twice in ten trades it was a phantom (UNI 29/09: −13,6 %
while Binance said +0,39 %, sold as a "stop" 2 h 29 min early; NEAR 26/09:
+3,6 %, the "target" sell died in simulation).

``plan_exit`` runs inside ``spot_exits._sell`` **before** any row is written:
for ``stop``/``target`` it asks Jupiter once more for the whole lot at the
leg's own tolerance, re-runs the pure rule on that quote
(``spot_exit_rules.confirm_trigger``) and hands the **same** quote to the leg
when it confirms — the executed quote is the one that confirmed the trigger.
Not confirmed: no order, no attempt, no backoff; the row's mark becomes the
confirming quote with ``mark_reason = trigger_unconfirmed:<reason>:<outcome>``;
a stop episode's start is kept on the row (``exit_intent.stop_unconfirmed_since``)
so the bounded wait survives a restart. ``emergency``/``sell_requested``/``time``
pass straight through. The Binance reference is **not** a gate here (Astra: it
would hold an exit through a real Solana-side de-peg) — that is a hypothesis.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_exit_repo import STOP_EPISODE_KEY, set_stop_episode
from hunter_meme_executor.spot_exit_rules import (
    TRIGGER_REASONS,
    confirm_trigger,
    overdue_stop,
    r_now,
    slippage_for,
)
from hunter_meme_executor.spot_repo import set_mark
from hunter_meme_executor.spot_send_rules import quote_mismatch

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.spot_config import SpotConfig
    from hunter_meme_executor.spot_repo import SpotPosition

__all__ = ["ExitPlan", "plan_exit", "settle_stop_episode", "stop_since"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)


@dataclass(frozen=True, slots=True)
class ExitPlan:
    """``reason`` ``None`` = sell nothing this tick; ``quote`` = the confirming
    quote the leg must execute (``None`` = the leg quotes for itself);
    ``record`` = ``intent.trigger_confirmation`` (``None`` when not required)."""

    reason: str | None
    slippage_bps: int
    quote: JupiterQuote | None
    record: dict[str, Any] | None


def stop_since(position: SpotPosition) -> datetime | None:
    raw = (position.exit_intent or {}).get(STOP_EPISODE_KEY)
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


async def _confirming_quote(
    ctx: ExecutorContext, position: SpotPosition, slippage_bps: int
) -> tuple[JupiterQuote | None, Decimal | None, str | None]:
    """``(quote, mark, error)`` — a quote that fails or is not for this lot is
    *unavailable*, never a number."""
    try:
        quote = await asyncio.to_thread(
            ctx.treasury_client.quote,
            input_mint=position.mint,
            output_mint=WRAPPED_SOL_MINT,
            amount=position.tokens,
            slippage_bps=slippage_bps,
        )
    except ExchangeError as exc:  # the leg's own split: a 4xx is a refusal, not an outage
        prefix = "quote_failed" if exc.retryable else "quote_refused"
        return None, None, f"{prefix}:{type(exc).__name__}"
    except Exception as exc:
        return None, None, f"quote_failed:{type(exc).__name__}"
    mismatch = quote_mismatch(quote, position.mint, WRAPPED_SOL_MINT, position.tokens)
    if mismatch is not None:
        return None, None, mismatch
    return quote, Decimal(int(quote.out_amount)) / LAMPORTS, None


async def plan_exit(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    position: SpotPosition,
    reason: str,
    *,
    attempt: int,
    now: datetime,
    decided_mark: Decimal | None,
) -> ExitPlan:
    """The reason, tolerance and quote the sell goes with — or ``reason=None``."""

    def tolerance(why: str) -> int:
        normal, panic = cfg.exit_slippage_bps, cfg.panic_slippage_bps
        return slippage_for(attempt, why, normal_bps=normal, panic_bps=panic)

    slippage = tolerance(reason)
    if reason not in TRIGGER_REASONS:
        return ExitPlan(reason, slippage, None, None)
    quote, mark, error = await _confirming_quote(ctx, position, slippage)
    checked_at = utcnow()  # after the await: the deadline reads the real clock
    since = stop_since(position)
    verdict = confirm_trigger(
        position,
        reason,
        mark,
        checked_at,
        ctx.kill.effective,
        auto_close_on_emergency=ctx.config.auto_close_on_emergency,
        stop_since=since,
        decided_on_mark=decided_mark is not None,
    )
    r = r_now(position, mark)
    record: dict[str, Any] = {
        "decided_reason": reason,
        "outcome": verdict.outcome,
        "confirm_mark_sol": None if mark is None else str(mark),
        "confirm_r_now": None if r is None else str(r),
        "confirm_error": error,
        "stop_since": None if since is None else since.isoformat(),
        "checked_at": checked_at.isoformat(),
    }
    if verdict.reason is not None:
        final = slippage if verdict.reason == reason else tolerance(verdict.reason)
        return ExitPlan(verdict.reason, final, quote if verdict.use_quote else None, record)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await set_mark(
            session,
            position.id,
            mark_sol=mark,
            reason=f"trigger_unconfirmed:{reason}:{verdict.outcome}",
            now=now,
        )
        if verdict.stop_since != since:
            await set_stop_episode(session, position.id, since=verdict.stop_since, now=now)
    logger.warning("meme_spot_exit_trigger_unconfirmed", position_id=position.id, **record)
    return ExitPlan(None, slippage, None, record)


async def settle_stop_episode(
    ctx: ExecutorContext,
    position: SpotPosition,
    mark: Decimal | None,
    reason: str | None,
    *,
    now: datetime,
) -> str | None:
    """The reason the loop goes on with. A **readable** mark that triggers
    nothing ends a stop episode; a failed mark is absence of data, never a
    recovery (Astra, design review) — and once the episode is past its deadline
    a failed mark still yields ``stop`` (Astra, diff review), which
    ``plan_exit`` then confirms or forces."""
    since = stop_since(position)
    if reason is not None or since is None:
        return reason
    if overdue_stop(since, mark, now):
        return "stop"
    if mark is not None:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await set_stop_episode(session, position.id, since=None, now=utcnow())
    return None
