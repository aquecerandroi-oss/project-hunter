"""Per-exchange heartbeat: ``hb:market:{exchange}`` hash, ``rt:system``
pub/sub, and ``system_events`` on reconnect/adapter errors.

docs/plans/M1.md T1.3 item 5. In addition to the generic
``hb:{role}:{instance}`` the runtime already writes, this is the
exchange-scoped heartbeat the API's ``/system/market-status`` and the
frontend's live-status widget read.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_market_worker.supervision import connection_field

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_exchanges.base import ExchangeAdapter
    from hunter_market_worker.universe import MonitoredUniverse

logger = get_logger(__name__)

HEARTBEAT_INTERVAL_S = 5
HB_TTL_S = 30
COMPONENT = "market-worker"


@dataclasses.dataclass
class HeartbeatState:
    """Shared mutable state: ``ingest.py`` and ``recovery.py`` update it,
    ``run_heartbeat`` reports it."""

    last_event_at: datetime | None = None
    reconnects: int = 0
    open_gaps: int = 0
    last_error: str | None = None


def hb_key(exchange: str) -> str:
    return f"hb:market:{exchange}"


async def _write_hash(
    redis: redis_asyncio.Redis,
    exchange: str,
    universe: MonitoredUniverse,
    state: HeartbeatState,
    ws_state: str,
    now: datetime,
    subscriptions: int | None = None,
) -> None:
    key = hb_key(exchange)
    mapping = {
        "last_event_at": state.last_event_at.isoformat() if state.last_event_at else "",
        "ws_state": ws_state,
        "subscriptions": str(len(universe.symbols) if subscriptions is None else subscriptions),
        "reconnects": str(state.reconnects),
        "markets_monitored": str(len(universe.symbols)),
        "open_gaps": str(state.open_gaps),
        "ts": now.isoformat(),
    }
    await cast(Any, redis).hset(key, mapping=mapping)
    await redis.expire(key, HB_TTL_S)


async def _publish_status(
    redis: redis_asyncio.Redis,
    exchange: str,
    universe: MonitoredUniverse,
    state: HeartbeatState,
    ws_state: str,
    now: datetime,
) -> None:
    payload = {
        "type": "market_status",
        "exchange": exchange,
        "ws_state": ws_state,
        "last_event_at": state.last_event_at.isoformat() if state.last_event_at else None,
        "markets_monitored": len(universe.symbols),
        "open_gaps": state.open_gaps,
        "ts": now.isoformat(),
    }
    await cast(Any, redis).publish("rt:system", orjson.dumps(payload))


async def record_system_event(
    session_factory: async_sessionmaker[AsyncSession],
    event: str,
    message: str,
    severity: RiskEventSeverity,
) -> None:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        session.add(SystemEvent(level=severity, component=COMPONENT, event=event, message=message))


def _transition_event(ws_state: str) -> tuple[str, RiskEventSeverity]:
    if ws_state == "connected":
        return "ws_reconnected", RiskEventSeverity.WARNING
    if ws_state == "disconnected":
        return "ws_disconnected", RiskEventSeverity.CRITICAL
    return "ws_state_changed", RiskEventSeverity.WARNING


def connection_summary(adapter: Any, previous: dict[str, int]) -> tuple[int | None, int]:
    method = getattr(adapter, "connection_states", None)
    if method is None:
        return None, 0
    subscriptions = reconnects = 0
    for name, connection in method().items():
        active = connection_field(connection, "subscriptions") or ()
        subscriptions += active if isinstance(active, int) else len(active)
        count = int(connection_field(connection, "reconnects") or 0)
        reconnects += max(0, count - previous.get(name, 0))
        previous[name] = count
    return subscriptions, reconnects


async def run_heartbeat(
    runtime: WorkerRuntime,
    adapter: ExchangeAdapter,
    universe: MonitoredUniverse,
    state: HeartbeatState,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Write the hash, publish ``rt:system``, and log state transitions —
    every :data:`HEARTBEAT_INTERVAL_S` seconds."""
    previous_ws_state: str | None = None
    last_sent = float("-inf")
    previous_counts: dict[str, int] = {}
    while True:
        subscriptions, reconnects = connection_summary(adapter, previous_counts)
        if reconnects:
            state.reconnects += reconnects
            runtime.mark_error()
            await record_system_event(
                session_factory,
                "adapter_reconnect",
                f"{adapter.code}: {reconnects} connection retries",
                RiskEventSeverity.WARNING,
            )
        ws_state = (
            "idle" if universe.initialized and not universe.symbols else adapter.connection_state()
        )
        if (
            ws_state == previous_ws_state
            and not reconnects
            and state.last_error is None
            and time.monotonic() - last_sent < HEARTBEAT_INTERVAL_S
        ):
            await asyncio.sleep(min(0.1, HEARTBEAT_INTERVAL_S))
            continue
        now = utcnow()
        await _write_hash(
            runtime.redis, adapter.code, universe, state, ws_state, now, subscriptions
        )
        await _publish_status(runtime.redis, adapter.code, universe, state, ws_state, now)
        if previous_ws_state is not None and ws_state != previous_ws_state:
            event, severity = _transition_event(ws_state)
            await record_system_event(
                session_factory, event, f"{previous_ws_state} -> {ws_state}", severity
            )
        if state.last_error is not None:
            await record_system_event(
                session_factory, "adapter_error", state.last_error, RiskEventSeverity.WARNING
            )
            state.last_error = None
        previous_ws_state = ws_state
        last_sent = time.monotonic()
        runtime.mark_success()
        await asyncio.sleep(min(0.1, HEARTBEAT_INTERVAL_S))
