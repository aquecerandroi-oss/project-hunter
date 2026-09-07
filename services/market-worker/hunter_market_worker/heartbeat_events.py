"""Writing ``system_events`` from the collector, and the one rule about them.

Extracted from :mod:`hunter_market_worker.heartbeat` (T3.0c) for the 350-line
budget, along the seam the two halves already had: the heartbeat is a *live*
signal in Redis, this is the *durable* record in Postgres, and the whole point
of :func:`safe_record_system_event` is that the second failing must never take
the first down. ``heartbeat.py`` re-exports both functions, so no importer
changes.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.logging import get_logger
from hunter_core.observability import market_system_event_record_failures_total

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

COMPONENT = "market-worker"

__all__ = [
    "COMPONENT",
    "record_system_event",
    "safe_record_system_event",
    "transition_event",
]


async def record_system_event(
    session_factory: async_sessionmaker[AsyncSession],
    event: str,
    message: str,
    severity: RiskEventSeverity,
) -> None:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        session.add(SystemEvent(level=severity, component=COMPONENT, event=event, message=message))


async def safe_record_system_event(
    session_factory: async_sessionmaker[AsyncSession],
    event: str,
    message: str,
    severity: RiskEventSeverity,
) -> None:
    """``record_system_event``, but a persistence failure is an observability
    loss, never a reason to stop ingesting (HIGH-2): a real Postgres outage
    must not take the caller's permanent loop down with it. Logs a warning,
    increments :data:`market_system_event_record_failures_total`, and
    returns. ``asyncio.CancelledError`` is never swallowed -- coordinated
    shutdown must still cancel."""
    try:
        await record_system_event(session_factory, event, message, severity)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("market_system_event_record_failed", system_event=event, exc_info=True)
        market_system_event_record_failures_total.labels(event=event).inc()


def transition_event(ws_state: str) -> tuple[str, RiskEventSeverity]:
    if ws_state == "connected":
        return "ws_reconnected", RiskEventSeverity.WARNING
    if ws_state == "disconnected":
        return "ws_disconnected", RiskEventSeverity.CRITICAL
    return "ws_state_changed", RiskEventSeverity.WARNING
