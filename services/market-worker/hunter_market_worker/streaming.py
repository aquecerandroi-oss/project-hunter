"""Single ingest writer and optional incremental subscription changes."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_market_worker.ingest import CHANNELS, AcceptedEvents, TickCoalescer, handle_event
from hunter_market_worker.supervision import IngestionHealth, Watchdog

logger = get_logger(__name__)


async def consume_once(
    adapter: Any,
    symbols: list[str],
    redis: Any,
    producer: str,
    queues: Any,
    coalescer: TickCoalescer,
    funding_memory: AcceptedEvents,
    universe: Any,
    heartbeat_state: Any,
    health: IngestionHealth | None = None,
    watchdog: Watchdog | None = None,
) -> None:
    stream = adapter.stream(symbols, CHANNELS)
    next_event = None
    try:
        while True:
            if next_event is None:
                next_event = asyncio.ensure_future(stream.__anext__())
            done, _ = await asyncio.wait({next_event}, timeout=0.1)
            if health is not None:
                health.observe_adapter(adapter, active=bool(symbols))
            if watchdog is not None and watchdog.restart_stream:
                watchdog.restart_stream = False
                return
            if universe.changed.is_set():
                added, removed = (
                    set(universe.symbols) - set(symbols),
                    set(symbols) - set(universe.symbols),
                )
                universe.changed.clear()
                if added or removed:
                    update = getattr(adapter, "update_subscriptions", None)
                    if update is None:
                        raise RuntimeError(
                            "adapter lacks update_subscriptions; cannot apply universe diffs"
                        )
                    await update(sorted(added), sorted(removed), CHANNELS)
                    symbols = list(universe.symbols)
            if not done:
                continue
            try:
                event = next_event.result()
            except StopAsyncIteration as exc:
                raise RuntimeError("task stream exited unexpectedly") from exc
            next_event = None
            if event.symbol not in symbols:
                continue
            accepted = await handle_event(event, redis, producer, queues, coalescer, funding_memory)
            if accepted:
                if health is not None:
                    health.data_event()
                if watchdog is not None:
                    watchdog.last_event = time.monotonic()
            source_ts = getattr(event, "ts", None)
            if accepted and source_ts is not None:
                previous = heartbeat_state.last_event_at
                heartbeat_state.last_event_at = max(previous, source_ts) if previous else source_ts
    finally:
        if next_event is not None:
            next_event.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await next_event
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()


async def run_ingest(
    adapter: Any,
    redis: Any,
    settings: Any,
    universe: Any,
    queues: Any,
    heartbeat_state: Any,
    runtime: Any,
    coalescer: TickCoalescer,
    health: IngestionHealth,
    watchdog: Watchdog,
) -> None:
    producer = f"market-worker@{runtime.instance}"
    memory = AcceptedEvents()
    while True:
        if not universe.symbols:
            if universe.initialized:
                health.update("idle", active=False)
            try:
                await asyncio.wait_for(universe.changed.wait(), 0.1)
            except TimeoutError:
                continue
            universe.changed.clear()
            continue
        universe.changed.clear()
        health.update("connecting", active=True)
        try:
            await consume_once(
                adapter,
                list(universe.symbols),
                redis,
                producer,
                queues,
                coalescer,
                memory,
                universe,
                heartbeat_state,
                health,
                watchdog,
            )
        except ExchangeError as exc:
            heartbeat_state.last_error = str(exc)
            runtime.mark_error()
            health.update("reconnecting", active=True)
            logger.warning("market_stream_error", error=str(exc))
            await asyncio.sleep(1)
        heartbeat_state.reconnects += 1


async def run_watchdog(watchdog: Watchdog, universe: Any) -> None:
    while True:
        await watchdog.check(active=bool(universe.symbols))
        await asyncio.sleep(1)
