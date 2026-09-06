"""The five stream consumers. They mark work; they never do it.

Each stream gets its own consumer group (``scanner-worker.<stream>``) so a slow
one cannot hold back another's pending list, and each message is filtered by
``event_id`` before the caller sees it (``hunter_core.events.consume``).

**What a consumer does with a message is mark the market dirty.** The evidence
the scanner reasons about is the hot state, not the message payload: a tick says
"this market moved", and the vector is then computed from the four Redis keys at
a cut the collector proved. That is what makes coalescence sound -- twenty ticks
in a second are one evaluation, and dropping nineteen of them costs nothing
because none of them *was* the evidence.

**The ACK still waits for the effect.** A closed candle announces a minute the
scanner has to snapshot, so its message is held (:class:`PendingAck`) and acked
by the persist cycle after the transaction that wrote the snapshot commits.
Ticks, derivatives and liquidations are pure notifications with no durable
effect of their own and are acked as they are handled; that difference is
stated per stream below rather than left to be inferred.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_core.domain.market import NormalizedCandle, from_wire
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.events.consume import ack, ack_many, consume, consume_batches
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_scanner_worker.config import group_for
from hunter_scanner_worker.metrics import (
    scanner_consumer_events_total,
    scanner_stream_delay_seconds,
)
from hunter_scanner_worker.state import PendingAck

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    import redis.asyncio as redis_asyncio

    from hunter_core.events.envelope import EventEnvelope
    from hunter_core.runtime import WorkerRuntime

logger = get_logger(__name__)

RESTART_BACKOFF_S = 1.0
RESTART_BACKOFF_MAX_S = 30.0

TICK_STREAMS = (
    Streams.MARKET_TICKS,
    Streams.MARKET_DERIVATIVES,
    Streams.MARKET_LIQUIDATIONS,
)

__all__ = [
    "Coalesced",
    "ConsumerHealth",
    "coalesce",
    "run_batch_consumer",
    "run_stream_consumer",
    "symbol_of",
    "ts_of",
]


@dataclass
class ConsumerHealth:
    """Liveness of the consumers, read by ``/ready``."""

    started_at: datetime | None = None
    last_message_at: dict[str, datetime] = field(default_factory=dict[str, datetime])
    last_iteration_at: dict[str, datetime] = field(default_factory=dict[str, datetime])
    errors: int = 0

    def touch(self, stream: str, *, message: bool = False) -> None:
        now = utcnow()
        self.last_iteration_at[stream] = now
        if message:
            self.last_message_at[stream] = now

    def alive(self, stream: str, *, max_idle_s: float, now: datetime | None = None) -> bool:
        """A quiet stream is not a stuck consumer -- only a stalled *loop* is."""
        moment = now or utcnow()
        seen = self.last_iteration_at.get(stream) or self.started_at
        if seen is None:
            return False
        return (moment - seen).total_seconds() <= max_idle_s


def symbol_of(envelope: EventEnvelope) -> str | None:
    """The market a message is about, from the payload or the routing key."""
    payload: dict[str, Any] = envelope.payload
    symbol = payload.get("symbol")
    if isinstance(symbol, str) and symbol:
        return symbol
    key = envelope.key or ""
    if ":" in key:
        return key.split(":", 1)[1]
    return None


def ts_of(envelope: EventEnvelope) -> datetime:
    """The instant the *market* produced this, not the instant we read it.

    The tick->opportunity budget is measured from here, so a queue the scanner
    is behind on has to show up in the number rather than be reset by it.
    """
    raw = envelope.payload.get("ts")
    if isinstance(raw, str):
        try:
            return ensure_utc(datetime.fromisoformat(raw))
        except ValueError:
            pass
    return ensure_utc(envelope.ts)


def candle_of(envelope: EventEnvelope) -> NormalizedCandle | None:
    data = dict(envelope.payload)
    data.pop("ts", None)
    try:
        return from_wire(NormalizedCandle, data)
    except Exception:
        logger.warning("scanner_candle_payload_unreadable", event_id=str(envelope.event_id))
        return None


async def run_stream_consumer(
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    stream: str,
    health: ConsumerHealth,
    handle: Callable[[str, EventEnvelope], Awaitable[PendingAck | None]],
    *,
    block_ms: int,
) -> None:
    """Consume ``stream`` forever, handing each message to ``handle``.

    ``handle`` returns a :class:`PendingAck` when the effect is not durable yet
    (the persist cycle will ack it) or ``None`` when the message is finished
    with. Two independent failure budgets, as in the strategy-worker: one
    unreadable message is skipped, while an error from the iteration itself --
    Redis restarting, a dropped connection, the idle read deadline -- backs off
    and re-enters ``consume()``. Returning is fatal (``forever``).
    """
    group = group_for(stream)
    consumer = f"scanner-worker@{runtime.instance}"
    backoff = RESTART_BACKOFF_S
    health.started_at = health.started_at or utcnow()
    while True:
        try:
            async for message_id, envelope in consume(
                redis, stream, group, consumer, block_ms=block_ms
            ):
                health.touch(stream, message=True)
                scanner_consumer_events_total.labels(stream=stream).inc()
                backoff = RESTART_BACKOFF_S
                try:
                    pending = await handle(message_id, envelope)
                except Exception:
                    health.errors += 1
                    runtime.mark_error()
                    logger.exception(
                        "scanner_message_failed", stream=stream, event_id=str(envelope.event_id)
                    )
                    continue
                if pending is None:
                    await ack(redis, stream, group, message_id, envelope)
                runtime.mark_success()
            logger.warning("scanner_consumer_stream_ended", stream=stream, backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            logger.exception("scanner_consumer_restarting", stream=stream, backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)


@dataclass(frozen=True, slots=True)
class Coalesced:
    """What one read batch of notifications amounts to, per market."""

    newest: dict[str, datetime]
    """The stamp each market's evaluation should carry: the most recent one.

    The vector is computed from the hot state at the current cut, so the newest
    notification is the one that describes the evidence the scanner will read.
    It is also what :meth:`MarketState.touch` already does between calls, so the
    batch cannot mean something different from the stream it replaces."""

    absorbed: int
    """Notifications another one of the same market already covers. Valid ones
    only -- a message with no market covers nothing."""

    oldest: datetime | None
    """The oldest stamp in the batch, kept **because** ``newest`` hides it.

    A batch that spans ten minutes of backlog and one fresh tick looks fresh
    from ``newest`` alone; this is what the queue actually costs, sampled before
    the coalescence (Astra, T2.5d design review, must-fix 4)."""


def coalesce(deliveries: Sequence[tuple[str, EventEnvelope]]) -> Coalesced:
    """One touch per market for a whole batch, instead of one per message.

    Sound only for notifications: a tick says "this market moved", and the
    evidence is the hot state, not the payload. Twenty ticks of one market in
    one batch are therefore one evaluation, and the nineteen absorbed ones cost
    nothing -- none of them *was* the evidence (see this module's header).
    """
    newest: dict[str, datetime] = {}
    absorbed = 0
    oldest: datetime | None = None
    for _message_id, envelope in deliveries:
        symbol = symbol_of(envelope)
        if symbol is None:
            continue
        stamp = ts_of(envelope)
        if oldest is None or stamp < oldest:
            oldest = stamp
        current = newest.get(symbol)
        if current is None:
            newest[symbol] = stamp
            continue
        absorbed += 1
        if stamp > current:
            newest[symbol] = stamp
    return Coalesced(newest=newest, absorbed=absorbed, oldest=oldest)


async def run_batch_consumer(
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    stream: str,
    health: ConsumerHealth,
    handle: Callable[[list[tuple[str, EventEnvelope]]], Awaitable[None]],
    *,
    block_ms: int,
    batch: int,
) -> None:
    """Consume ``stream`` in batches, handing each whole batch to ``handle``.

    For the **notification** streams only (ticks, derivatives, liquidations):
    they have no durable effect of their own, so the whole batch is acked as
    soon as the handler returns, in one round trip. ``market.candles.closed``
    stays on :func:`run_stream_consumer`, whose ACK the persist cycle owns.

    The failure budgets are the ones above, with the batch as the unit: a
    handler that raises leaves the **whole** batch pending and the next
    ``XAUTOCLAIM`` brings it back; an error from the iteration itself backs off
    and re-enters.

    The honest contract of that redelivery is "not everything completed", not
    "nothing was applied" (Astra, T2.5d diff review): a handler that fails on the
    twentieth market has already touched nineteen. Redoing them is free and
    exact — a touch is a set of reasons and a maximum timestamp — which is why
    the whole batch may be replayed rather than picked apart.
    """
    group = group_for(stream)
    consumer = f"scanner-worker@{runtime.instance}"
    backoff = RESTART_BACKOFF_S
    health.started_at = health.started_at or utcnow()
    while True:
        try:
            async for deliveries in consume_batches(
                redis, stream, group, consumer, block_ms=block_ms, batch=batch
            ):
                health.touch(stream, message=bool(deliveries))
                if not deliveries:
                    continue
                scanner_consumer_events_total.labels(stream=stream).inc(len(deliveries))
                backoff = RESTART_BACKOFF_S
                try:
                    await handle(deliveries)
                except Exception:
                    health.errors += 1
                    runtime.mark_error()
                    logger.exception(
                        "scanner_batch_failed", stream=stream, messages=len(deliveries)
                    )
                    continue
                await ack_many(redis, stream, group, deliveries)
                runtime.mark_success()
            logger.warning("scanner_consumer_stream_ended", stream=stream, backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            logger.exception("scanner_consumer_restarting", stream=stream, backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)


def observe_delay(stream: str, oldest: datetime | None, *, now: datetime | None = None) -> None:
    """Sample how far behind the batch was, from the market's own stamp."""
    if oldest is None:
        return
    scanner_stream_delay_seconds.labels(stream=stream).observe(
        max(0.0, ((now or utcnow()) - oldest).total_seconds())
    )


def pending_ack(stream: str, message_id: str, envelope: EventEnvelope) -> PendingAck:
    return PendingAck(
        stream=stream,
        group=group_for(stream),
        message_id=message_id,
        event_id=str(envelope.event_id),
    )


async def heartbeat_touch(health: ConsumerHealth, stream: str) -> None:
    health.touch(stream)
