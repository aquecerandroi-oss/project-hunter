"""The two cycle meters, the durable history and their wiring, built once per boot.

Split from ``main.py`` (350-line budget). Everything is created and announced at
the **top** of ``run_meme``, before the ``MEME_ENABLED`` branch: a loop that is
switched off (or a radar that is off entirely) still publishes an empty
generation with ``<loop>_cycle_enabled=false``, so the previous process's numbers
in the shared ``hb:meme:radar`` hash never look current.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.cycle_history import (
    FLUSH_EVERY_S,
    CycleHistory,
    drain,
    flush_once,
    publish_counters,
)
from hunter_meme_worker.cycle_metrics import (
    CHAIN_WINDOW,
    LAB_WINDOW,
    PUBLISH_BUDGET_S,
    CycleMeter,
    CyclePublisher,
    announce_all,
    timed_step,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.config import MemeConfig

__all__ = ["CLOSE_FLUSH_BUDGET_S", "CycleInstruments", "build_cycle_instruments"]

logger = get_logger(__name__)

CLOSE_FLUSH_BUDGET_S = 3.0


@dataclass
class CycleInstruments:
    chain: CycleMeter
    lab: CycleMeter
    session_factory: async_sessionmaker[AsyncSession]
    write: CyclePublisher
    history: CycleHistory = field(default_factory=CycleHistory)
    crashed: bool = False
    """Set the moment something other than a cancel takes the run down - before any cleanup,
    because a SIGTERM during the cleanup replaces the exception in flight."""

    async def announce(self) -> None:
        """Both meters, enabled or not, replace the previous process's fields, leave a
        birth certificate in the durable history, and zero the history counters."""
        await announce_all([self.chain, self.lab], self.write)
        self.history.mark_start(self.chain)
        self.history.mark_start(self.lab)
        await publish_counters(self.history, self.write, PUBLISH_BUDGET_S, force=True)

    def chain_step[ContextT, ResultT](
        self, step: Callable[[ContextT], Awaitable[ResultT]]
    ) -> Callable[[ContextT], Coroutine[Any, Any, ResultT]]:
        return timed_step(self.chain, step, self.write, on_cycle=self.history.offer)

    def lab_step[ContextT, ResultT](
        self, step: Callable[[ContextT], Awaitable[ResultT]]
    ) -> Callable[[ContextT], Coroutine[Any, Any, ResultT]]:
        return timed_step(self.lab, step, self.write, on_cycle=self.history.offer)

    def note_crash(self) -> None:
        self.crashed = True

    async def flush(self, _ctx: object = None) -> None:
        """One flush; ``flush_once`` never raises except on cancel."""
        await flush_once(self.history, self.session_factory, self.write)

    async def _writer(self) -> None:
        """Flush, *then* sleep, until cancelled. Unlike ``collect.forever`` it never ends on an
        unexpected exception (nobody supervises it: ending would leave a worker that runs on
        with a queue that only drops) - it logs and tries again next time."""
        while True:
            try:
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("meme_cycle_history_writer_failed")
            await asyncio.sleep(FLUSH_EVERY_S)

    async def close(self, *, clean: bool) -> None:
        """The final totals of both generations and how they ended (``clean`` is false
        when a loop crashed), then drain the queue within ``CLOSE_FLUSH_BUDGET_S`` — a hard
        bound (the write is abandoned at the budget). A generation without a
        ``generation_end`` has an unproven ending, not necessarily a crash."""
        now = utcnow()
        self.history.mark_end(self.chain, now, clean=clean)
        self.history.mark_end(self.lab, now, clean=clean)
        await drain(self.history, self.session_factory, self.write, budget_s=CLOSE_FLUSH_BUDGET_S)

    @asynccontextmanager
    async def supervised(self) -> AsyncGenerator[None]:
        """Around the whole run, **enabled or not**: the writer runs for its duration (a
        radar switched off still persists the generations it announced) and the exit closes
        the generations - ``clean`` only when the body ended by a cancel (SIGTERM) or
        normally and nothing called :meth:`note_crash`: a loop's crash (an ``ExceptionGroup``)
        or any other exception is not clean, and neither is a crash a later cancel covered."""
        flusher = asyncio.create_task(self._writer(), name="meme-cycle-history")
        try:
            yield
        except asyncio.CancelledError:
            raise
        except BaseException:
            self.crashed = True
            raise
        finally:
            flusher.cancel()
            await asyncio.wait({flusher}, timeout=CLOSE_FLUSH_BUDGET_S)
            await self.close(clean=not self.crashed)


def build_cycle_instruments(
    config: MemeConfig, session_factory: async_sessionmaker[AsyncSession], write: CyclePublisher
) -> CycleInstruments:
    return CycleInstruments(
        chain=CycleMeter(
            "chain",
            nominal_s=config.chain_cycle_s,
            window=CHAIN_WINDOW,
            enabled=config.enabled and config.chain_curves_enabled,
        ),
        lab=CycleMeter(
            "lab",
            nominal_s=config.lab_cycle_s,
            window=LAB_WINDOW,
            enabled=config.enabled and config.lab_enabled,
        ),
        session_factory=session_factory,
        write=write,
    )
