"""T3.5 items 4 and 5 — the curve, then the switch that reads it. V2/V3 persisted.

Nothing here writes ``kill_switch_state`` by hand: the block is produced by a
**real** mark-to-market of a real position, which is the trap §12.10 of the spec
exists to forbid. The equity falls because the market fell, the point of the
curve records it, and the evaluation that follows finds it.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import KillSwitchState, ReservationState
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.guard import cancel_pending_entries
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.mtm import run_mtm_cycle
from hunter_execution_worker.protection import run_protection_cycle
from hunter_execution_worker.wallet import WalletRef

from .builders import (
    NO_EXIT_COST,
    NOW,
    add_market,
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
MARK_AT = NOW + timedelta(seconds=60)
NET_BASE = Decimal("18.499482")
CASH = Decimal("18148.2000000000")
CRASH_PRICE = Decimal("78")
EXIT_COST = Decimal("0.001")


def _entry_snapshot(tenant):  # type: ignore[no-untyped-def]
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(tenant, received_at=FILL_AT),
        trades=(trade(tenant, price=Decimal(100), ts=FILL_AT, trade_id=1),),
        avg_price=Decimal(100),
    )


async def _admit(factory, wallet, **overrides):  # type: ignore[no-untyped-def]
    from hunter_core.admission.service import admit

    market_id = overrides.pop("market_id", wallet.market_id)
    identity = overrides.pop("market", None)
    spec = overrides.pop("spec", None)
    liquidity = overrides.pop("liquidity", None)
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await admit(
            session,
            request_for(
                wallet,
                market_id=market_id,
                **({"market": identity} if identity is not None else {}),
                **overrides,
            ),
            source="manual",
            liquidity=liquidity or liquidity_for(wallet.tenant),
            spec=spec or spec_for(wallet.tenant),
            beta=beta_for(),
            prices={wallet.market_id: Decimal(100), market_id: Decimal(100)},
            betas={wallet.market_id: Decimal(1), market_id: Decimal(1)},
            exit_cost_rate=NO_EXIT_COST,
            now=NOW,
        )


async def _open_a_position(factory, engine, tenant):  # type: ignore[no-untyped-def]
    wallet = await open_wallet(factory, engine, tenant)
    await _admit(factory, wallet)
    data = StaticSpotMarketData({(tenant.slug, tenant.symbol): _entry_snapshot(tenant)})
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        outcomes = await execute_approved_entries(
            session, wallet=WalletRef(wallet.org_id, wallet.portfolio_id), data=data, now=FILL_AT
        )
    assert [outcome.status for outcome in outcomes] == ["filled"]
    return wallet


async def _mark(factory, wallet, price, now=MARK_AT, fx=None):  # type: ignore[no-untyped-def]
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await run_mtm_cycle(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            marks={wallet.market_id: price} if price is not None else {},
            betas=None,
            exit_cost_rate=EXIT_COST,
            now=now,
            fx=fx,
        )


class TestTheCurveIsWrittenBeforeTheSwitchReadsIt:
    async def test_a_point_with_no_rate_says_why_and_a_stale_mark_says_so_too(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)

        # No mark for the open market at all: the ledger falls back to the last
        # durable one and the point is written **as an estimate**.
        result = await _mark(db_session_factory, wallet, None)

        assert result.stale_marks == (wallet.market_id,)
        async with db_engine.begin() as connection:
            point = (
                await connection.execute(
                    text(
                        "SELECT equity, cash, marks_stale, brl_unavailable_reason, "
                        "fx_observation_id, resolution::text AS resolution "
                        "FROM portfolio_equity_snapshots WHERE portfolio_id = :pf "
                        "AND ts = :ts"
                    ),
                    {"pf": wallet.portfolio_id, "ts": MARK_AT},
                )
            ).one()
        assert point.resolution == "1m"
        assert point.cash == CASH
        assert point.marks_stale is True
        # The opening rate is still inside the policy one minute later, so this
        # point *was* converted and names the observation it used.
        assert point.brl_unavailable_reason is None
        assert point.fx_observation_id is not None

        # Twenty minutes later the same rate is past ``observed_at <= 600 s``:
        # the USDT point is still written and the BRL becomes unavailable **with
        # a reason**, never extrapolated (§18.2).
        late = await _mark(db_session_factory, wallet, None, now=NOW + timedelta(minutes=20))
        assert late.point.brl_unavailable_reason == "fx_rejected"
        async with db_engine.begin() as connection:
            stale_point = (
                await connection.execute(
                    text(
                        "SELECT brl_unavailable_reason, marks_stale, fx_observation_id "
                        "FROM portfolio_equity_snapshots WHERE portfolio_id = :pf AND ts = :ts"
                    ),
                    {"pf": wallet.portfolio_id, "ts": NOW + timedelta(minutes=20)},
                )
            ).one()
        assert stale_point.brl_unavailable_reason == "fx_rejected"
        assert stale_point.marks_stale is True
        assert stale_point.fx_observation_id is None

    async def test_a_two_percent_drop_blocks_entries_cancels_pendings_and_never_a_protection(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await _open_a_position(db_session_factory, db_engine, tenant)
        second = await add_market(db_engine, tenant)
        pending = await _admit(
            db_session_factory,
            wallet,
            client_key="manual-2",
            market_id=second.market_id,
            market=market_identity(second),  # type: ignore[arg-type]
            spec=spec_for(second),  # type: ignore[arg-type]
            liquidity=liquidity_for(second),  # type: ignore[arg-type]
        )
        assert pending.approved, pending.decision.rejection_reasons
        assert pending.reservation_state is ReservationState.HELD

        result = await _mark(db_session_factory, wallet, CRASH_PRICE)

        assert result.evaluation.latched is KillSwitchState.TRADING_DISABLED
        assert result.evaluation.changed is True
        async with db_engine.begin() as connection:
            events = [
                row.stream
                for row in await connection.execute(
                    # The stored payload is the whole envelope; the business body
                    # is nested under it, and ``key`` is the wallet.
                    text("SELECT stream FROM outbox_events WHERE payload->>'key' = :pf"),
                    {"pf": str(wallet.portfolio_id)},
                )
            ]
        assert "kill_switch.changed" in events

        # The blocked wallet gives the pending entry back — audited, and only
        # what was not executed.
        async with tenant_session(db_session_factory, wallet.org_id, db_role=WORKER_ROLE) as s:
            cancelled = await cancel_pending_entries(
                s, wallet=WalletRef(wallet.org_id, wallet.portfolio_id), now=MARK_AT
            )
        assert cancelled == (pending.proposal_id,)

        # ... and the entry cycle refuses to open anything new.
        async with tenant_session(db_session_factory, wallet.org_id, db_role=WORKER_ROLE) as s:
            outcomes = await execute_approved_entries(
                s,
                wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
                data=StaticSpotMarketData({}),
                now=MARK_AT,
            )
        assert outcomes == ()

        # The stop, however, is untouched by the latch: rule 3 of the directive.
        stop_at = MARK_AT + timedelta(seconds=1)
        snapshot = SpotSnapshot(
            market=market_identity(tenant),
            book=book(
                tenant,
                received_at=stop_at + timedelta(milliseconds=300),
                bid=CRASH_PRICE,
                ask=CRASH_PRICE + Decimal("0.05"),
            ),
            trades=(trade(tenant, price=CRASH_PRICE, ts=stop_at, trade_id=9),),
            avg_price=Decimal(100),
        )
        async with tenant_session(db_session_factory, wallet.org_id, db_role=WORKER_ROLE) as s:
            protections = await run_protection_cycle(
                s,
                wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
                data=StaticSpotMarketData({(tenant.slug, tenant.symbol): snapshot}),
                now=stop_at + timedelta(seconds=1),
            )
        assert [outcome.status for outcome in protections] == ["filled"]
        async with db_engine.begin() as connection:
            latch = await connection.scalar(
                text("SELECT kill_switch_state FROM portfolios WHERE id = :pf"),
                {"pf": wallet.portfolio_id},
            )
        assert latch == KillSwitchState.TRADING_DISABLED.value
