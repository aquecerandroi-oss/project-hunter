"""One durable row per tick — ``meme_lab_ticks`` (``0031``, T4.15).

The heartbeat's ``lab_gate_refusals`` is overwritten every minute; the daily
close (``infra/scripts/meme_close_day.py``) needs the whole day. So the loop
appends, at the end of every pass, the counters ``TickReport`` carries and the
same refusal dictionary the heartbeat publishes — as ``hunter_worker``, in a
session of its own, ``ON CONFLICT DO NOTHING`` on the tick's instant.

A row that cannot be written is a warning, never a stopped Lab: the close
reports "sem ticks gravados" for the minutes that are missing, which is the
visible failure the contract wants, not a silent one.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.lab import LabState, TickReport

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"

_INSERT_TICK = text(
    "INSERT INTO meme_lab_ticks (ticked_at, tick_minute, minutes_evaluated, rows_evaluated, "
    "  rule_sets_active, proposals, expired, cancelled, fills, unfilled, closes, bets_open, "
    "  refusals) "
    "VALUES (:ticked_at, :tick_minute, :minutes_evaluated, :rows_evaluated, :rule_sets_active, "
    "  :proposals, :expired, :cancelled, :fills, :unfilled, :closes, :bets_open, "
    "  CAST(:refusals AS jsonb)) "
    "ON CONFLICT (ticked_at) DO NOTHING"
)


def tick_row(state: LabState, report: TickReport, *, now: datetime) -> dict[str, Any]:
    """The row exactly as the heartbeat would describe this tick."""
    return {
        "ticked_at": now,
        "tick_minute": report.minute,
        "minutes_evaluated": report.minutes_evaluated,
        "rows_evaluated": report.rows_evaluated,
        "rule_sets_active": state.rule_sets_active,
        "proposals": report.proposals,
        "expired": report.expired,
        "cancelled": report.cancelled,
        "fills": report.fills.filled,
        "unfilled": report.fills.unfilled,
        "closes": report.bets.closed,
        "bets_open": report.bets.open,
        "refusals": json.dumps(state.refusals, sort_keys=True),
    }


async def record_tick(
    session_factory: async_sessionmaker[AsyncSession],
    state: LabState,
    report: TickReport,
    *,
    now: datetime,
) -> bool:
    """Append the tick; ``False`` (and a warning) when the row could not be written."""
    try:
        async with role_session(session_factory, db_role=WORKER_ROLE) as session:
            await session.execute(_INSERT_TICK, tick_row(state, report, now=now))
    except Exception as exc:  # the record is not the tick
        logger.warning("meme_lab_tick_row_not_written", error=str(exc))
        return False
    return True
