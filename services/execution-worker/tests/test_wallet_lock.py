"""T3.5b item 2 — the protection cycle takes the wallet's lock, or the MTM lies.

The scenario the guardian reproduced in Postgres, driven here with two real
sessions on two real connections:

1. the protection sells 18,499 units at 95 and its transaction is **still open**;
2. the mark-to-market of the same wallet starts.

``build_portfolio_state`` reads the cash and the positions in two statements
under READ COMMITTED, so if the protection may commit *between* them the point
of the curve is built from the cash of before the sale and the position of after
it: 18.148,2458 where the wallet really holds 19.903,8934 — 8,78 % below the
truth, which latches BLOCKED on a wallet that is up on the day and only Everton
can unlatch.

The fix is not "read them together" (there is no such statement): it is that the
protection acquires ``portfolio_risk_state`` **first**, in the contract's order,
so the MTM either sees the whole sale or none of it. This test proves the MTM
never got as far as reading cash while the protection's transaction was open —
which is the only formulation that does not depend on how fast either side runs.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_core.db.repositories.ledger import LedgerRepository
from hunter_core.db.session import tenant_session
from hunter_execution_worker.mtm import run_mtm_cycle
from hunter_execution_worker.protection import run_protection_cycle
from hunter_execution_worker.wallet import WalletRef

from .builders import NO_EXIT_COST, NOW, create_tenant
from .scenarios import CYCLE_AT, GAP_PRICE, WORKER_ROLE, gap_snapshot, open_a_position, static

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MARK_AT = NOW + timedelta(seconds=60)
TRUE_EQUITY = Decimal("19903.893385")
"""Cash of 19.903,847595 after the sale plus the dust valued at the same mark."""

TORN_EQUITY = Decimal("18148.245790")
"""What the interleaved read produced: the cash of *before* the sale plus the
position of *after* it. Named so the failure is recognisable, never expected."""

HANDOVER_S = 1.5
"""How long the seller waits, with its transaction open, for the MTM to reach
its cash read. It is a *ceiling on the wrong behaviour*, not a race: without the
lock the MTM gets there in milliseconds, and with it the wait can only time out
because Postgres is holding the second session on the lock row."""


class TestTheProtectionCycleHoldsTheWalletLock:
    async def test_the_mark_to_market_waits_and_writes_the_equity_after_the_sale(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_a_position(db_session_factory, db_engine, tenant)
        reference = WalletRef(wallet.org_id, wallet.portfolio_id)

        sold = asyncio.Event()
        """The sale is written, and its transaction is still open."""
        read_cash = asyncio.Event()
        """The MTM has just read the wallet's cash."""
        committed = asyncio.Event()
        slipped_in: list[bool] = []

        original = LedgerRepository.reconcile_cash

        async def instrumented(
            self: LedgerRepository, portfolio_id: uuid.UUID, **kwargs: Any
        ) -> Any:
            # The real read happens first, then the seller is allowed to commit:
            # that is exactly the interleaving that tore the point in two.
            reconciliation = await original(self, portfolio_id, **kwargs)
            read_cash.set()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(committed.wait(), timeout=HANDOVER_S * 4)
            return reconciliation

        monkeypatch.setattr(LedgerRepository, "reconcile_cash", instrumented)

        async def sell() -> None:
            async with tenant_session(
                db_session_factory, wallet.org_id, db_role=WORKER_ROLE
            ) as session:
                outcomes = await run_protection_cycle(
                    session,
                    wallet=reference,
                    data=static(tenant, gap_snapshot(tenant)),
                    now=CYCLE_AT,
                )
                assert [outcome.status for outcome in outcomes] == ["filled"]
                sold.set()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(read_cash.wait(), timeout=HANDOVER_S)
                slipped_in.append(read_cash.is_set())
            committed.set()

        async def mark() -> Any:
            async with tenant_session(
                db_session_factory, wallet.org_id, db_role=WORKER_ROLE
            ) as session:
                return await run_mtm_cycle(
                    session,
                    wallet=reference,
                    marks={wallet.market_id: GAP_PRICE},
                    betas=None,
                    exit_cost_rate=NO_EXIT_COST,
                    now=MARK_AT,
                )

        seller = asyncio.create_task(sell())
        await sold.wait()
        marker = asyncio.create_task(mark())
        await seller
        result = await marker

        # The MTM never read the wallet's cash while the sale was uncommitted.
        assert slipped_in == [False]
        assert result.equity != TORN_EQUITY
        assert result.equity == TRUE_EQUITY
