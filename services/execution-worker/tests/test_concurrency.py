"""V4 and §11 — two real sessions, one balance, and a redelivered report.

Two **distinct connections**, not two tasks on one session: the second would
serialise inside the driver and exercise no Postgres lock at all (spec §12, trap
8). What is proved is that the position's row lock is what stops the same unit
being sold twice, and that re-applying a report that already landed moves
nothing.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.protection import run_protection_cycle
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
CYCLE_AT = STOP_AT + timedelta(seconds=1)
NET_BASE = Decimal("18.499482")
SOLD = Decimal("18.499")
GAP_PRICE = Decimal("95")
ATTEMPT_ID = uuid.UUID("0193f7f0-0000-7000-8000-000000000001")
"""A fixed attempt id, so "the same report delivered twice" is literally the same."""


def _entry_snapshot(tenant: Tenant) -> SpotSnapshot:
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(tenant, received_at=FILL_AT),
        trades=(trade(tenant, price=Decimal(100), ts=FILL_AT, trade_id=1),),
        avg_price=Decimal(100),
    )


def _stop_snapshot(tenant: Tenant) -> SpotSnapshot:
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(
            tenant,
            received_at=STOP_AT + timedelta(milliseconds=300),
            bid=GAP_PRICE,
            ask=GAP_PRICE + Decimal("0.05"),
        ),
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
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        outcomes = await execute_approved_entries(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            data=StaticSpotMarketData({(tenant.slug, tenant.symbol): _entry_snapshot(tenant)}),
            now=FILL_AT,
        )
    assert [outcome.status for outcome in outcomes] == ["filled"]
    return wallet


class TestTwoSessionsNeverSellTheSameUnitTwice:
    async def test_two_concurrent_protection_cycles_sell_the_position_once(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)
        data = StaticSpotMarketData({(tenant.slug, tenant.symbol): _stop_snapshot(tenant)})
        reference = WalletRef(wallet.org_id, wallet.portfolio_id)

        async def cycle() -> tuple[str, ...]:
            async with tenant_session(
                db_session_factory, wallet.org_id, db_role=WORKER_ROLE
            ) as session:
                outcomes = await run_protection_cycle(
                    session, wallet=reference, data=data, now=CYCLE_AT
                )
                return tuple(outcome.status for outcome in outcomes)

        first, second = await asyncio.gather(cycle(), cycle())

        async with db_engine.begin() as connection:
            sold = await connection.scalar(
                text(
                    "SELECT coalesce(sum(f.qty), 0) FROM fills f JOIN orders o ON o.id = f.order_id "
                    "WHERE f.portfolio_id = :pf AND o.side = 'sell'"
                ),
                {"pf": wallet.portfolio_id},
            )
            position = await connection.scalar(
                text("SELECT qty FROM positions WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )
        # Exactly one of the two sold, and never more than the position held.
        assert sold == SOLD
        assert sold <= NET_BASE
        assert position == NET_BASE - SOLD
        assert ("filled",) in (first, second)

    async def test_a_redelivered_exit_report_moves_nothing_a_second_time(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        from hunter_core.execution.intents import ExitAttempt
        from hunter_core.execution.paper import PaperExecutionAdapter
        from hunter_execution_worker.apply import apply_exit
        from hunter_execution_worker.intents_repo import live_intents
        from hunter_execution_worker.positions import load_open_positions
        from hunter_execution_worker.reference import load_market

        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)
        reference = WalletRef(wallet.org_id, wallet.portfolio_id)
        snapshot = _stop_snapshot(tenant)

        async def apply_once() -> str:
            async with tenant_session(
                db_session_factory, wallet.org_id, db_role=WORKER_ROLE
            ) as session:
                market = await load_market(session, wallet.market_id)
                assert market is not None
                position = (await load_open_positions(session, wallet=reference))[0]
                intent = (await live_intents(session, wallet=reference, market=market))[0]
                attempt = ExitAttempt.for_intent(
                    intent,
                    qty=position.qty,
                    decision_at=STOP_AT,
                    position_qty=position.qty,
                    attempt_id=ATTEMPT_ID,
                )
                report = PaperExecutionAdapter().submit_protection_exit(
                    attempt,
                    position.qty,
                    snapshot.book,
                    snapshot.last_trade,
                    market.filters,
                    market.fees,
                    CYCLE_AT,
                    avg_price=snapshot.avg_price,
                )
                application = await apply_exit(
                    session,
                    wallet=reference,
                    market=market,
                    attempt=attempt,
                    report=report,
                    position=position,
                    now=CYCLE_AT,
                    source="test_fixture",
                )
                return "replayed" if application.replayed else application.status

        assert await apply_once() == "filled"
        async with db_engine.begin() as connection:
            before = (
                await connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM fills WHERE portfolio_id = :pf) AS fills, "
                        "(SELECT count(*) FROM orders WHERE portfolio_id = :pf) AS orders, "
                        "(SELECT qty FROM positions WHERE portfolio_id = :pf) AS qty, "
                        "(SELECT filled_qty FROM portfolio_exit_intents "
                        "WHERE portfolio_id = :pf) AS intent_filled"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()

        # The very same attempt id, delivered again.
        assert await apply_once() == "replayed"

        async with db_engine.begin() as connection:
            after = (
                await connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM fills WHERE portfolio_id = :pf) AS fills, "
                        "(SELECT count(*) FROM orders WHERE portfolio_id = :pf) AS orders, "
                        "(SELECT qty FROM positions WHERE portfolio_id = :pf) AS qty, "
                        "(SELECT filled_qty FROM portfolio_exit_intents "
                        "WHERE portfolio_id = :pf) AS intent_filled"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert (after.fills, after.orders, after.qty, after.intent_filled) == (
            before.fills,
            before.orders,
            before.qty,
            before.intent_filled,
        )
