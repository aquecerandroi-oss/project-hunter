"""T3.5 item 7 and V6 step 5 — nothing in memory is a source of truth.

The "restart" here is real in the only sense that matters: every object the
first half built is dropped, and the second half rebuilds the position, the
intention and the attempts already applied **from Postgres alone**. That is what
makes ``kill -9`` uneventful — there was never anything to lose.

Two boundaries are exercised:

- a protection that filled **nothing** wrote an ``orders`` row and no ``fills``
  row. Deriving the applied attempts from the fills alone would lose it, and the
  redelivery would then land on an intention that had moved on
  (notes-T3.4.md §10.4c). The union of the two keys is what recovers it;
- a protection that filled **part** of its quantity leaves the intention ``open``
  with the remainder. After the restart a new attempt, with an identity of its
  own, finishes the job — never a position of six units silently unprotected.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import ExitIntentState
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.protection import TriggerWatermarks, run_protection_cycle
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
STOP_AT = NOW + timedelta(seconds=30)
CYCLE_AT = STOP_AT + timedelta(seconds=1)
NET_BASE = Decimal("18.499482")
GAP_PRICE = Decimal("95")
SHALLOW = Decimal(10)


async def _open_a_position(factory, engine, tenant):  # type: ignore[no-untyped-def]
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
    entry = SpotSnapshot(
        market=market_identity(tenant),
        book=book(tenant, received_at=FILL_AT),
        trades=(trade(tenant, price=Decimal(100), ts=FILL_AT, trade_id=1),),
        avg_price=Decimal(100),
    )
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        outcomes = await execute_approved_entries(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            data=StaticSpotMarketData({(tenant.slug, tenant.symbol): entry}),
            now=FILL_AT,
        )
    assert [outcome.status for outcome in outcomes] == ["filled"]
    return wallet


def _stop(tenant, *, at, depth=Decimal(1_000), trade_id=2, book_present=True):  # type: ignore[no-untyped-def]
    return SpotSnapshot(
        market=market_identity(tenant),
        book=(
            book(
                tenant,
                received_at=at + timedelta(milliseconds=300),
                bid=GAP_PRICE,
                ask=GAP_PRICE + Decimal("0.05"),
                qty=depth,
            )
            if book_present
            else None
        ),
        trades=(trade(tenant, price=GAP_PRICE, ts=at, trade_id=trade_id),),
        avg_price=Decimal(100),
    )


async def _cycle(factory, wallet, snapshot, now):  # type: ignore[no-untyped-def]
    """One protection pass in a **fresh** object graph — the restart."""
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await run_protection_cycle(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            data=StaticSpotMarketData({(wallet.tenant.slug, wallet.tenant.symbol): snapshot}),
            now=now,
            watermarks=TriggerWatermarks(),  # a restart starts with none
        )


class TestTheWorkerRebuildsItselfFromTheDatabase:
    async def test_an_attempt_that_filled_nothing_is_recovered_from_its_order(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        from hunter_execution_worker.intents_repo import live_intents
        from hunter_execution_worker.reference import load_market

        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)

        degraded = await _cycle(
            db_session_factory, wallet, _stop(tenant, at=STOP_AT, book_present=False), CYCLE_AT
        )
        assert [outcome.status for outcome in degraded] == ["pending_degraded"]
        attempt_id = degraded[0].application.execution_key.removeprefix("exit:")  # type: ignore[union-attr]

        # The restart: a new session, a new object graph, nothing carried over.
        reference = WalletRef(wallet.org_id, wallet.portfolio_id)
        async with tenant_session(db_session_factory, wallet.org_id, db_role=WORKER_ROLE) as s:
            market = await load_market(s, wallet.market_id)
            assert market is not None
            intent = (await live_intents(s, wallet=reference, market=market))[0]

        assert intent.state is ExitIntentState.OPEN
        assert intent.filled_qty == Decimal(0)
        assert intent.degraded_since is not None
        # The attempt wrote an order and no fill; the union of the two keys is
        # what puts it back in the set that makes ``apply_attempt`` idempotent.
        assert uuid.UUID(attempt_id) in intent.applied_attempts

    async def test_a_partial_exit_is_finished_by_a_new_attempt_after_a_restart(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)

        partial = await _cycle(
            db_session_factory,
            wallet,
            _stop(tenant, at=STOP_AT, depth=SHALLOW),
            CYCLE_AT,
        )
        assert [outcome.status for outcome in partial] == ["partially_filled"]

        async with db_engine.begin() as connection:
            after_partial = (
                await connection.execute(
                    text(
                        "SELECT (SELECT qty FROM positions WHERE portfolio_id = :pf) AS qty, "
                        "(SELECT filled_qty FROM portfolio_exit_intents WHERE portfolio_id = :pf) "
                        "AS filled, (SELECT state::text FROM portfolio_exit_intents "
                        "WHERE portfolio_id = :pf) AS state"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert after_partial.filled == SHALLOW
        assert after_partial.qty == NET_BASE - SHALLOW
        assert after_partial.state == ExitIntentState.OPEN.value

        # Restart, deep book, a **new** attempt for the remainder.
        later = CYCLE_AT + timedelta(seconds=10)
        finished = await _cycle(
            db_session_factory,
            wallet,
            _stop(tenant, at=later, trade_id=7),
            later + timedelta(seconds=1),
        )
        assert [outcome.status for outcome in finished] == ["filled"]

        async with db_engine.begin() as connection:
            attempts = [
                row.client_order_id
                for row in await connection.execute(
                    text(
                        "SELECT client_order_id FROM orders WHERE portfolio_id = :pf "
                        "AND side = 'sell' ORDER BY created_at"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ]
            intent = (
                await connection.execute(
                    text(
                        "SELECT filled_qty, state::text AS state FROM portfolio_exit_intents "
                        "WHERE portfolio_id = :pf"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert len(attempts) == 2
        assert attempts[0] != attempts[1]  # each attempt has an identity of its own
        assert intent.filled_qty == Decimal("18.499")
        assert intent.state == ExitIntentState.BLOCKED_RESIDUAL.value
