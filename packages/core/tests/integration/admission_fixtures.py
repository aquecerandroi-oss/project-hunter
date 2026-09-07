"""Shared setup for the T3.12 admission tests: an opened wallet and the inputs.

Not a ``conftest.py`` on purpose — these are helpers three test modules import,
and each of those modules is run on its own (one testcontainer per file).

The numbers are the closed ones of ``.claude/state/spec-T3.9-verificacoes.md``
§0: R$100.000 at a test rate of 5,00 BRL/USDT credits exactly 20.000 USDT, and
the SOL-like synthetic market of ``packages/risk-core/tests/unit/factories.py``
(``step_size=0,001``, ``min_notional=5``) with ``entry_ref=100``,
``stop=97,5``. V1 of that spec says what has to come out: ``binding_constraint =
risk_per_trade``, ``qty = 18,518``, ``notional = 1.851,800``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.admission.sources import ProposalRequest
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import MarketType, TradeDirection
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.inputs import BetaEstimate, BookLevel, MarketIdentity, MarketLiquidity, MarketSpec

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from packages.core.tests.integration.conftest import LedgerTenant

NOW = datetime(2026, 9, 6, 15, 30, tzinfo=UTC)
RATE = Decimal("5.0000000000")
CREDITED = Decimal("20000.0000000000")
NO_EXIT_COST = Decimal(0)

ENGINE_ROLE = "hunter_worker"
"""The database role admission runs as.

``portfolio_risk_state`` is the engine's row: T3.1b's guard refuses every
``UPDATE`` issued by ``hunter_app``, and ``fifo_v1`` is a counter on that row
(DATABASE.md §18.7). ``hunter_app`` also has no ``INSERT`` on ``outbox_events``.
Both are recorded as blocking couplings for T3.8 in ``.claude/state/
notes-T3.12.md`` §2; the tests declare the role instead of hiding the fact.
"""

ORG_ROW_LOCK_GRANT = 'GRANT UPDATE ("updated_at") ON organizations TO hunter_worker'
"""**A privilege T3.1b still has to add**, applied by these tests so the service
can be proved at all — and reported as a blocking coupling, never hidden.

The contract's lock order is system -> organization -> portfolio, and the middle
rung is ``SELECT ... FOR SHARE`` on ``organizations``
(``hunter_core.risk.transitions.organization_kill_switch``). PostgreSQL charges
``ACL_UPDATE`` for a row mark, and ``hunter_worker`` — the role that owns
``portfolio_risk_state`` and therefore the only role that can advance
``fifo_v1`` — has ``SELECT`` and ``DELETE`` on ``organizations`` but no
``UPDATE``. So admission fails with *permission denied for table organizations*
before it decides anything.

The shape asked for is the one T3.1b itself measured for ``portfolio_risk_state``
(``ddl/paper.py``, ``PAPER_LOCK_ONLY_TABLES``): a **column** grant, which lets
the role take the row lock and refuses every ``UPDATE`` that writes a value. It
is strictly narrower than the ``DELETE`` the role already holds on the same
table. ``.claude/state/notes-T3.12.md`` §2 carries the request.
"""

COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)
"""``factories.COSTS`` of the pure core: 2 bps spread, 5 bps slippage, 4 bps fee."""

CASH_MULTIPLIER = Decimal("1.00100024")
"""``(1 + 0,0006) x (1 + 0,0004)`` — what one unit of notional holds of the cash."""


def market_identity(tenant: LedgerTenant) -> MarketIdentity:
    return MarketIdentity(
        exchange=tenant.slug,
        symbol=tenant.symbol,
        market_type=MarketType.SPOT,
        base_asset=tenant.base_symbol,
        quote_asset="USDT",
    )


def spec_for(tenant: LedgerTenant) -> MarketSpec:
    return MarketSpec(
        market=market_identity(tenant),
        step_size=Decimal("0.001"),
        min_notional=Decimal(5),
        tick_size=Decimal("0.01"),
    )


def liquidity_for(
    tenant: LedgerTenant,
    *,
    as_of: datetime = NOW,
    last_price: Decimal = Decimal(100),
    minute_volume: Decimal = Decimal(50_000_000),
    depth: Decimal = Decimal(10_000),
) -> MarketLiquidity:
    """A healthy market: fresh price, deep book, 24 h volume above the floor."""
    return MarketLiquidity(
        market=market_identity(tenant),
        last_price=last_price,
        mid_price=last_price,
        best_bid=last_price * Decimal("0.9999"),
        best_ask=last_price * Decimal("1.0001"),
        price_ts=as_of,
        asks=(
            BookLevel(price=last_price * Decimal("1.0001"), qty=depth),
            BookLevel(price=last_price * Decimal("1.0005"), qty=depth),
        ),
        book_ts=as_of,
        quote_volume_24h=Decimal(100_000_000),
        last_minute_quote_volume=minute_volume,
        median_30m_quote_volume=minute_volume,
        volume_window_complete=True,
        volume_ts=as_of,
        gap_state="ok",
        in_universe=True,
    )


def beta_for(*, as_of: datetime = NOW, validated: bool = True) -> BetaEstimate:
    return BetaEstimate(value=Decimal("1.0"), as_of=as_of, validated=validated, bars=120)


async def apply_pending_grants(engine: AsyncEngine) -> None:
    """Apply :data:`ORG_ROW_LOCK_GRANT`. Additive, and labelled as pending."""
    async with engine.begin() as connection:
        await connection.execute(text(ORG_ROW_LOCK_GRANT))


class Wallet:
    """An opened paper wallet plus the ids its tests need."""

    def __init__(self, tenant: LedgerTenant, portfolio_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.portfolio_id = portfolio_id
        self.org_id = tenant.org_id
        self.market_id = tenant.market_id


async def open_wallet(
    factory: async_sessionmaker[AsyncSession],
    tenant: LedgerTenant,
    observe_fx: Callable[..., Awaitable[uuid.UUID]],
    *,
    as_of: datetime = NOW,
) -> Wallet:
    from hunter_core.db.repositories.fx import FxObservationRepository
    from hunter_core.portfolio.opening import open_paper_wallet

    fx_id = await observe_fx(rate=RATE, observed_at=as_of)
    async with tenant_session(factory, tenant.org_id) as session:
        observation = await FxObservationRepository(session).get(fx_id)
        assert observation is not None
        result = await open_paper_wallet(
            session,
            organization_id=tenant.org_id,
            workspace_id=tenant.workspace_id,
            fx=observation,
            as_of=as_of,
        )
    return Wallet(tenant, result.portfolio_id)


def request_for(
    wallet: Wallet,
    *,
    client_key: str = "manual-1",
    entry_ref: Decimal = Decimal(100),
    stop: Decimal = Decimal("97.5"),
    **overrides: Any,
) -> ProposalRequest:
    fields: dict[str, Any] = {
        "client_key": client_key,
        "organization_id": wallet.org_id,
        "portfolio_id": wallet.portfolio_id,
        "market_id": wallet.market_id,
        "market": market_identity(wallet.tenant),
        "direction": TradeDirection.LONG,
        "entry_ref": entry_ref,
        "stop": stop,
        "assumed_costs": COSTS,
        "actor_id": str(uuid.uuid4()),
    }
    fields.update(overrides)
    return ProposalRequest.model_validate(fields)


async def admit_default(
    session: AsyncSession,
    wallet: Wallet,
    request: ProposalRequest,
    *,
    now: datetime = NOW,
    liquidity: MarketLiquidity | None = None,
    beta: BetaEstimate | None = None,
    **overrides: Any,
) -> Any:
    """``admit`` with the healthy market of this module as the default input."""
    from hunter_core.admission.service import admit

    return await admit(
        session,
        request,
        source=overrides.pop("source", "manual"),
        liquidity=liquidity or liquidity_for(wallet.tenant, as_of=now),
        spec=spec_for(wallet.tenant),
        beta=beta or beta_for(as_of=now),
        prices=overrides.pop("prices", {wallet.market_id: Decimal(100)}),
        betas=overrides.pop("betas", {wallet.market_id: Decimal(1)}),
        exit_cost_rate=overrides.pop("exit_cost_rate", NO_EXIT_COST),
        now=now,
        **overrides,
    )


async def buy_filled(
    engine: AsyncEngine,
    wallet: Wallet,
    *,
    qty: Decimal,
    price: Decimal,
    stop: Decimal,
    ts: datetime = NOW,
) -> uuid.UUID:
    """One entry that already filled: order, fill and the position it opened.

    Written as the container owner because the *writer* of these rows is T3.5,
    which does not exist yet; what is under test is what admission reads back
    from them.
    """
    from hunter_core.domain.types import uuid7

    order_id, fill_id, position_id = uuid7(), uuid7(), uuid7()
    params = {
        "org": wallet.org_id,
        "pf": wallet.portfolio_id,
        "market": wallet.market_id,
        "order": order_id,
        "fill": fill_id,
        "position": position_id,
        "qty": qty,
        "price": price,
        "stop": stop,
        "ts": ts,
        "key": f"exec-{fill_id}",
        "client": f"cli-{order_id}",
    }
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO orders (id, organization_id, portfolio_id, market_id, "
                "client_order_id, side, type, purpose, qty, filled_qty, execution_mode, status) "
                "VALUES (:order, :org, :pf, :market, :client, 'buy', 'market', 'entry', :qty, "
                ":qty, 'paper', 'filled')"
            ),
            params,
        )
        await connection.execute(
            text(
                "INSERT INTO fills (id, organization_id, portfolio_id, order_id, execution_key, "
                "ts, qty, price, fee, fee_asset) VALUES (:fill, :org, :pf, :order, :key, :ts, "
                ":qty, :price, 0, 'USDT')"
            ),
            params,
        )
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price, mark_price, stop_price, status, opened_at) "
                "VALUES (:position, :org, :pf, :market, 'long', :qty, :price, :price, :stop, "
                "'open', :ts)"
            ),
            params,
        )
    return position_id


async def read_proposal(engine: AsyncEngine, proposal_id: uuid.UUID) -> Any:
    async with engine.begin() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT status::text AS status, source::text AS source, admission_seq, "
                    "reservation_state::text AS reservation_state, reserved_notional, "
                    "reserved_cash, reserved_risk, reserved_slot, reserved_until, expires_at, "
                    "decided_at, rejection_reason, risk_decision, kill_switch_snapshot "
                    "FROM trade_proposals WHERE id = :id"
                ),
                {"id": proposal_id},
            )
        ).one()


async def stale_reservation(
    engine: AsyncEngine, wallet: Wallet, *, proposal_id: uuid.UUID, seconds: int
) -> None:
    """Age one standing reservation, without a wall-clock sleep."""
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE trade_proposals SET reserved_until = :until WHERE id = :id"),
            {"until": NOW - timedelta(seconds=seconds), "id": proposal_id},
        )
