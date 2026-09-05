"""Single ingest writer and optional incremental subscription changes."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_market_worker.hot_state import TradeMemory
from hunter_market_worker.ingest import CHANNELS, AcceptedEvents, TickCoalescer, handle_event
from hunter_market_worker.supervision import IngestionHealth, Watchdog

logger = get_logger(__name__)

_HOUSEKEEPING_INTERVAL_S = 0.1


async def consume_once(
    adapter: Any,
    symbols: list[str],
    redis: Any,
    producer: str,
    queues: Any,
    coalescer: TickCoalescer,
    funding_memory: AcceptedEvents,
    trade_memory: TradeMemory,
    universe: Any,
    heartbeat_state: Any,
    health: IngestionHealth | None = None,
    watchdog: Watchdog | None = None,
) -> None:
    """Drain ``adapter.stream(...)`` with a plain ``async for`` (B1 —
    t16b-profile.md ACHADO-2: the old loop created one ``Task`` and one timer
    entry per event just to poll universe/watchdog every 100ms, which at
    ~30k events/s starved the consumer of the loop). Universe-diff/watchdog/
    health housekeeping now runs on its own 100ms loop, so the consumer
    never has to be interrupted just to check them.
    """
    stream = adapter.stream(list(symbols), CHANNELS)
    symbols = list(symbols)

    async def housekeeping() -> None:
        while True:
            await asyncio.sleep(_HOUSEKEEPING_INTERVAL_S)
            if health is not None:
                health.observe_adapter(adapter, active=bool(symbols))
            if watchdog is not None and watchdog.restart_stream:
                watchdog.restart_stream = False
                return
            if universe.changed.is_set():
                added = set(universe.symbols) - set(symbols)
                removed = set(symbols) - set(universe.symbols)
                universe.changed.clear()
                if added or removed:
                    update = getattr(adapter, "update_subscriptions", None)
                    if update is None:
                        raise RuntimeError(
                            "adapter lacks update_subscriptions; cannot apply universe diffs"
                        )
                    await update(sorted(added), sorted(removed), CHANNELS)
                    for symbol in removed:
                        trade_memory.forget(adapter.code, symbol)
                    symbols[:] = list(universe.symbols)

    async def consume() -> None:
        async for event in stream:
            if event.symbol not in symbols:
                continue
            accepted = await handle_event(
                event, redis, producer, queues, coalescer, funding_memory, trade_memory
            )
            if accepted:
                if health is not None:
                    health.data_event()
                if watchdog is not None:
                    watchdog.last_event = time.monotonic()
            source_ts = getattr(event, "ts", None)
            if accepted and source_ts is not None:
                previous = heartbeat_state.last_event_at
                heartbeat_state.last_event_at = max(previous, source_ts) if previous else source_ts
        # ``async for`` swallows StopAsyncIteration as normal loop exit — the
        # old code caught it explicitly from a manual __anext__() and turned
        # it into a fatal RuntimeError; a plain exhaustion here means the
        # same thing (the adapter's generator ended on its own).
        raise RuntimeError("task stream exited unexpectedly")

    housekeeping_task = asyncio.ensure_future(housekeeping())
    consume_task = asyncio.ensure_future(consume())
    try:
        done, _pending = await asyncio.wait(
            {housekeeping_task, consume_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if consume_task in done:
            exc = consume_task.exception()
            if exc is not None:
                raise exc
        if housekeeping_task in done:
            exc = housekeeping_task.exception()
            if exc is not None:
                raise exc
        # Otherwise housekeeping ended on its own (watchdog.restart_stream) —
        # same contract as before: consume_once simply returns.
    finally:
        for task in (consume_task, housekeeping_task):
            task.cancel()
        for task in (consume_task, housekeeping_task):
            with contextlib.suppress(asyncio.CancelledError):
                await task
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
    trade_memory = TradeMemory()
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
                trade_memory,
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
