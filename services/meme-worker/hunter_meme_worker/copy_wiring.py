"""``main.py``'s one line for the copy lane (H-037): the same shape ``launch_lane_wiring.py`` and
``event_gate_wiring.py`` settled on, so the worker's ``main`` stays a list of lanes.

The lane is **inert** until an active ``copy_v0`` rule set exists (today none does): it reads the
rule set, writes ``copy_state = inert`` on the heartbeat, and re-checks every 30 s. It consumes a
``LeaderSource`` — the NATS per-wallet channel with its on-chain fallback — and never touches the
executor, a wallet or an order.

Wiring in ``main.py`` (inside the worker's ``TaskGroup``, next to the launch lane)::

    group.create_task(
        start_copy_lane(
            session_factory=session_factory,
            chain=chain,  # the same ChainSource the Lab already holds
            source=leader_source,  # a hunter_exchanges.pumpfun.leader_events.LeaderSource
            heartbeat=heartbeat,  # the writer of hb:meme:radar (fields already prefixed copy_)
        ),
        name="meme-copy-lane",
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.copy_forever import run_copy_lane_forever

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.leader_events import LeaderSource
    from hunter_meme_worker.context import ChainSource

__all__ = ["start_copy_lane"]

logger = get_logger(__name__)


async def start_copy_lane(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    chain: ChainSource,
    source: LeaderSource,
    heartbeat: Callable[[dict[str, str]], Awaitable[None]] | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Run the copy lane until cancelled. Never raises into the caller's ``TaskGroup``: a crash of
    the lane is logged and the lane restarts (``run_copy_lane_forever``)."""
    logger.info("meme_copy_lane_wired")
    await run_copy_lane_forever(
        session_factory=session_factory,
        chain=chain,
        source=source,
        heartbeat=heartbeat,
        clock=clock,
    )
