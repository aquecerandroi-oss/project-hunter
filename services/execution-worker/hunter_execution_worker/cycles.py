"""The five loops, each one transaction per pass, each one wallet at a time.

Nothing here holds state between passes: every loop opens a tenant transaction
as the engine, re-reads what it needs from Postgres, acts, and commits. That is
what makes a restart a no-op — the worker after a crash is the worker before it,
because there was never anything in memory to lose (T3.5 item 7).

The clock is **injected**. Every cycle takes ``now`` from a callable, so a test
drives a whole day through them without one real ``sleep`` (spec §12, traps 1
and 2), and production passes the wall clock once, at the top.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.execution.tape import usable_trade
from hunter_core.logging import get_logger
from hunter_execution_worker import metrics
from hunter_execution_worker.admission_cycle import pending_requests, report_unreadable
from hunter_execution_worker.config import WORKER_ROLE, ExecutionConfig
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.guard import (
    cancel_pending_entries,
    expire_stale_reservations,
    read_effective_state,
)
from hunter_execution_worker.mtm import run_mtm_cycle
from hunter_execution_worker.positions import load_open_positions
from hunter_execution_worker.protection import TriggerWatermarks, run_protection_cycle
from hunter_execution_worker.reference import load_markets
from hunter_execution_worker.wallet import WalletRef, principal_wallets

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_execution_worker.market_data import SpotMarketData
    from hunter_execution_worker.state import CycleHealth

__all__ = ["Clock", "Cycles", "every"]

logger = get_logger(__name__)

Clock = Callable[[], datetime]


async def every(
    seconds: float, run: Callable[[], Awaitable[None]], *, name: str, health: CycleHealth
) -> None:
    """Run ``run`` for ever, on a fixed cadence. A failure is logged, never fatal.

    A cycle that raises must not take the process down: the protection loop has
    to keep running while the admission loop cannot reach a market, and vice
    versa. What *is* fatal is a loop **returning** — that is
    :func:`hunter_execution_worker.main.forever`'s job.
    """
    while True:
        try:
            await run()
        except Exception:
            health.errors += 1
            logger.exception("execution_cycle_failed", cycle=name)
        await asyncio.sleep(seconds)


class Cycles:
    """One object per process, holding only what a cycle may legitimately reuse."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        data: SpotMarketData,
        config: ExecutionConfig,
        health: CycleHealth,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self.factory = factory
        self.data = data
        self.config = config
        self.health = health
        self.clock = clock
        self.adapter = PaperExecutionAdapter()
        self.watermarks = TriggerWatermarks()

    async def wallets(self) -> tuple[WalletRef, ...]:
        """Every managed wallet, re-read each pass (one opened later is picked up)."""
        async with role_session(self.factory, db_role=WORKER_ROLE) as session:
            return await principal_wallets(session)

    async def _for_each(self, run: Callable[[AsyncSession, WalletRef], Awaitable[None]]) -> None:
        for wallet in await self.wallets():
            async with tenant_session(
                self.factory, wallet.organization_id, db_role=WORKER_ROLE
            ) as session:
                await run(session, wallet)

    # ------------------------------------------------------------- the loops

    async def admission(self) -> None:
        """Look at what the API filed. Decide what can be decided; say what cannot."""

        async def run(session: AsyncSession, wallet: WalletRef) -> None:
            filed = await pending_requests(session, wallet=wallet)
            unreadable = report_unreadable(wallet, filed)
            self.health.pending_requests = len(filed)
            self.health.unreadable_requests = unreadable
            metrics.execution_pending_requests.labels(readable="false").set(unreadable)
            metrics.execution_pending_requests.labels(readable="true").set(len(filed) - unreadable)
            self.health.admission_at = self.clock()

        await self._for_each(run)

    async def entries(self) -> None:
        """Turn approved, reserved proposals into at most one attempt each."""

        async def run(session: AsyncSession, wallet: WalletRef) -> None:
            now = self.clock()
            outcomes = await execute_approved_entries(
                session, wallet=wallet, data=self.data, now=now, adapter=self.adapter
            )
            for outcome in outcomes:
                metrics.execution_orders_total.labels(kind="entry", outcome=outcome.status).inc()
            self.health.entries_at = now

        await self._for_each(run)

    async def protection(self) -> None:
        """Evaluate every protection against the tape, and attempt what fired."""

        async def run(session: AsyncSession, wallet: WalletRef) -> None:
            now = self.clock()
            outcomes = await run_protection_cycle(
                session,
                wallet=wallet,
                data=self.data,
                now=now,
                watermarks=self.watermarks,
                adapter=self.adapter,
                clock=self.clock,
            )
            for outcome in outcomes:
                metrics.execution_orders_total.labels(kind="exit", outcome=outcome.status).inc()
                if outcome.status == "pending_degraded":
                    metrics.execution_pending_degraded_total.labels(
                        reason=outcome.reason or "unknown"
                    ).inc()
                    self.health.mark_degraded(outcome.intent_id, now)
                elif outcome.application is not None and outcome.application.filled_qty > 0:
                    self.health.clear_degraded(outcome.intent_id)
            metrics.execution_protection_delay_seconds.set(self.health.protection_delay_s())
            self.health.protection_at = now

        await self._for_each(run)

    async def expiry(self) -> None:
        """The 30 s reservation tenure, swept under the wallet's lock."""

        async def run(session: AsyncSession, wallet: WalletRef) -> None:
            expired = await expire_stale_reservations(session, wallet=wallet, now=self.clock())
            for _ in expired:
                metrics.execution_reservations_total.labels(state="expired").inc()

        await self._for_each(run)

    async def kill_switch(self) -> None:
        """Re-read the latch, and cancel pendings while it blocks entries."""

        async def run(session: AsyncSession, wallet: WalletRef) -> None:
            now = self.clock()
            scopes = await read_effective_state(session, wallet=wallet)
            self.health.kill_switch = scopes.effective.value
            self.health.kill_switch_read_at = now
            cancelled = await cancel_pending_entries(session, wallet=wallet, now=now, scopes=scopes)
            for _ in cancelled:
                metrics.execution_reservations_total.labels(state="released").inc()

        await self._for_each(run)

    async def mark_to_market(self) -> None:
        """One point of the 1m curve, then the kill switch that reads it."""

        async def run(session: AsyncSession, wallet: WalletRef) -> None:
            now = self.clock()
            marks = await self._marks(session, wallet=wallet, now=now)
            result = await run_mtm_cycle(
                session,
                wallet=wallet,
                marks=marks,
                betas=None,
                exit_cost_rate=self.config.exit_cost_rate,
                now=now,
            )
            self.health.mtm_written_at = now
            self.health.equity = str(result.equity)
            self.health.kill_switch = result.evaluation.effective.value
            self.health.kill_switch_read_at = now
            metrics.execution_mtm_age_seconds.set(0.0)

        await self._for_each(run)

    async def _marks(
        self, session: AsyncSession, *, wallet: WalletRef, now: datetime
    ) -> dict[uuid.UUID, Decimal]:
        """A price per open market, from the **last valid SPOT trade** and nothing else.

        A market whose tape has nothing usable is simply absent from the map, and
        the ledger then falls back to the last durable mark and flags the state
        incomplete. Marking at a price we could not validate would be the
        invented number the directive forbids.
        """
        positions = await load_open_positions(session, wallet=wallet)
        markets = await load_markets(session, {position.market_id for position in positions})
        marks: dict[uuid.UUID, Decimal] = {}
        for market_id, market in markets.items():
            snapshot = await self.data.snapshot(market.identity)
            trade, _ = usable_trade(
                snapshot.last_trade, now=now, policy=self.adapter.policy.marking_policy
            )
            if trade is not None:
                marks[market_id] = trade.price
        self.health.open_positions = len(positions)
        return marks
