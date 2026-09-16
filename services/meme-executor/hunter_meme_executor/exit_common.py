"""Shared between ``exits.py`` (bonding curve) and ``pumpswap_exit.py``
(T4.29a) — kept in its own module so neither imports the other."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, set_exit_intent

__all__ = ["BACKOFF_S", "mark_blocked"]

logger = get_logger(__name__)
BACKOFF_S = (2, 4, 8, 16, 32, 60)


async def mark_blocked(
    ctx: ExecutorContext, position: OpenPosition, reason: str, block: str, now: datetime
) -> None:
    """Record a named, non-silent exit refusal — never a quiet skip."""
    intent: dict[str, Any] = {"reason": reason, "decided_at": now.isoformat(), "blocked": block}
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await set_exit_intent(session, position.id, intent, now=now)
    ctx.state.blocked_exits[position.id] = block
    ctx.state.exits_blocked += 1
    logger.warning(
        "meme_live_exit_blocked",
        position_id=position.id,
        mint=position.mint,
        reason=reason,
        blocked=block,
    )
