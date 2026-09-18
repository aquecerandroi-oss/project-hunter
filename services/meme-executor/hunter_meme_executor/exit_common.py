"""Shared between ``exits.py`` (bonding curve) and ``pumpswap_exit.py``
(T4.29a) — kept in its own module so neither imports the other."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from hunter_core.db.session import role_session
from hunter_core.execution.meme.gates import parse_flag
from hunter_core.logging import get_logger
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, set_exit_intent

__all__ = ["BACKOFF_S", "ENV_CLOSE_ATA_ON_FULL_SELL", "close_ata_on_full_sell", "mark_blocked"]

logger = get_logger(__name__)
BACKOFF_S = (2, 4, 8, 16, 32, 60)
ENV_CLOSE_ATA_ON_FULL_SELL = "MEME_CLOSE_ATA_ON_FULL_SELL"


def close_ata_on_full_sell(env: Mapping[str, str]) -> bool:
    """T4.46 — OFF by default: a full sell closes the mint's ATA (rent back,
    R43) only when Everton sets ``MEME_CLOSE_ATA_ON_FULL_SELL=1`` in the VPS
    ``.env``. Review of 5bbae3ab: safe, but a systematic close error would park
    every position at simulation, and the first mainnet close is the only
    real test — a change to the real sell transaction is his flag."""
    return parse_flag(env.get(ENV_CLOSE_ATA_ON_FULL_SELL), default=False)


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
