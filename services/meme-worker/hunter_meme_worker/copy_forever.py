"""Keeps the copy lanes running (H-037): one :class:`~hunter_meme_worker.copy_lane.CopyLane` **per
active ``clock = 'copy'`` rule set** — today ``copy_v0/1`` (stratum ``regra``, the pre-registered
population) and ``copy_everton_v0/1`` (``escolha_everton``, descriptive only) — all fed by **one** source
opened for the union of their wallets.

Each lane has its own book, queue, outbox, executor and counters, so capacity (100 open copies plus
pending fills, one attempt per (stratum, mint), 20 per leader per day) is per set by construction: an
``escolha_everton`` copy can never take a slot of ``regra``. The primary also keeps **protected
priority** on the shared resources: its executor has a larger in-flight cap and an overloaded
secondary refuses its own load (``sobrecarga``) without ever touching the primary's queue.

Inert until a copy set is active; restarts every lane when the active sets change (the leader list of
a set is frozen — a different set is a different cohort).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import LeaderGap
from hunter_meme_worker.copy_lane import CopyLane
from hunter_meme_worker.copy_spec import load_copy_specs

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.leader_events import LeaderItem, LeaderSource
    from hunter_meme_worker.context import ChainSource

__all__ = ["CopyFleet", "run_copy_lane_forever"]

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
SPEC_CHECK_S = 30.0
INERT_RECHECK_S = 30.0
SOURCE_RESTART_S = 5.0
SOURCE_LOST = "source_lost"


class CopyFleet:
    def __init__(
        self,
        lanes: list[CopyLane],
        source: LeaderSource,
        *,
        clock: Callable[[], datetime] = utcnow,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.lanes = lanes
        self._source = source
        self._clock = clock
        self._sleep = sleep
        self._route: dict[str, list[CopyLane]] = {}
        for lane in lanes:
            for wallet in lane.spec.wallets:
                self._route.setdefault(wallet, []).append(lane)

    @property
    def wallets(self) -> list[str]:
        return sorted(self._route)

    def dispatch(self, item: LeaderItem) -> None:
        """Hand one item to the lanes that follow it — synchronous, like each lane's ``on_item``."""
        if isinstance(item, LeaderGap):
            targets = self.lanes if item.wallet is None else self._route.get(item.wallet, [])
        else:
            targets = self._route.get(item.wallet, [])
        for lane in targets:
            try:
                lane.on_item(item)
            except (
                Exception
            ) as exc:  # one lane's bad item never starves the other; no logging here:
                lane.stats.bad_items += 1  # a blocked stderr must not hold the shared source
                lane.stats.last_error = f"{type(exc).__name__}: {exc}"[:200]

    async def read_source(self) -> None:
        """Feed the lanes from the source. A source that ends or fails is a **loss of coverage**: a
        global gap opens at once (entries become ``lacuna``, leader-driven exits are censored) and
        closes when the stream speaks again — never a lane that says ``running`` over silence."""
        lost_at: datetime | None = None
        if not self._route:  # every set is empty (escolha_everton may be): nothing to follow
            await asyncio.Event().wait()
        while True:
            try:
                async for item in self._source.stream(self.wallets):
                    if lost_at is not None:
                        self.dispatch(LeaderGap(None, lost_at, self._clock(), SOURCE_LOST))
                        lost_at = None
                    self.dispatch(item)
                logger.warning("meme_copy_source_ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("meme_copy_source_failed", error=str(exc)[:200], exc_info=True)
            if lost_at is None:
                lost_at = self._clock()
                self.dispatch(LeaderGap(None, lost_at, None, SOURCE_LOST))
            await self._sleep(SOURCE_RESTART_S)

    async def run(self) -> None:
        """Recover EVERY lane first (T0, the funnel, the open copies), then open the one source: the
        barrier that keeps an early event from meeting an empty memory."""
        await asyncio.gather(*(lane.start() for lane in self.lanes))
        async with asyncio.TaskGroup() as group:
            group.create_task(self.read_source(), name="meme-copy-source")
            for lane in self.lanes:
                group.create_task(lane.run(), name=f"meme-copy-{lane.spec.name}")


async def _inert(heartbeat: Callable[[dict[str, str]], Awaitable[None]] | None) -> None:
    if heartbeat is not None:
        await heartbeat({"copy_state": "inert", "copy_leaders": "0", "copy_open": "0"})


async def _active_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[str, str]] | None:
    try:
        async with role_session(session_factory, db_role=WORKER_ROLE) as session:
            return [(spec.id, spec.status) for spec in await load_copy_specs(session)]
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # keep running on the last known sets
        logger.warning("meme_copy_spec_load_failed", error=str(exc)[:200])
        return None


async def run_copy_lane_forever(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    chain: ChainSource,
    source: LeaderSource,
    heartbeat: Callable[[dict[str, str]], Awaitable[None]] | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Inert until an active copy rule set exists; then run them all; restart when the set changes."""
    while True:
        try:
            async with role_session(session_factory, db_role=WORKER_ROLE) as session:
                specs = await load_copy_specs(session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("meme_copy_spec_load_failed", error=str(exc)[:200])
            specs = []
        if not specs:
            await _inert(heartbeat)
            await asyncio.sleep(INERT_RECHECK_S)
            continue
        lanes = [
            CopyLane(
                spec=spec,
                session_factory=session_factory,
                chain=chain,
                heartbeat=heartbeat,
                clock=clock,
            )
            for spec in specs
        ]
        fleet = CopyFleet(lanes, source, clock=clock)
        logger.info(
            "meme_copy_lanes_starting",
            rule_sets=[s.label for s in specs],
            wallets=len(fleet.wallets),
        )
        runner = asyncio.create_task(fleet.run(), name="meme-copy-fleet")
        known = [(spec.id, spec.status) for spec in specs]
        try:
            while not runner.done():
                await asyncio.wait({runner}, timeout=SPEC_CHECK_S)
                if runner.done():
                    logger.warning(
                        "meme_copy_lanes_crashed_restarting",
                        error=str(runner.exception())[:200],
                        exc_info=runner.exception(),
                    )
                    await asyncio.sleep(SOURCE_RESTART_S)
                    break
                current = await _active_ids(session_factory)
                if current is not None and current != known:
                    logger.info("meme_copy_rule_sets_changed", old=known, new=current)
                    break
        finally:
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)
