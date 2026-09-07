"""T3.5 item 2 — the order cycle: an approved proposal becomes a fill, once.

Every number here is the closed one of ``spec-T3.9-verificacoes.md`` §0/V1/V5:
20.000 USDT of equity, entry_ref 100, stop 97,5, ``qty = 18,518``,
``gross = 1.851,800``, taker fee of 10 bps charged **in the base asset**
(``0,01851800``), ``net_base_delta = 18,499482`` and cash of ``18.148,2``.
Nothing is asserted with a tolerance: money is compared exactly.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import ExitIntentState, ReservationState
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.wallet import WalletRef

from .builders import (
    NO_EXIT_COST,
    NOW,
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
QTY = Decimal("18.518")
GROSS = Decimal("1851.800")
FEE_BASE = Decimal("0.01851800")
NET_BASE = Decimal("18.499482")
CASH_AFTER = Decimal("18148.2000000000")


async def _admit(factory, wallet, engine):  # type: ignore[no-untyped-def]
    from hunter_core.admission.service import admit

    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await admit(
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


def _snapshot(tenant):  # type: ignore[no-untyped-def]
    """A book received after the declared latency, and one fresh print."""
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(tenant, received_at=FILL_AT),
        trades=(trade(tenant, price=Decimal(100), ts=FILL_AT, trade_id=1),),
        avg_price=Decimal(100),
    )


async def _run_entries(factory, wallet, data):  # type: ignore[no-untyped-def]
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await execute_approved_entries(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            data=data,
            now=FILL_AT,
        )


async def _counts(engine: AsyncEngine, wallet) -> dict[str, int]:  # type: ignore[no-untyped-def]
    async with engine.begin() as connection:
        rows = {}
        for table in ("orders", "fills", "positions", "portfolio_exit_intents"):
            rows[table] = int(
                await connection.scalar(
                    # S608: ``table`` comes from the literal tuple above, never
                    # from input; the value is a bound parameter.
                    text(f"SELECT count(*) FROM {table} WHERE portfolio_id = :pf"),  # noqa: S608
                    {"pf": wallet.portfolio_id},
                )
                or 0
            )
        rows["participation_executed"] = int(
            await connection.scalar(
                text(
                    "SELECT count(*) FROM participation_consumptions "
                    "WHERE portfolio_id = :pf AND kind = 'executed'"
                ),
                {"pf": wallet.portfolio_id},
            )
            or 0
        )
        return rows


async def _cash(factory, wallet) -> Decimal:  # type: ignore[no-untyped-def]
    from hunter_core.db.repositories.ledger import LedgerRepository
    from hunter_core.db.repositories.portfolio import PortfolioRepository

    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        anchor = await PortfolioRepository(session, wallet.org_id).get_anchor(wallet.portfolio_id)
        assert anchor is not None
        reconciliation = await LedgerRepository(session, wallet.org_id).reconcile_cash(
            wallet.portfolio_id,
            credited=anchor.credited_amount,
            operating_currency=anchor.operating_currency,
        )
        return reconciliation.cash


class TestOneApprovedProposalBecomesOneFilledPosition:
    async def test_the_fill_moves_cash_quantity_fees_reservation_and_protection_together(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await _admit(db_session_factory, wallet, db_engine)
        assert decision.approved, decision.decision.rejection_reasons
        assert decision.decision.sizing is not None
        assert decision.decision.sizing.qty == QTY

        outcomes = await _run_entries(
            db_session_factory,
            wallet,
            StaticSpotMarketData({(tenant.slug, tenant.symbol): _snapshot(tenant)}),
        )

        assert [outcome.status for outcome in outcomes] == ["filled"]
        assert await _cash(db_session_factory, wallet) == CASH_AFTER
        async with db_engine.begin() as connection:
            fill = (
                await connection.execute(
                    text(
                        "SELECT qty, price, fee, fee_asset, execution_key, metadata FROM fills "
                        "WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
            position = (
                await connection.execute(
                    text(
                        "SELECT qty, avg_entry_price, status::text AS status FROM positions "
                        "WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
            proposal = (
                await connection.execute(
                    text(
                        "SELECT reservation_state::text AS state, reserved_slot "
                        "FROM trade_proposals WHERE id = :id"
                    ),
                    {"id": decision.proposal_id},
                )
            ).one()
            intent = (
                await connection.execute(
                    text(
                        "SELECT protection_key, intended_qty, trigger_price, state::text AS state "
                        "FROM portfolio_exit_intents WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert fill.qty == QTY
        assert fill.price == Decimal(100)
        assert fill.fee == FEE_BASE
        assert fill.fee_asset == tenant.base_symbol
        assert fill.execution_key == f"entry:{decision.proposal_id}"
        # The two identity fields T3.4b added: without them a replay guard
        # rebuilt from Postgres matches any quantity (notes-T3.4.md §12).
        assert Decimal(fill.metadata["submitted_qty"]) == QTY
        assert fill.metadata["decision_fingerprint"]
        assert position.qty == NET_BASE
        assert position.avg_entry_price == Decimal(100)
        assert position.status == "open"
        assert proposal.state == ReservationState.CONSUMED.value
        assert proposal.reserved_slot is False
        assert intent.protection_key == "stop"
        assert intent.intended_qty == NET_BASE
        assert intent.trigger_price == Decimal("97.5")
        assert intent.state == ExitIntentState.OPEN.value

    async def test_the_same_report_delivered_twice_moves_nothing_a_second_time(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        await _admit(db_session_factory, wallet, db_engine)
        data = StaticSpotMarketData({(tenant.slug, tenant.symbol): _snapshot(tenant)})

        await _run_entries(db_session_factory, wallet, data)
        counts, cash = await _counts(db_engine, wallet), await _cash(db_session_factory, wallet)

        again = await _run_entries(db_session_factory, wallet, data)

        assert again == ()
        assert await _counts(db_engine, wallet) == counts
        assert await _cash(db_session_factory, wallet) == cash
