"""``PortfolioState`` rebuilt from Postgres, under the wallet's own lock — T3.3.

The engine's state object is *built here*, never redefined: what
``hunter_risk.evaluate`` receives is the very
:class:`hunter_risk.exposure.PortfolioState` it declares, with its own
validators (the peak is monotonic, ``day_start_utc`` really is the Sao Paulo day
of ``as_of``) doing the last check on what this ledger assembled.

Four promises are exercised against a live database:

- **cash is reconciled from the anchor and every fill**, never carried in
  memory, so a restart reaches the same wallet;
- **a position with no valid price never marks at zero** — it keeps its last
  durable mark and the state is flagged incomplete, which is what makes the risk
  engine refuse a new entry while leaving protections alone;
- **a standing reservation is exposure**, with its own ``reserved_cash``;
- **the daily decomposition is measured, never fabricated**: without the point
  bound to the day's reference, the three reporting fields are ``None``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hunter_core.db.repositories.equity import REFERENCE_RESOLUTION
from hunter_core.db.session import create_session_factory, tenant_session
from hunter_core.domain.types import uuid7
from hunter_core.portfolio.ledger import record_equity_point
from hunter_core.portfolio.opening import open_paper_wallet
from hunter_core.portfolio.state import build_portfolio_state

if TYPE_CHECKING:
    from packages.core.tests.integration.conftest import LedgerTenant

pytestmark = pytest.mark.integration

ENGINE_ROLE = "hunter_worker"
"""The role the ledger runs as since ``0007_paper_roles`` (DATABASE.md §19.6).

Opening a wallet writes the wallet, its lock row, its anchor **and the first
point of the equity curve** in one transaction (§18.2), and the curve is now
read-only to ``hunter_app``: it is the evidence a resume reads, so a role that
can write it can fabricate the recovery it then claims. Opening and marking are
the engine's acts — there is no HTTP route for either."""

_NOW = datetime(2026, 9, 6, 15, 30, tzinfo=UTC)
_RATE = Decimal("5.0000000000")
_NO_EXIT_COST = Decimal(0)
"""These tests are about the ledger, not the cost hypothesis; the exit cost is
declared as zero so every number below is the one being asserted. The parameter
has no default precisely so that a caller has to make this choice out loud."""

_CREDITED = Decimal("20000.0000000000")
"""R$100.000 at 5,00 credits exactly 20.000 USDT and leaves no residue."""


class Wallet:
    """An opened wallet plus the ids the tests need to write execution rows."""

    def __init__(self, tenant: LedgerTenant, portfolio_id: uuid.UUID, fx_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.portfolio_id = portfolio_id
        self.fx_id = fx_id
        self.org_id = tenant.org_id
        self.market_id = tenant.market_id


@pytest_asyncio.fixture
async def factory(ledger_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield create_session_factory(ledger_engine)


@pytest_asyncio.fixture
async def wallet(
    factory: async_sessionmaker[AsyncSession],
    ledger_tenant: LedgerTenant,
    observe_fx: Callable[..., Awaitable[uuid.UUID]],
) -> Wallet:
    from hunter_core.db.repositories.fx import FxObservationRepository

    fx_id = await observe_fx(rate=_RATE, observed_at=_NOW)
    async with tenant_session(factory, ledger_tenant.org_id, db_role=ENGINE_ROLE) as session:
        observation = await FxObservationRepository(session).get(fx_id)
        assert observation is not None
        result = await open_paper_wallet(
            session,
            organization_id=ledger_tenant.org_id,
            workspace_id=ledger_tenant.workspace_id,
            fx=observation,
            as_of=_NOW,
        )
    return Wallet(ledger_tenant, result.portfolio_id, fx_id)


async def _buy(
    engine: AsyncEngine,
    wallet: Wallet,
    *,
    qty: Decimal,
    price: Decimal,
    fee: Decimal,
    mark: Decimal | None,
    stop: Decimal | None = None,
    ts: datetime = _NOW,
    fee_asset: str = "USDT",
    position_qty: Decimal | None = None,
    status: str = "open",
) -> uuid.UUID:
    """One filled entry: an order, its fill and the position it opened.

    ``qty`` is the fill's **gross** quantity, which is what left the cash;
    ``position_qty`` is what the wallet actually holds afterwards, which differs
    when the fee was charged in the base asset.
    """
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
        "fee": fee,
        "mark": mark,
        "stop": stop,
        "ts": ts,
        "key": f"exec-{fill_id}",
        "client": f"cli-{order_id}",
        "fee_asset": fee_asset,
        "position_qty": qty if position_qty is None else position_qty,
        "status": status,
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
                ":qty, :price, :fee, :fee_asset)"
            ),
            params,
        )
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price, mark_price, stop_price, status, opened_at) "
                "VALUES (:position, :org, :pf, :market, 'long', :position_qty, :price, :mark, "
                ":stop, :status, :ts)"
            ),
            params,
        )
    return position_id


async def _reserve(
    engine: AsyncEngine,
    wallet: Wallet,
    *,
    notional: Decimal,
    cash: Decimal,
    risk: Decimal,
) -> uuid.UUID:
    """One approved proposal whose reservation is still standing."""
    proposal_id = uuid7()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                "direction, status, idempotency_key, source, admission_seq, reservation_state, "
                "reserved_notional, reserved_cash, reserved_risk, reserved_slot, reserved_until) "
                "VALUES (:id, :org, :pf, :market, 'long', 'approved', :key, 'manual', 1, 'held', "
                ":notional, :cash, :risk, true, :until)"
            ),
            {
                "id": proposal_id,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "market": wallet.market_id,
                "key": f"idem-{proposal_id}",
                "notional": notional,
                "cash": cash,
                "risk": risk,
                "until": _NOW + timedelta(minutes=5),
            },
        )
    return proposal_id


class TestCashAndEquity:
    async def test_cash_is_the_anchored_credit_minus_every_fill_and_its_fees(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal("0.5"),
            price=Decimal(4000),
            fee=Decimal("2.0"),
            mark=Decimal(4000),
            stop=Decimal(3900),
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4200)},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.cash == _CREDITED - Decimal(2000) - Decimal("2.0")
        assert build.equity == build.cash + Decimal("0.5") * Decimal(4200)
        assert build.state is not None
        assert build.state.equity == build.equity
        assert build.state.cash == build.cash
        assert build.state.marks_complete is True
        assert len(build.state.open_positions) == 1
        assert build.state.open_positions[0].notional == Decimal("0.5") * Decimal(4200)
        assert build.state.open_positions[0].market.base_asset == wallet.tenant.base_symbol
        assert build.state.open_positions[0].market.quote_asset == "USDT"

    async def test_planned_risk_is_the_distance_to_the_position_own_stop(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(4000),
            fee=Decimal(0),
            mark=Decimal(4000),
            stop=Decimal(3900),
        )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4200)},
                exit_cost_rate=_NO_EXIT_COST,
            )
        assert build.state is not None
        assert build.state.open_positions[0].planned_risk_quote == Decimal(300)

    async def test_a_position_with_no_stop_commits_its_whole_notional(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """An unknown planned loss is not a zero planned loss."""
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(4000),
            fee=Decimal(0),
            mark=Decimal(4000),
            stop=None,
        )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4200)},
                exit_cost_rate=_NO_EXIT_COST,
            )
        assert build.state is not None
        assert build.state.open_positions[0].planned_risk_quote == Decimal(4200)


class TestUnavailablePricesNeverBecomeZero:
    async def test_a_position_without_a_valid_price_keeps_its_last_durable_mark(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(4000),
            fee=Decimal(0),
            mark=Decimal("4100"),
            stop=Decimal(3900),
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        assert build.state.marks_complete is False
        assert build.state.open_positions[0].notional == Decimal(4100)
        assert build.equity == build.cash + Decimal(4100)
        assert build.stale_marks == (wallet.market_id,)

    async def test_a_non_positive_price_is_not_a_price(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(4000),
            fee=Decimal(0),
            mark=Decimal("4100"),
            stop=Decimal(3900),
        )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(0)},
                exit_cost_rate=_NO_EXIT_COST,
            )
        assert build.state is not None
        assert build.state.marks_complete is False
        assert build.state.open_positions[0].notional == Decimal(4100)


class TestReservationsAreExposure:
    async def test_a_standing_reservation_holds_cash_risk_exposure_and_a_slot(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _reserve(
            ledger_engine,
            wallet,
            notional=Decimal(1000),
            cash=Decimal("1000.75"),
            risk=Decimal("50"),
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        assert build.state.slots_used == 1
        assert build.state.total_exposure == Decimal(1000)
        assert build.state.committed_planned_risk == Decimal("50")
        assert build.state.available_cash == _CREDITED - Decimal("1000.75")
        # the reservation is not cash *spent*: cash itself has not moved
        assert build.cash == _CREDITED


class TestTheDailyDecomposition:
    async def test_without_the_point_bound_to_the_reference_the_three_fields_are_none(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """The reference stands, the point it was taken on does not.

        Written as a deletion because the schema refuses to *move* a known day
        reference (``portfolio_risk_state_guard``), which is the right refusal:
        the case this reproduces is a day rollover that set the reference
        without recording the matching point, or a point lost to retention.
        """
        async with ledger_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM portfolio_equity_snapshots WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        assert build.state.daily_realized_pnl is None
        assert build.state.daily_unrealized_pnl is None
        assert build.state.daily_costs is None
        assert build.state.daily_decomposition_gap is None
        assert "daily_decomposition" in build.unavailable

    async def test_with_the_reference_point_the_gap_is_measured(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """The opening wrote the point at the reference instant, so the day is
        reconstructible: buy at 4000, mark at 4200, fee 2 — the decomposition
        matches the patrimony's own movement and the gap is zero."""
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(4000),
            fee=Decimal(2),
            mark=Decimal(4000),
            stop=Decimal(3900),
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4200)},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        assert build.state.daily_realized_pnl == Decimal(0)
        assert build.state.daily_unrealized_pnl == Decimal(200)
        assert build.state.daily_costs == Decimal(2)
        assert build.state.daily_decomposition_gap == Decimal(0)
        assert build.state.daily_pnl == Decimal(198)


class TestTheStateComesFromTheDatabase:
    async def test_a_fresh_engine_rebuilds_the_same_wallet(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """No process memory: a second engine, a second session factory."""
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal("0.25"),
            price=Decimal(4000),
            fee=Decimal("1"),
            mark=Decimal(4000),
            stop=Decimal(3900),
        )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            first = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4100)},
                exit_cost_rate=_NO_EXIT_COST,
            )

        restarted = create_session_factory(ledger_engine)
        async with tenant_session(restarted, wallet.org_id, db_role=ENGINE_ROLE) as session:
            second = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4100)},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert first.cash == second.cash
        assert first.equity == second.equity
        assert first.state is not None
        assert second.state is not None
        assert first.state.model_dump() == second.state.model_dump()

    async def test_the_build_takes_the_wallet_row_lock(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """A second builder waits for the first transaction to end."""
        started = asyncio.Event()
        release = asyncio.Event()

        async def hold() -> None:
            async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
                await build_portfolio_state(
                    session,
                    organization_id=wallet.org_id,
                    portfolio_id=wallet.portfolio_id,
                    as_of=_NOW,
                    marks={},
                    exit_cost_rate=_NO_EXIT_COST,
                )
                started.set()
                await release.wait()

        holder = asyncio.create_task(hold())
        await started.wait()

        async def contend() -> None:
            async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
                await build_portfolio_state(
                    session,
                    organization_id=wallet.org_id,
                    portfolio_id=wallet.portfolio_id,
                    as_of=_NOW,
                    marks={},
                    exit_cost_rate=_NO_EXIT_COST,
                )

        contender = asyncio.create_task(contend())
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(contender), timeout=1.0)

        release.set()
        await holder
        await contender


class TestTheEquityCurve:
    async def test_the_point_names_its_observation_and_closes_the_brl_identity(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        wallet: Wallet,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        from hunter_core.db.repositories.fx import FxObservationRepository

        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(4000),
            fee=Decimal(0),
            mark=Decimal(4000),
            stop=Decimal(3900),
        )
        later = _NOW + timedelta(hours=1)
        today_fx = await observe_fx(rate=Decimal("6.0000000000"), observed_at=later)

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            observation = await FxObservationRepository(session).get(today_fx)
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=later,
                marks={wallet.market_id: Decimal(4200)},
                exit_cost_rate=_NO_EXIT_COST,
            )
            point = await record_equity_point(session, build=build, fx=observation)

        assert point.fx_observation_id == today_fx
        assert point.brl is not None
        assert point.brl.equity_brl == build.equity * Decimal(6)
        assert point.brl.opening_brl + point.brl.total_brl == point.brl.equity_brl
        assert point.brl.operational_brl + point.brl.currency_brl == point.brl.total_brl

        async with ledger_engine.connect() as connection:
            stored = (
                await connection.execute(
                    text(
                        "SELECT equity, cash, fx_observation_id, resolution::text AS resolution "
                        "FROM portfolio_equity_snapshots WHERE portfolio_id = :pf AND ts = :ts"
                    ),
                    {"pf": wallet.portfolio_id, "ts": later},
                )
            ).one()
        assert stored.equity == build.equity
        assert stored.fx_observation_id == today_fx
        assert stored.resolution == REFERENCE_RESOLUTION.value

    async def test_without_an_observation_the_usdt_point_still_exists_and_brl_says_why(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        later = _NOW + timedelta(hours=2)
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=later,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )
            point = await record_equity_point(session, build=build, fx=None)

        assert point.equity == _CREDITED
        assert point.fx_observation_id is None
        assert point.brl is None
        assert point.brl_unavailable_reason == "no_fx_observation"


class TestUnavailabilityIsAudited:
    """Adversarial review of ``8a6a69f``, deve-corrigir 5:
    ``brl_unavailable_reason`` and ``stale_marks`` lived only in memory, and a
    row with a null ``fx_observation_id`` is indistinguishable from a healthy
    one that simply had nothing to convert. Both now write an ``AuditEvent``
    (and a structured log line) at the instant the ledger notices."""

    async def test_no_fx_observation_is_audited(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        later = _NOW + timedelta(hours=2)
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=later,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )
            point = await record_equity_point(session, build=build, fx=None)

        assert point.brl_unavailable_reason == "no_fx_observation"
        async with ledger_engine.begin() as connection:
            audited = (
                await connection.execute(
                    text(
                        "SELECT after FROM audit_logs WHERE entity_id = :pf "
                        "AND action = 'portfolio.equity_point.brl_unavailable'"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert audited.after["reason"] == "no_fx_observation"
        assert audited.after["resolution"] == REFERENCE_RESOLUTION.value
        assert "rejected_fx_observation_id" not in audited.after

    async def test_an_fx_observation_that_fails_validation_is_audited_with_its_id(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        wallet: Wallet,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        """Astra's follow-up on deve-corrigir 5: the earlier test only proved
        the ``no_fx_observation`` branch; the ``fx_rejected`` branch, and the
        id of the observation that failed, need their own proof."""
        from hunter_core.db.repositories.fx import FxObservationRepository

        point_at = _NOW + timedelta(minutes=10)
        future_fx = await observe_fx(
            rate=Decimal("6.0000000000"), observed_at=_NOW + timedelta(hours=1)
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            observation = await FxObservationRepository(session).get(future_fx)
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=point_at,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )
            point = await record_equity_point(session, build=build, fx=observation)

        assert point.brl_unavailable_reason == "fx_rejected"
        async with ledger_engine.begin() as connection:
            audited = (
                await connection.execute(
                    text(
                        "SELECT after FROM audit_logs WHERE entity_id = :pf "
                        "AND action = 'portfolio.equity_point.brl_unavailable'"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert audited.after["reason"] == "fx_rejected"
        assert audited.after["detail"] is not None
        assert audited.after["rejected_fx_observation_id"] == str(future_fx)

    async def test_a_stale_mark_is_audited(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        later = _NOW + timedelta(minutes=30)
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(4000),
            fee=Decimal(0),
            mark=Decimal(4100),
            stop=Decimal(3900),
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=later,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )
            await record_equity_point(session, build=build, fx=None)

        async with ledger_engine.begin() as connection:
            audited = (
                await connection.execute(
                    text(
                        "SELECT after FROM audit_logs WHERE entity_id = :pf "
                        "AND action = 'portfolio.equity_point.stale_marks'"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()
        assert audited.after["market_ids"] == [str(wallet.market_id)]
        assert audited.after["resolution"] == REFERENCE_RESOLUTION.value


class TestTheCostsOfTheDayIncludeFeesPaidInCoins:
    """Astra, review of the T3.3 diff, must-fix A."""

    async def test_a_fee_charged_in_the_base_asset_is_a_cost_of_the_day(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """Buy 1 at 100 with a fee of 0,01 units: cash is down 100, the wallet
        holds 0,99, the patrimony is down 1 — and the decomposition says so
        instead of reporting zero costs and leaving the whole drop in the gap."""
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(100),
            fee=Decimal("0.01"),
            mark=Decimal(100),
            stop=Decimal(90),
            fee_asset=wallet.tenant.base_symbol,
            position_qty=Decimal("0.99"),
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(100)},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        # cash fell by the gross 100; the wallet holds 0,99 worth 99; the missing
        # unit is the fee, and it has to appear as a cost of the day.
        assert build.cash == _CREDITED - Decimal(100)
        assert build.equity == _CREDITED - Decimal(1)
        assert build.state.daily_costs == Decimal(1)
        assert build.state.daily_realized_pnl == Decimal(0)
        assert build.state.daily_unrealized_pnl == Decimal(0)
        assert build.state.daily_decomposition_gap == Decimal(0)
        assert build.state.daily_pnl == Decimal(-1)

    async def test_a_base_asset_fee_at_schema_legal_magnitude_is_not_rounded_by_28_digits(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """Adversarial review of ``8a6a69f``, suggestion 12: ``costs += qty *
        price`` ran under the ambient default context (28 significant digits),
        not :data:`hunter_core.portfolio.attribution.LEDGER_CONTEXT`.
        ``NUMERIC(28,10)`` bounds each *column* to 28 digits, not their
        *product* — two schema-legal values below round to a different tenth
        decimal without the wider context."""
        from decimal import localcontext

        from hunter_core.portfolio.attribution import LEDGER_CONTEXT

        huge_fee = Decimal("123456789012345.6789012345")
        huge_price = Decimal("987654321098.7654321098")
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(100),
            fee=huge_fee,
            mark=huge_price,
            stop=Decimal(90),
            fee_asset=wallet.tenant.base_symbol,
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: huge_price},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        with localcontext(LEDGER_CONTEXT):
            expected = huge_fee * huge_price
        assert build.state.daily_costs == expected

    async def test_without_a_price_for_the_coin_the_costs_are_unavailable_not_zero(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal(1),
            price=Decimal(100),
            fee=Decimal("0.01"),
            mark=None,
            stop=Decimal(90),
            fee_asset=wallet.tenant.base_symbol,
            position_qty=Decimal("0.99"),
        )
        async with ledger_engine.begin() as connection:
            await connection.execute(
                text("UPDATE positions SET qty = 0 WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        assert build.state.daily_costs is None
        assert build.state.daily_realized_pnl is None
        assert build.state.daily_unrealized_pnl is None
        assert "daily_decomposition" in build.unavailable


class TestTheCurveRefusesAnFxItMayNotUse:
    """Astra, review of the T3.3 diff, must-fix D."""

    async def test_an_observation_from_the_future_of_the_point_is_refused(
        self,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        """Recording the point of 15:40 with a rate that only arrived at 16:30
        would fold future information into a stored BRL figure."""
        from hunter_core.db.repositories.fx import FxObservationRepository

        point_at = _NOW + timedelta(minutes=10)
        future_fx = await observe_fx(
            rate=Decimal("6.0000000000"), observed_at=_NOW + timedelta(hours=1)
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            observation = await FxObservationRepository(session).get(future_fx)
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=point_at,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )
            point = await record_equity_point(session, build=build, fx=observation)

        assert point.equity == _CREDITED
        assert point.brl is None
        assert point.brl_unavailable_reason == "fx_rejected"
        assert point.brl_unavailable_detail is not None
        assert "had not reached us" in point.brl_unavailable_detail
        assert point.fx_observation_id is None

    async def test_a_stale_observation_leaves_the_usdt_point_and_no_brl(
        self,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        from hunter_core.db.repositories.fx import FxObservationRepository

        later = _NOW + timedelta(hours=3)
        stale_fx = await observe_fx(rate=Decimal("6.0000000000"), observed_at=_NOW)

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            observation = await FxObservationRepository(session).get(stale_fx)
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=later,
                marks={},
                exit_cost_rate=_NO_EXIT_COST,
            )
            point = await record_equity_point(session, build=build, fx=observation)

        assert point.equity == _CREDITED
        assert point.brl is None
        assert point.brl_unavailable_reason == "fx_rejected"
        assert point.fx_observation_id is None

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            stored = await session.scalar(
                text(
                    "SELECT fx_observation_id FROM portfolio_equity_snapshots "
                    "WHERE portfolio_id = :pf AND ts = :ts"
                ),
                {"pf": wallet.portfolio_id, "ts": later},
            )
        assert stored is None


class TestDustIsMarkedButIsNotAPosition:
    """T3.5b item 3 — the residual of a spot exit stays in the patrimony and
    leaves the slot.

    ``positions.status = 'closing'`` is what the execution worker writes when
    the leftover of an exit is below the exchange minimum: 0,000482 units that
    no price makes sellable. It is owned, so the exposure and the equity count
    it; it is not a position, so the engine never sees it — before this it held
    one of five slots and refused that coin a second order for ever.
    """

    async def test_a_residual_is_valued_in_the_equity_and_takes_no_slot(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal("0.5"),
            price=Decimal(4000),
            fee=Decimal("2.0"),
            mark=Decimal(4000),
            stop=Decimal(3900),
            position_qty=Decimal("0.000482"),
            status="closing",
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4200)},
                exit_cost_rate=_NO_EXIT_COST,
            )

        dust_notional = Decimal("0.000482") * Decimal(4200)
        assert build.cash == _CREDITED - Decimal(2000) - Decimal("2.0")
        # Visible and valued — the coins are owned and the patrimony says so.
        assert build.exposure_notional == dust_notional
        assert build.equity == build.cash + dust_notional
        assert build.state is not None
        assert build.state.equity == build.equity
        # And invisible to the engine: no slot, no coin held, no planned risk.
        assert build.state.open_positions == ()
        assert build.state.slots_used == 0
        assert build.state.assets_held == frozenset()
        assert build.state.committed_planned_risk == Decimal(0)
        # The mark was found, so nothing is degraded by the residual's presence.
        assert build.state.marks_complete is True

    async def test_a_residual_next_to_a_real_position_leaves_exactly_one_slot(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal("0.5"),
            price=Decimal(4000),
            fee=Decimal("2.0"),
            mark=Decimal(4000),
            position_qty=Decimal("0.000482"),
            status="closing",
        )
        await _buy(
            ledger_engine,
            wallet,
            qty=Decimal("0.25"),
            price=Decimal(4000),
            fee=Decimal("1.0"),
            mark=Decimal(4000),
            stop=Decimal(3900),
        )

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=_NOW,
                marks={wallet.market_id: Decimal(4200)},
                exit_cost_rate=_NO_EXIT_COST,
            )

        assert build.state is not None
        assert build.state.slots_used == 1
        assert [p.qty for p in build.state.open_positions] == [Decimal("0.25")]
        # The dust is still in the exposure, next to the position that counts.
        assert build.exposure_notional == (Decimal("0.000482") + Decimal("0.25")) * Decimal(4200)
        assert build.state.assets_held == frozenset({wallet.tenant.base_symbol})
