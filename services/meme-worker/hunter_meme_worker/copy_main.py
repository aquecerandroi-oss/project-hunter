"""``main.py``'s glue for the paper copy lane (H-037, task F): the ``MEME_COPY_LANE`` flag, the leader
source and a supervisor that keeps a crash of the lane inside the lane.

``MEME_COPY_LANE`` is ``off`` (the default, also when unset) or ``paper``. There is no ``on`` and no
``live``: any other value logs a warning and reads as ``off`` (fail closed), exactly like
``MEME_LAUNCH_LANE`` and ``MEME_EVENT_GATE``. With ``off`` nothing here runs: no RPC client, no WS
feed, no source, no task -- ``build_copy_lane`` returns ``None`` before touching the context. The lane
itself stays inert until an audited ``copy_v0`` rule set is active (``copy_wiring.py``), so ``paper``
without the seed opens no NATS or WS connection either (the source is opened by ``stream()``).

Two things the lane's own module does not give ``main.py`` for free:

* **A source per stream.** ``ChainLeaderSource.stream`` closes its feed when the stream ends and
  ``SolanaWsClient.aclose`` is final, so one source reused after a source failure or a rule-set change
  would keep the NATS side and lose the on-chain confirmation silently. :class:`_RenewedLeaderSource`
  builds a new source and a new feed for every ``stream()`` and closes the feed when it ends.
* **A dedicated RPC client** for the confirmations. ``RadarContext.chain`` is typed ``ChainSource``,
  which has no ``call``; and the radar's chain budget is the scarcest of the three, so the lane's
  ``getTransaction`` bursts get their own buckets. The lane still *prices* from ``ctx.chain``.

An operational exception in the lane (``Exception``: a Redis or database error, a bug) does not reach
the worker's ``TaskGroup``: :meth:`CopyLaneRuntime.run` logs it and starts the lane again after
:data:`RESTART_S`. A cancellation (shutdown) passes through, and so would ``SystemExit`` or
``KeyboardInterrupt`` -- those are not swallowed on purpose.

The dedicated RPC client has its own buckets, like the wallets watcher's: it does not share the
endpoint's quota with the radar or with ``MEME_WATCH_WALLETS``. On the public endpoint that is a real
risk of 429s for the confirmations, so ``paper`` belongs on a paid ``SOLANA_RPC_URL``.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats
from hunter_exchanges.pumpfun.leader_source_wiring import build_leader_source
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_meme_worker.copy_wiring import start_copy_lane
from hunter_meme_worker.event_gate_config import solana_rpc_ws_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Collection

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.leader_events import LeaderItem, LeaderSource
    from hunter_meme_worker.context import ChainSource, RadarContext

__all__ = [
    "COPY_LANE_OFF",
    "COPY_LANE_PAPER",
    "RESTART_S",
    "CopyLaneRuntime",
    "build_copy_lane",
    "copy_lane_mode",
]

logger = get_logger(__name__)

COPY_LANE_OFF = "off"
COPY_LANE_PAPER = "paper"
RESTART_S = 5.0
"""Pause before the lane is started again after a crash (the fleet's own source restart is also 5 s)."""


def copy_lane_mode() -> str:
    raw = os.environ.get("MEME_COPY_LANE", "").strip().lower()
    if not raw or raw == COPY_LANE_OFF:
        return COPY_LANE_OFF
    if raw == COPY_LANE_PAPER:
        return COPY_LANE_PAPER
    logger.warning("meme_copy_lane_config_invalid", variable="MEME_COPY_LANE", value=raw[:32])
    return COPY_LANE_OFF


class _RenewedLeaderSource:
    """A :class:`LeaderSource` whose every ``stream()`` is a brand-new NATS + chain source."""

    def __init__(self, rpc: SolanaRpcClient, ws_url: str) -> None:
        self._rpc = rpc
        self._ws_url = ws_url
        # one object across restarts, so the latency series belongs to the lane, not to a stream
        self._stats = LeaderSourceStats()

    async def stream(self, wallets: Collection[str]) -> AsyncIterator[LeaderItem]:
        feed = SolanaWsClient(url=self._ws_url)
        try:
            items = build_leader_source(self._rpc, feed, stats=self._stats).stream(wallets)
            try:
                async for item in items:
                    yield item
            finally:
                close = getattr(items, "aclose", None)
                if close is not None:
                    await close()
        finally:
            await feed.aclose()


class CopyLaneRuntime:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        chain: ChainSource,
        rpc: SolanaRpcClient,
        source: LeaderSource,
        heartbeat: Callable[[dict[str, str]], Awaitable[None]],
    ) -> None:
        self._session_factory = session_factory
        self._chain = chain
        self._rpc = rpc
        self.source = source
        self._heartbeat = heartbeat

    async def run(self) -> None:
        """Run the lane for the life of the worker; a crash is logged and the lane restarts."""
        while True:
            try:
                await start_copy_lane(
                    session_factory=self._session_factory,
                    chain=self._chain,
                    source=self.source,
                    heartbeat=self._heartbeat,
                )
                logger.warning("meme_copy_lane_returned_restarting")
            except Exception as exc:  # CancelledError is not an Exception: shutdown passes through
                logger.error(
                    "meme_copy_lane_crashed_restarting",
                    error=f"{type(exc).__name__}: {exc}"[:200],
                    exc_info=True,
                )
            await asyncio.sleep(RESTART_S)

    async def aclose(self) -> None:
        """Called from ``main.py``'s ``finally``; the feed of a live stream is closed by the stream."""
        await self._rpc.aclose()


def build_copy_lane(
    ctx: RadarContext, heartbeat: Callable[[dict[str, str]], Awaitable[None]]
) -> CopyLaneRuntime | None:
    """``None`` unless ``MEME_COPY_LANE=paper``; with ``None`` nothing was built or opened."""
    if copy_lane_mode() != COPY_LANE_PAPER:
        return None
    rpc = SolanaRpcClient()
    logger.info("meme_copy_lane_enabled", mode=COPY_LANE_PAPER)
    return CopyLaneRuntime(
        session_factory=ctx.session_factory,
        chain=ctx.chain,
        rpc=rpc,
        source=_RenewedLeaderSource(rpc, solana_rpc_ws_url()),
        heartbeat=heartbeat,
    )
