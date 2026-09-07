"""T3.5b item 3 — the dust of a spot exit is not a position.

A spot buy pays its fee in the coin, so the wallet receives ``qty × 0,999`` and
almost never a whole number of ``step_size``: 18,499482 units sell 18,499 and
**0,000482** stay, below ``min_qty``, unsellable at any price. That is the
normal case, not an edge one.

The decision (orchestrator, delegated): a residual below the exchange minimum
does not take a slot, does not count as exposure to the risk engine and does not
make the coin a duplicate — and it stays **visible and valued in the patrimony**
at the same mark, as dust. Before this fix the residual kept ``slots_used`` at 1
and refused the wallet a second order in that coin for ever: four hours after the
stop, one of five slots was still held by 0,000482 units worth 4,6 cents.

The marker on the row is ``positions.status = 'closing'`` plus the intention's
``blocked_residual`` (a durable ``positions.is_residual`` is filed for T3.1e in
``notes-T3.5.md``).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import ExitIntentState, PositionStatus
from hunter_core.portfolio.state import build_portfolio_state

from .builders import NO_EXIT_COST, NOW, create_tenant
from .scenarios import (
    DUST,
    GAP_PRICE,
    WORKER_ROLE,
    admit_one,
    count_of,
    entry_snapshot,
    gap_snapshot,
    open_a_position,
    protect,
    run_entries,
    static,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .builders import Wallet

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MARK_AT = NOW + timedelta(seconds=60)
SECOND_ENTRY_AT = NOW + timedelta(hours=4)
"""Four hours after the stop — the interval the guardian's scenario used."""

DUST_NOTIONAL = DUST * GAP_PRICE
"""0,045790 USDT: small, owned, and part of the patrimony."""

CASH_AFTER = Decimal("19903.847595")
EQUITY_WITH_DUST = CASH_AFTER + DUST_NOTIONAL


async def _state(factory: async_sessionmaker[AsyncSession], wallet: Wallet, *, now: object):  # type: ignore[no-untyped-def]
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await build_portfolio_state(
            session,
            organization_id=wallet.org_id,
            portfolio_id=wallet.portfolio_id,
            as_of=now,  # type: ignore[arg-type]
            marks={wallet.market_id: GAP_PRICE},
            exit_cost_rate=NO_EXIT_COST,
            betas={wallet.market_id: Decimal(1)},
        )


class TestDustDoesNotHoldASlotOrTheCoin:
    async def test_after_the_stop_the_residual_is_valued_but_frees_the_slot(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_a_position(db_session_factory, db_engine, tenant)

        outcomes = await protect(db_session_factory, wallet, gap_snapshot(tenant))
        assert [outcome.status for outcome in outcomes] == ["filled"]

        async with db_engine.begin() as connection:
            position = (
                await connection.execute(
                    text(
                        "SELECT qty, status::text AS status FROM positions WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
            intent_state = await connection.scalar(
                text("SELECT state::text FROM portfolio_exit_intents WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )
        assert position.qty == DUST
        assert position.status == PositionStatus.CLOSING.value
        assert intent_state == ExitIntentState.BLOCKED_RESIDUAL.value

        build = await _state(db_session_factory, wallet, now=MARK_AT)

        assert build.state is not None
        # Visible and valued: the dust is in the exposure and in the patrimony.
        assert build.exposure_notional == DUST_NOTIONAL
        assert build.cash == CASH_AFTER
        assert build.equity == EQUITY_WITH_DUST
        # And it is not a position: no slot, no coin held, no planned risk.
        assert build.state.slots_used == 0
        assert build.state.open_positions == ()
        assert build.state.assets_held == frozenset()
        assert build.state.marks_complete is True

    async def test_a_second_order_in_the_same_coin_is_approved_and_filled(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_a_position(db_session_factory, db_engine, tenant)
        await protect(db_session_factory, wallet, gap_snapshot(tenant))

        second = await admit_one(
            db_session_factory,
            wallet,
            client_key="manual-2",
            now=SECOND_ENTRY_AT,
            price=GAP_PRICE,
            entry_ref=GAP_PRICE,
            stop=Decimal("92.625"),
        )

        assert second.approved, second.decision.rejection_reasons
        assert "duplicate_position" not in second.decision.rejection_reasons
        assert "concurrent_positions" not in second.decision.rejection_reasons

        filled_at = SECOND_ENTRY_AT + timedelta(seconds=1)
        again = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, entry_snapshot(tenant, at=filled_at)),
            now=filled_at,
        )

        assert [outcome.status for outcome in again] == ["filled"]
        # The dust row and the new position both exist: nothing was overwritten.
        assert await count_of(db_engine, wallet, "positions") == 2
