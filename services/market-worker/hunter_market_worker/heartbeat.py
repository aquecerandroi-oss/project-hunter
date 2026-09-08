"""Per-exchange heartbeat: ``hb:market:{exchange}`` hash, ``rt:system``
pub/sub, and ``system_events`` on reconnect/adapter errors.

docs/plans/M1.md T1.3 item 5. In addition to the generic
``hb:{role}:{instance}`` the runtime already writes, this is the
exchange-scoped heartbeat the API's ``/system/market-status`` and the
frontend's live-status widget read.

**T2.5g — one heartbeat per shard.** With ``MARKET_SHARD=i/N`` and ``N > 1``
this process writes ``hb:market:{exchange}:{i}of{N}`` and nothing else: N
shards sharing one hash is what kept the 200 already-proven markets from
being delivered in M1 (``.claude/state/milestone.json`` ``m1_result``) —
whoever wrote last won, and a dead shard stayed invisible. The API unions the
shard keys (``hunter_api.services.market_shards``) and says how many of the
declared ``shard_total`` are actually reporting. ``N == 1`` is unchanged, key
and payload alike.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.domain.enums import MarketType, RiskEventSeverity
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.observability import (
    market_dropped_events_total,
    market_spot_dropped_events_total,
)
from hunter_core.redis import keys
from hunter_exchanges.rate_limit import REST_GATE_OK
from hunter_market_worker.heartbeat_events import (
    COMPONENT as COMPONENT,
)
from hunter_market_worker.heartbeat_events import (
    record_system_event as record_system_event,
)
from hunter_market_worker.heartbeat_events import (
    safe_record_system_event as safe_record_system_event,
)
from hunter_market_worker.heartbeat_events import (
    transition_event,
)
from hunter_market_worker.supervision import connection_field, counter_delta, rest_gate_status

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_exchanges.base import ExchangeAdapter
    from hunter_market_worker.universe import MonitoredUniverse

logger = get_logger(__name__)

HEARTBEAT_INTERVAL_S = 5
HB_TTL_S = 30


@dataclasses.dataclass
class HeartbeatState:
    """Shared mutable state: ``ingest.py`` and ``recovery.py`` update it,
    ``run_heartbeat`` reports it."""

    last_event_at: datetime | None = None
    reconnects: int = 0
    open_gaps: int = 0
    unrecoverable_gaps: int = 0
    """T3.7d: terminal gaps (before listing, or reopen-exhausted) — apart from
    :attr:`open_gaps` so a stuck backlog and a closed door never look equal."""
    last_error: str | None = None
    dropped_events: int = 0
    """Cumulative events discarded by the adapter's bounded queue (HIGH-1b),
    mirrors :attr:`reconnects`: a running total surfaced in the heartbeat
    hash, while :data:`hunter_core.observability.market_dropped_events_total`
    only ever receives the per-tick delta."""


def hb_key(
    exchange: str,
    shard_index: int = 0,
    shard_total: int = 1,
    market_type: MarketType = MarketType.PERPETUAL,
) -> str:
    """``hb:market:{exchange}`` solo, ``hb:market:{exchange}:{i}of{N}`` sharded
    — the same builder the API reads with (:meth:`keys.market_heartbeat`).

    T3.0c: spot is ``hb:market:spot:{exchange}``. The type goes **before** the
    exchange deliberately (T3.0b §1): Redis glob matches ``:``, so
    ``hb:market:{ex}:spot:...`` would be swept up by the perpetual shard scan.
    """
    return keys.market_heartbeat(exchange, shard_index, shard_total, market_type=market_type)


async def _write_hash(
    redis: redis_asyncio.Redis,
    exchange: str,
    universe: MonitoredUniverse,
    state: HeartbeatState,
    ws_state: str,
    now: datetime,
    subscriptions: int | None = None,
    rest_gate: str = REST_GATE_OK,
    shard_index: int = 0,
    shard_total: int = 1,
    market_type: MarketType = MarketType.PERPETUAL,
) -> None:
    key = hb_key(exchange, shard_index, shard_total, market_type)
    mapping = {
        "last_event_at": state.last_event_at.isoformat() if state.last_event_at else "",
        "ws_state": ws_state,
        "subscriptions": str(len(universe.symbols) if subscriptions is None else subscriptions),
        "reconnects": str(state.reconnects),
        "markets_monitored": str(len(universe.symbols)),
        "open_gaps": str(state.open_gaps),
        "unrecoverable_gaps": str(state.unrecoverable_gaps),
        "dropped_events": str(state.dropped_events),
        # T2.9: "suspended" while the shared rate-limit coordination is
        # unreachable and this process therefore admits no REST call. A
        # degradation reported next to a healthy ``ws_state`` — never a
        # readiness failure, since ingestion continues over the WebSocket.
        "rest_gate": rest_gate,
        # T2.5g: the topology, self-declared, so the API can tell "3 of 4
        # shards reporting" from "3 shards is all there is" without knowing
        # this process's MARKET_SHARD.
        "shard_index": str(shard_index),
        "shard_total": str(shard_total),
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
    rest_gate: str = REST_GATE_OK,
) -> None:
    payload = {
        "type": "market_status",
        "exchange": exchange,
        "ws_state": ws_state,
        "last_event_at": state.last_event_at.isoformat() if state.last_event_at else None,
        "markets_monitored": len(universe.symbols),
        "open_gaps": state.open_gaps,
        "rest_gate": rest_gate,
        "ts": now.isoformat(),
    }
    await cast(Any, redis).publish("rt:system", orjson.dumps(payload))


def connection_summary(
    adapter: Any,
    previous_reconnects: dict[str, int],
    previous_dropped: dict[str, int],
) -> tuple[int | None, int, int]:
    """Subscriptions (a snapshot count) plus reconnects and dropped events
    (per-tick deltas of each connection's monotonic counter) since the last
    call -- HIGH-1b: ``ConnectionState.dropped_events`` is otherwise
    incremented by the adapter and never read by anything."""
    method = getattr(adapter, "connection_states", None)
    if method is None:
        return None, 0, 0
    subscriptions = reconnects = dropped = 0
    for name, connection in method().items():
        active = connection_field(connection, "subscriptions") or ()
        subscriptions += active if isinstance(active, int) else len(active)
        count = int(connection_field(connection, "reconnects") or 0)
        reconnects += counter_delta(previous_reconnects.get(name, 0), count)
        previous_reconnects[name] = count
        dropped_count = int(connection_field(connection, "dropped_events") or 0)
        dropped += counter_delta(previous_dropped.get(name, 0), dropped_count)
        previous_dropped[name] = dropped_count
    return subscriptions, reconnects, dropped


async def _safe_publish(
    redis: redis_asyncio.Redis,
    exchange: str,
    universe: MonitoredUniverse,
    state: HeartbeatState,
    ws_state: str,
    now: datetime,
    subscriptions: int | None,
    rest_gate: str,
    shard_index: int = 0,
    shard_total: int = 1,
    market_type: MarketType = MarketType.PERPETUAL,
) -> bool:
    """Publish the heartbeat, degrading instead of raising. True if it landed.

    T2.9/Astra: ``run_heartbeat`` is a ``forever()`` task in the market
    ``TaskGroup``, so an exception out of these two writes cancels every
    sibling — including the WebSocket ingestion that suspending REST
    admissions exists to keep alive. A Redis outage must degrade this loop to
    "no heartbeat published" (the hash then expires on its own TTL, so the API
    correctly shows the worker as stale) exactly like a Postgres outage
    already degrades it to "no system_events written" via
    :func:`safe_record_system_event`. The next tick republishes the *current*
    state, so the snapshot converges within ``HEARTBEAT_INTERVAL_S`` of the
    outage ending. What a skipped tick does lose is a transition that both
    happened and reverted during the outage: ``rt:system`` is a live feed with
    no replay. The durable record of a connection transition is the
    ``system_events`` row, which is written on the Postgres path and does not
    depend on this succeeding.
    """
    try:
        await _write_hash(
            redis,
            exchange,
            universe,
            state,
            ws_state,
            now,
            subscriptions,
            rest_gate,
            shard_index,
            shard_total,
            market_type,
        )
        if shard_total <= 1 and market_type is MarketType.PERPETUAL:
            # T2.5g: ``rt:system`` patches the *whole* exchange row on the
            # System page (``apps/web/components/system/live-status.tsx``
            # ``mergeExchangeUpdate``), so a shard publishing here would
            # replace 200 markets with its own 50 and a dead sibling would
            # keep reading "connected". In sharded mode the aggregate on
            # ``/system/market-status`` is the only truth and the widget is
            # refreshed by polling — declared in docs/PIPELINE.md §1.
            # T3.0c: and never from the spot collector either, for the same
            # reason — that row is the perpetual exchange row, and a spot
            # ws_state written into it would describe the wrong connection.
            await _publish_status(redis, exchange, universe, state, ws_state, now, rest_gate)
    except Exception:
        logger.warning("market_heartbeat_publish_failed", exchange=exchange, exc_info=True)
        return False
    return True


async def run_heartbeat(
    runtime: WorkerRuntime,
    adapter: ExchangeAdapter,
    universe: MonitoredUniverse,
    state: HeartbeatState,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    market_type: MarketType = MarketType.PERPETUAL,
    shard: tuple[int, int] | None = None,
) -> None:
    """Write the hash, publish ``rt:system``, and log state transitions —
    every :data:`HEARTBEAT_INTERVAL_S` seconds.

    HIGH-2: the Redis writes (:func:`_write_hash`, :func:`_publish_status`)
    are the liveness signal this loop exists to produce, and they must
    complete every tick even when Postgres is down. So they run *before* any
    ``system_events`` recording is even attempted, and every such recording
    goes through :func:`safe_record_system_event`, which never raises. A
    database outage must degrade this loop to "no system_events written",
    never to "the whole TaskGroup dies".
    """
    # T3.0c: ``shard`` overrides MARKET_SHARD. The spot collector is a single
    # process owning the whole spot universe, so it reports as solo — claiming
    # "0 of 4" would make the API wait for three spot shards that never exist.
    settings = runtime.settings
    shard_index, shard_total = shard or (settings.shard_index, settings.shard_total)
    previous_ws_state: str | None = None
    previous_rest_gate: str | None = None
    last_sent = float("-inf")
    previous_reconnects: dict[str, int] = {}
    previous_dropped: dict[str, int] = {}
    while True:
        subscriptions, reconnects, dropped = connection_summary(
            adapter, previous_reconnects, previous_dropped
        )
        if reconnects:
            state.reconnects += reconnects
            runtime.mark_error()
        if dropped:
            state.dropped_events += dropped
            # T3.0e: separate series per venue -- both adapters answer
            # ``adapter.code == "binance"`` by design (one row in
            # ``exchanges``), so a shared counter cannot tell "spot is
            # reconnecting, routine" from "the perpetual, which the whole
            # Radar depends on, is losing tape" (review-T3.0c-T3.0d.md).
            metric = (
                market_spot_dropped_events_total
                if market_type is MarketType.SPOT
                else market_dropped_events_total
            )
            metric.labels(exchange=adapter.code).inc(dropped)
        ws_state = (
            "idle" if universe.initialized and not universe.symbols else adapter.connection_state()
        )
        rest_gate = rest_gate_status(adapter)
        if (
            ws_state == previous_ws_state
            and rest_gate == previous_rest_gate
            and not reconnects
            and not dropped
            and state.last_error is None
            and time.monotonic() - last_sent < HEARTBEAT_INTERVAL_S
        ):
            await asyncio.sleep(min(0.1, HEARTBEAT_INTERVAL_S))
            continue
        now = utcnow()
        published = await _safe_publish(
            runtime.redis,
            adapter.code,
            universe,
            state,
            ws_state,
            now,
            subscriptions,
            rest_gate,
            shard_index,
            shard_total,
            market_type,
        )
        if reconnects:
            await safe_record_system_event(
                session_factory,
                "adapter_reconnect",
                f"{adapter.code}: {reconnects} connection retries",
                RiskEventSeverity.WARNING,
            )
        if previous_ws_state is not None and ws_state != previous_ws_state:
            event, severity = transition_event(ws_state)
            await safe_record_system_event(
                session_factory, event, f"{previous_ws_state} -> {ws_state}", severity
            )
        if state.last_error is not None:
            await safe_record_system_event(
                session_factory, "adapter_error", state.last_error, RiskEventSeverity.WARNING
            )
            state.last_error = None
        previous_ws_state = ws_state
        previous_rest_gate = rest_gate
        last_sent = time.monotonic()
        if published:
            runtime.mark_success()
        await asyncio.sleep(min(0.1, HEARTBEAT_INTERVAL_S))
