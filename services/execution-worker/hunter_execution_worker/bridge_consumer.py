"""``shadow.signals.emitted`` → the bridge, behind ``ENABLE_PAPER_AUTONOMY``.

The flag is a **wiring** decision, not a branch inside the loop: with it false
:func:`bridge_tasks` returns nothing, so no task is created, ``XGROUP CREATE`` is
never issued and the consumer group ``execution-worker.bridge`` does not exist on
the stream. That is stronger than a guard inside the handler — a group that
exists accumulates pending entries and looks, to anyone reading ``XINFO``, like
an autonomy that is running.

``/ready`` says which of the two it is (``autonomy: off`` / ``on``), because "the
wallet is not entering anything" has two completely different causes and an
operator must not have to guess which one they are looking at.

The loop itself is the ordinary one: own group, ``event_id`` guard from
``hunter_core.events.consume``, and the ACK **after** the transaction that made
the effect durable committed. A crash in between redelivers the message, and the
redelivery is a no-op twice over: the guard skips it, and even without the guard
the proposal's ``client_key`` is ``shadow:{signal_id}``, so admission answers
with the decision it already took instead of taking a second FIFO place.

**Two drivers, one queue, and why that is safe.** This consumer runs a cycle
when a signal arrives (latency: the entry window is 120 s), and
``Cycles.bridge`` runs one on the admission cadence (liveness: a candidate that
lost a slot is retried without waiting for another event). They share no memory
— the queue is a query — so the worst they can do is run the same cycle twice.
Each cycle still submits **one** proposal, and what stops the second cycle from
committing capital the first one already committed is not this module: it is
``admit`` taking the wallet lock, re-reading the state inside it and seeing the
first reservation (M3 joint decision, item 4).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.types import utcnow
from hunter_core.events.consume import ack, consume
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_execution_worker.bridge import run_bridge_cycle
from hunter_execution_worker.config import WORKER_ROLE, ExecutionConfig
from hunter_execution_worker.wallet import principal_wallets

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_execution_worker.market_data import SpotMarketData
    from hunter_execution_worker.state import CycleHealth

__all__ = [
    "CONSUMER_GROUP",
    "autonomy_status",
    "bridge_tasks",
    "handle_signal_event",
    "run_bridge_consumer",
]

logger = get_logger(__name__)

CONSUMER_GROUP = "execution-worker.bridge"
"""This bridge's own group. Never shared with the strategy-worker's: two
consumers of one group split the stream, and half the signals would silently
never be screened."""


def autonomy_status(config: ExecutionConfig) -> str:
    """What ``/ready`` publishes under ``autonomy``."""
    return "on" if config.enable_paper_autonomy else "off"


async def handle_signal_event(
    factory: async_sessionmaker[AsyncSession],
    *,
    data: SpotMarketData,
    config: ExecutionConfig,
    health: CycleHealth,
    now: datetime,
    payload: dict[str, Any] | None = None,
) -> int:
    """Run one bridge cycle per managed wallet. Returns how many were submitted.

    The event is a **wake-up**, not the candidate: what may be admitted is read
    from Postgres inside the transaction that acts on it, so a message that
    arrives twice, out of order, or after a restart cannot decide anything the
    durable state does not already say (T3.5 item 7).
    """
    if payload is not None:
        logger.debug("bridge_event_received", signal_id=str(payload.get("signal_id", "")))
    async with role_session(factory, db_role=WORKER_ROLE) as session:
        wallets = await principal_wallets(session)
    submitted = 0
    for wallet in wallets:
        async with tenant_session(factory, wallet.organization_id, db_role=WORKER_ROLE) as session:
            outcome = await run_bridge_cycle(
                session,
                wallet=wallet,
                data=data,
                now=now,
                exit_cost_rate=config.exit_cost_rate,
            )
        health.bridge_candidates = outcome.candidates
        if outcome.submitted is not None:
            submitted += 1
    health.bridge_at = now
    health.bridge_events += 1
    return submitted


async def run_bridge_consumer(
    redis: redis_asyncio.Redis,
    factory: async_sessionmaker[AsyncSession],
    *,
    data: SpotMarketData,
    config: ExecutionConfig,
    health: CycleHealth,
    consumer: str,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Consume the stream for ever. Only ever started behind the flag."""
    logger.info("bridge_consumer_starting", group=CONSUMER_GROUP, consumer=consumer)
    async for message_id, envelope in consume(
        redis, Streams.SHADOW_SIGNALS_EMITTED, CONSUMER_GROUP, consumer
    ):
        try:
            await handle_signal_event(
                factory,
                data=data,
                config=config,
                health=health,
                now=clock(),
                payload=envelope.payload,
            )
        except Exception:
            # The message stays pending: another pass (or another instance, via
            # XAUTOCLAIM) will try it again. Acking a failed effect is the one
            # thing that loses a signal for good.
            health.errors += 1
            logger.exception("bridge_event_failed", event_id=str(envelope.event_id))
            continue
        await ack(redis, Streams.SHADOW_SIGNALS_EMITTED, CONSUMER_GROUP, message_id, envelope)


def bridge_tasks(
    config: ExecutionConfig,
    *,
    redis: redis_asyncio.Redis,
    factory: async_sessionmaker[AsyncSession],
    data: SpotMarketData,
    health: CycleHealth,
    consumer: str,
) -> list[tuple[str, Coroutine[Any, Any, None]]]:
    """The long-lived tasks autonomy adds — **empty** when the flag is off.

    Returning coroutines rather than starting them keeps the decision in one
    place and makes it assertable: a test can prove that a disabled worker
    creates no task, and therefore never touches the stream.
    """
    if not config.enable_paper_autonomy:
        logger.info(
            "paper_autonomy_off",
            reason="ENABLE_PAPER_AUTONOMY is false; the shadow bridge does not consume",
        )
        return []
    logger.warning(
        "paper_autonomy_on",
        group=CONSUMER_GROUP,
        note=(
            "the bridge will submit shadow signals to admission; M3 forbids this in production "
            "before the nine verifications of T3.9 are accepted"
        ),
    )
    return [
        (
            "bridge_consumer",
            run_bridge_consumer(
                redis,
                factory,
                data=data,
                config=config,
                health=health,
                consumer=consumer,
            ),
        )
    ]
