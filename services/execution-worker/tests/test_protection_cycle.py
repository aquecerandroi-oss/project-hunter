"""T3.5 item 3 — the protection cycle, and V8/V9 through the persisted path.

The geometry is the closed one: a position of ``18,499482`` units entered at
100 with a stop at ``97,5``. A gap prints straight through to ``95,00`` — no
intermediate price is negotiated and no candle is consulted — so the fill is
**worse than the plan** and says so: ``slippage_vs_plan_quote = 46,248705`` and
``slippage_vs_plan_bps = 256,41025641``. Nothing corrects it back to the stop.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import ExitIntentState, PositionStatus
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.protection import ProtectionOutcome, run_protection_cycle
from hunter_execution_worker.wallet import WalletRef

from .builders import (
    NO_EXIT_COST,
    NOW,
    Tenant,
    Wallet,
    beta_for,
    book,
    create_tenant,
    liquidity_for,
    market_identity,
    open_wallet,
    request_for,
    spec_for,
    trade,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WORKER_ROLE = "hunter_worker"
FILL_AT = NOW + timedelta(seconds=1)
STOP_AT = NOW + timedelta(seconds=30)
BOOK_AT = STOP_AT + timedelta(milliseconds=200)
CYCLE_AT = STOP_AT + timedelta(seconds=1)
NET_BASE = Decimal("18.499482")
"""What the wallet really received: 18,518 bought minus 0,018518 of fee, in coins."""
SOLD = Decimal("18.499")
"""What the exchange lets it sell back: ``NET_BASE`` floored to ``step = 0,001``."""
DUST = NET_BASE - SOLD
"""``0,000482`` — below ``min_qty``, so unsellable. Accounted and visible,
never quitted as if it had been sold (RISK_ENGINE.md §10, spec V7 item 5)."""
GAP_PRICE = Decimal("95")
EXIT_GROSS = Decimal("1757.405")
EXIT_FEE = Decimal("1.75740500")
CASH_AFTER = Decimal("19903.8475950000")
SLIPPAGE_QUOTE = Decimal("46.24750000")
SLIPPAGE_BPS = Decimal("256.41025641")
REALIZED = SOLD * (GAP_PRICE - Decimal(100))


def _entry_snapshot(tenant: Tenant) -> SpotSnapshot:
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(tenant, received_at=FILL_AT),
        trades=(trade(tenant, price=Decimal(100), ts=FILL_AT, trade_id=1),),
        avg_price=Decimal(100),
    )


def _gap_snapshot(tenant: Tenant) -> SpotSnapshot:
    """A gap: the tape jumps from 100 to 95 and the book gapped with it."""
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(tenant, received_at=BOOK_AT, bid=GAP_PRICE, ask=Decimal("95.05")),
        trades=(trade(tenant, price=GAP_PRICE, ts=STOP_AT, trade_id=2),),
        avg_price=Decimal(100),
    )


def _no_book_snapshot(tenant: Tenant) -> SpotSnapshot:
    """The tape crosses the stop and there is no book at all: V9."""
    return SpotSnapshot(
        market=market_identity(tenant),
        book=None,
        trades=(trade(tenant, price=GAP_PRICE, ts=STOP_AT, trade_id=2),),
        avg_price=Decimal(100),
    )


async def _open_a_position(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, tenant: Tenant
) -> Wallet:
    from hunter_core.admission.service import admit

    wallet = await open_wallet(factory, engine, tenant)
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        await admit(
            session,
            request_for(wallet),
            source="manual",
            liquidity=liquidity_for(wallet.tenant),
            spec=spec_for(wallet.tenant),
            beta=beta_for(),
            prices={wallet.market_id: Decimal(100)},
            betas={wallet.market_id: Decimal(1)},
            exit_cost_rate=NO_EXIT_COST,
            now=NOW,
        )
    data = StaticSpotMarketData({(tenant.slug, tenant.symbol): _entry_snapshot(tenant)})
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        outcomes = await execute_approved_entries(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            data=data,
            now=FILL_AT,
        )
    assert [outcome.status for outcome in outcomes] == ["filled"]
    return wallet


async def _protect(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    snapshot: SpotSnapshot,
    now: datetime = CYCLE_AT,
) -> tuple[ProtectionOutcome, ...]:
    data = StaticSpotMarketData({(wallet.tenant.slug, wallet.tenant.symbol): snapshot})
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await run_protection_cycle(
            session, wallet=WalletRef(wallet.org_id, wallet.portfolio_id), data=data, now=now
        )


async def _cash(factory: async_sessionmaker[AsyncSession], wallet: Wallet) -> Decimal:
    from hunter_core.db.repositories.ledger import LedgerRepository
    from hunter_core.db.repositories.portfolio import PortfolioRepository

    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        anchor = await PortfolioRepository(session, wallet.org_id).get_anchor(wallet.portfolio_id)
        assert anchor is not None
        return (
            await LedgerRepository(session, wallet.org_id).reconcile_cash(
                wallet.portfolio_id,
                credited=anchor.credited_amount,
                operating_currency=anchor.operating_currency,
            )
        ).cash


class TestAStopThatFiresIsExecutedAndReconciled:
    async def test_the_gap_fills_worse_than_the_plan_and_the_number_is_published(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)

        outcomes = await _protect(db_session_factory, wallet, _gap_snapshot(tenant))

        assert [outcome.status for outcome in outcomes] == ["filled"]
        assert await _cash(db_session_factory, wallet) == CASH_AFTER
        async with db_engine.begin() as connection:
            fill = (
                await connection.execute(
                    text(
                        "SELECT f.qty, f.price, f.fee, f.fee_asset, f.slippage_bps, f.metadata "
                        "FROM fills f JOIN orders o ON o.id = f.order_id "
                        "WHERE f.portfolio_id = :pf AND o.side = 'sell'"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
            position = (
                await connection.execute(
                    text(
                        "SELECT qty, status::text AS status, realized_pnl FROM positions "
                        "WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
            intent = (
                await connection.execute(
                    text(
                        "SELECT state::text AS state, filled_qty FROM portfolio_exit_intents "
                        "WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
            closed = (
                await connection.execute(
                    text(
                        "SELECT qty, entry_price, exit_price, pnl, fees, exit_reason::text AS why "
                        "FROM trades WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert fill.qty == SOLD
        assert fill.price == GAP_PRICE
        assert fill.fee == EXIT_FEE
        assert fill.fee_asset == "USDT"
        assert fill.slippage_bps == SLIPPAGE_BPS
        assert Decimal(fill.metadata["slippage_vs_plan_quote"]) == SLIPPAGE_QUOTE
        # The dust is still owned, still valued, and still visible.
        assert position.qty == DUST
        assert position.status == PositionStatus.CLOSING.value
        assert position.realized_pnl == REALIZED
        # ``blocked_residual``, never ``fulfilled``: the intended quantity was
        # not liquidated, and the database refuses to say it was.
        assert intent.state == ExitIntentState.BLOCKED_RESIDUAL.value
        assert intent.filled_qty == SOLD
        assert closed.qty == SOLD
        assert closed.entry_price == Decimal(100)
        assert closed.exit_price == GAP_PRICE
        assert closed.why == "stop"
        # Net of every fee the position paid: the gross result minus the costs,
        # counted exactly once.
        assert closed.pnl == REALIZED - closed.fees

    async def test_a_stop_with_no_book_never_fabricates_a_fill_and_retries_with_a_new_identity(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)

        degraded = await _protect(db_session_factory, wallet, _no_book_snapshot(tenant))

        assert [outcome.status for outcome in degraded] == ["pending_degraded"]
        async with db_engine.begin() as connection:
            sells = int(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM fills f JOIN orders o ON o.id = f.order_id "
                        "WHERE f.portfolio_id = :pf AND o.side = 'sell'"
                    ),
                    {"pf": wallet.portfolio_id},
                )
                or 0
            )
            intent = (
                await connection.execute(
                    text(
                        "SELECT state::text AS state, degraded_reason FROM portfolio_exit_intents "
                        "WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert sells == 0
        assert intent.state == ExitIntentState.OPEN.value
        assert intent.degraded_reason

        # The book comes back one cycle later: a **new** attempt, with its own
        # identity, for the same intention — never a second consumption of the
        # quantity already tried.
        later = CYCLE_AT + timedelta(seconds=1)
        recovered = SpotSnapshot(
            market=market_identity(tenant),
            book=book(
                tenant,
                received_at=CYCLE_AT + timedelta(milliseconds=800),
                bid=GAP_PRICE,
                ask=Decimal("95.05"),
            ),
            trades=(
                trade(
                    tenant,
                    price=GAP_PRICE,
                    ts=CYCLE_AT + timedelta(milliseconds=400),
                    trade_id=3,
                ),
            ),
            avg_price=Decimal(100),
        )
        again = await _protect(db_session_factory, wallet, recovered, now=later)

        assert [outcome.status for outcome in again] == ["filled"]
        async with db_engine.begin() as connection:
            attempts = int(
                await connection.scalar(
                    text("SELECT count(*) FROM orders WHERE portfolio_id = :pf AND side = 'sell'"),
                    {"pf": wallet.portfolio_id},
                )
                or 0
            )
            filled = await connection.scalar(
                text("SELECT filled_qty FROM portfolio_exit_intents WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )
        assert attempts == 2
        assert filled == SOLD
