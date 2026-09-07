"""The setup the T3.5b review suites share: admit, enter, protect.

Deliberately **not** in ``builders.py``: that module belongs to T3.14 while the
bridge lands, and a shared file edited by two tasks at once is a merge conflict
with money in it. What lives here is only the *sequence* — a wallet that admits
one request, fills it and then meets a tape — never a number: every quantity and
price still comes from ``builders``, which is what keeps the closed figures of
``spec-T3.9-verificacoes.md`` §0 in exactly one place.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.protection import run_protection_cycle
from hunter_execution_worker.wallet import WalletRef

from .builders import (
    NO_EXIT_COST,
    NOW,
    beta_for,
    book,
    liquidity_for,
    market_identity,
    open_wallet,
    request_for,
    spec_for,
    trade,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_execution_worker.protection import ProtectionOutcome
    from hunter_execution_worker.triggering import DegradedRetries

    from .builders import Tenant, Wallet

WORKER_ROLE = "hunter_worker"
FILL_AT = NOW + timedelta(seconds=1)
STOP_AT = NOW + timedelta(seconds=30)
CYCLE_AT = STOP_AT + timedelta(seconds=1)
GAP_PRICE = Decimal(95)
NET_BASE = Decimal("18.499482")
SOLD = Decimal("18.499")
DUST = NET_BASE - SOLD
"""``0,000482`` — below ``min_qty``, so unsellable at any price."""


def entry_snapshot(tenant: Tenant, *, at: Any = FILL_AT) -> SpotSnapshot:
    """A book received after the declared latency, and one fresh print."""
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(tenant, received_at=at),
        trades=(trade(tenant, price=Decimal(100), ts=at, trade_id=1),),
        avg_price=Decimal(100),
    )


def gap_snapshot(tenant: Tenant, *, trade_id: int = 2) -> SpotSnapshot:
    """The tape gaps straight through the stop, and the book gapped with it."""
    return SpotSnapshot(
        market=market_identity(tenant),
        book=book(
            tenant,
            received_at=STOP_AT + timedelta(milliseconds=200),
            bid=GAP_PRICE,
            ask=Decimal("95.05"),
        ),
        trades=(trade(tenant, price=GAP_PRICE, ts=STOP_AT, trade_id=trade_id),),
        avg_price=Decimal(100),
    )


def no_book_snapshot(tenant: Tenant, *, ts: Any = STOP_AT, trade_id: int = 2) -> SpotSnapshot:
    """The tape crosses the stop and there is no book at all (V9)."""
    return SpotSnapshot(
        market=market_identity(tenant),
        book=None,
        trades=(trade(tenant, price=GAP_PRICE, ts=ts, trade_id=trade_id),),
        avg_price=Decimal(100),
    )


def static(tenant: Tenant, snapshot: SpotSnapshot) -> StaticSpotMarketData:
    return StaticSpotMarketData({(tenant.slug, tenant.symbol): snapshot})


async def admit_one(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    *,
    client_key: str = "manual-1",
    market_id: uuid.UUID | None = None,
    now: Any = NOW,
    price: Decimal = Decimal(100),
    **overrides: Any,
) -> Any:
    """One request through the shared admission service, as the engine."""
    from hunter_core.admission.service import admit

    target = market_id or wallet.market_id
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await admit(
            session,
            request_for(wallet, client_key=client_key, market_id=target, **overrides),
            source="manual",
            liquidity=liquidity_for(wallet.tenant, as_of=now, last_price=price),
            spec=spec_for(wallet.tenant),
            beta=beta_for(as_of=now),
            prices={target: price},
            betas={target: Decimal(1)},
            exit_cost_rate=NO_EXIT_COST,
            now=now,
        )


async def run_entries(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    data: StaticSpotMarketData,
    *,
    now: Any = FILL_AT,
) -> tuple[Any, ...]:
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await execute_approved_entries(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            data=data,
            now=now,
        )


async def open_a_position(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, tenant: Tenant
) -> Wallet:
    """A wallet holding the closed position: 18,499482 units entered at 100."""
    wallet = await open_wallet(factory, engine, tenant)
    await admit_one(factory, wallet)
    outcomes = await run_entries(factory, wallet, static(tenant, entry_snapshot(tenant)))
    assert [outcome.status for outcome in outcomes] == ["filled"]
    return wallet


async def protect(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    snapshot: SpotSnapshot,
    *,
    now: Any = CYCLE_AT,
    retries: DegradedRetries | None = None,
) -> tuple[ProtectionOutcome, ...]:
    async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
        return await run_protection_cycle(
            session,
            wallet=WalletRef(wallet.org_id, wallet.portfolio_id),
            data=static(wallet.tenant, snapshot),
            now=now,
            retries=retries,
        )


async def count_of(engine: AsyncEngine, wallet: Wallet, table: str) -> int:
    """How many rows of ``table`` this wallet has. ``table`` is never input."""
    allowed = ("orders", "fills", "positions", "trades", "portfolio_exit_intents")
    if table not in allowed:
        raise ValueError(f"{table} is not one of {allowed}")
    async with engine.begin() as connection:
        return int(
            await connection.scalar(
                text(f"SELECT count(*) FROM {table} WHERE portfolio_id = :pf"),  # noqa: S608
                {"pf": wallet.portfolio_id},
            )
            or 0
        )


async def block_the_organization(engine: AsyncEngine, wallet: Wallet, *, now: Any) -> None:
    """Latch the **organization** scope, the way the schema demands.

    ``0008``'s ``organizations_move_their_kill_switch_audited`` refuses a move
    whose ``kill_switch_transitions`` row was not written by *this* transaction,
    so the two statements travel together. That is the point of the scenario:
    the block lands between the decision and the order, from somebody else's
    session, exactly as an operator's would.
    """
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, reason, actor_type, actor_id, evidence, created_at) "
                "VALUES (gen_random_uuid(), :org, 'organization', :org, 'ACTIVE', "
                "'TRADING_DISABLED', 'operator blocked the tenant', 'system', NULL, "
                '\'{"source": "test"}\'::jsonb, :now)'
            ),
            {"org": wallet.org_id, "now": now},
        )
        await connection.execute(
            text(
                "UPDATE organizations SET kill_switch_state = 'TRADING_DISABLED', "
                "kill_switch_reason = 'operator blocked the tenant' WHERE id = :org"
            ),
            {"org": wallet.org_id},
        )


async def reservation_of(engine: AsyncEngine, proposal_id: uuid.UUID) -> Any:
    """``(status, reservation_state, reserved_until)`` of one proposal."""
    async with engine.begin() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT status::text AS status, reservation_state::text AS reservation_state, "
                    "reserved_until FROM trade_proposals WHERE id = :id"
                ),
                {"id": proposal_id},
            )
        ).one()
