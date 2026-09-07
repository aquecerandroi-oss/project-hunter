"""Opening the paper wallet against a real Postgres — T3.3 + the T3.11 half.

What is proved here is the part the schema explicitly says it cannot prove
(DATABASE.md §18.2): that the wallet, the credit, the anchor, the lock row, the
first point of the equity curve and the audit entry are born **in the same
commit**, and that no invalid FX observation ever produces any of them.

Everything runs as ``hunter_app`` through ``tenant_session``, so RLS and the
table grants are in force exactly as they are in production; the fixtures build
the tenant as the container owner, which is the only privileged step.
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hunter_core.db.models.fx import FxObservation
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import create_session_factory, tenant_session
from hunter_core.portfolio.attribution import OPENING_ROUNDING_POLICY
from hunter_core.portfolio.opening import (
    DEFAULT_CAPITAL_BRL,
    PAPER_FX_POLICY,
    FxObservationRejected,
    WalletAlreadyOpen,
    open_paper_wallet,
)

if TYPE_CHECKING:
    from packages.core.tests.integration.conftest import LedgerTenant

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 6, 15, 30, tzinfo=UTC)
"""12:30 in Sao Paulo — the same UTC day, so a wrong zone would still be wrong
in the same direction and the assertion below would not catch it by accident."""


@pytest_asyncio.fixture
async def factory(ledger_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield create_session_factory(ledger_engine)


async def _fx(session: AsyncSession, observation_id: uuid.UUID) -> FxObservation:
    observation = await FxObservationRepository(session).get(observation_id)
    assert observation is not None
    return observation


async def _count(engine: AsyncEngine, table: str, org_id: uuid.UUID) -> int:
    async with engine.connect() as connection:
        value = await connection.scalar(
            text(f"SELECT count(*) FROM {table} WHERE organization_id = :org"),  # noqa: S608
            {"org": org_id},
        )
    return int(value or 0)


class TestTheOpeningIsOneCommit:
    async def test_it_writes_wallet_credit_anchor_lock_curve_and_audit_together(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        observation_id = await observe_fx(observed_at=_NOW)

        async with tenant_session(factory, ledger_tenant.org_id) as session:
            result = await open_paper_wallet(
                session,
                organization_id=ledger_tenant.org_id,
                workspace_id=ledger_tenant.workspace_id,
                fx=await _fx(session, observation_id),
                as_of=_NOW,
            )

        # R$100.000 at 5,4321 credits the floor at ten decimals, and the wallet
        # says it opened with exactly what the anchor credited.
        assert result.conversion.credited_amount == Decimal("18409.0867252075")
        assert result.conversion.rounding_policy == OPENING_ROUNDING_POLICY
        assert result.conversion.origin_amount == DEFAULT_CAPITAL_BRL

        async with ledger_engine.connect() as connection:
            wallet = (
                await connection.execute(
                    text(
                        "SELECT type, is_arena, base_currency, initial_capital, status "
                        "FROM portfolios WHERE id = :id"
                    ),
                    {"id": result.portfolio_id},
                )
            ).one()
            anchor = (
                await connection.execute(
                    text(
                        "SELECT origin_amount, credited_amount, rate, conversion_residual, "
                        "rounding_policy, fx_observation_id FROM portfolio_currency_anchor "
                        "WHERE portfolio_id = :id"
                    ),
                    {"id": result.portfolio_id},
                )
            ).one()
            risk_state = (
                await connection.execute(
                    text(
                        "SELECT peak_equity, equity_day_start, trading_day, "
                        "trading_day_start_utc, day_reference_observed_at, last_admission_seq "
                        "FROM portfolio_risk_state WHERE portfolio_id = :id"
                    ),
                    {"id": result.portfolio_id},
                )
            ).one()
            curve = (
                await connection.execute(
                    text(
                        "SELECT cash, equity, fx_observation_id, unrealized_pnl, ts "
                        "FROM portfolio_equity_snapshots WHERE portfolio_id = :id"
                    ),
                    {"id": result.portfolio_id},
                )
            ).all()
            audited = await connection.scalar(
                text(
                    "SELECT count(*) FROM audit_logs WHERE entity_id = :id "
                    "AND action = 'portfolio.opened'"
                ),
                {"id": result.portfolio_id},
            )

        assert wallet.type == "paper"
        assert wallet.is_arena is False
        assert wallet.base_currency == "USDT"
        assert wallet.initial_capital == result.conversion.credited_amount
        assert anchor.credited_amount == result.conversion.credited_amount
        assert anchor.origin_amount == DEFAULT_CAPITAL_BRL
        assert anchor.fx_observation_id == observation_id
        assert risk_state.peak_equity == result.conversion.credited_amount
        assert risk_state.equity_day_start == result.conversion.credited_amount
        assert risk_state.last_admission_seq == 0
        assert len(curve) == 1
        assert curve[0].fx_observation_id == observation_id
        assert curve[0].cash == result.conversion.credited_amount
        assert curve[0].equity == result.conversion.credited_amount
        assert curve[0].unrealized_pnl == 0
        assert audited == 1

    async def test_the_day_reference_is_the_sao_paulo_day_of_the_opening(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        """01:30 UTC on the 7th is still the 6th in Sao Paulo (UTC−3)."""
        just_after_utc_midnight = datetime(2026, 9, 7, 1, 30, tzinfo=UTC)
        observation_id = await observe_fx(observed_at=just_after_utc_midnight)

        async with tenant_session(factory, ledger_tenant.org_id) as session:
            result = await open_paper_wallet(
                session,
                organization_id=ledger_tenant.org_id,
                workspace_id=ledger_tenant.workspace_id,
                fx=await _fx(session, observation_id),
                as_of=just_after_utc_midnight,
            )

        async with ledger_engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT trading_day, trading_day_start_utc, trading_day_timezone "
                        "FROM portfolio_risk_state WHERE portfolio_id = :id"
                    ),
                    {"id": result.portfolio_id},
                )
            ).one()

        assert str(row.trading_day) == "2026-09-06"
        assert row.trading_day_start_utc.replace(tzinfo=UTC) == datetime(
            2026, 9, 6, 3, 0, tzinfo=UTC
        )
        assert row.trading_day_timezone == "America/Sao_Paulo"

    async def test_a_failure_after_the_wallet_row_leaves_nothing_behind(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        """The anchor's own trigger is the injected failure: an FX observation
        the wallet names but whose rate was tampered with in flight."""
        observation_id = await observe_fx(observed_at=_NOW)

        tampered = FxObservation(
            id=observation_id,
            pair=PAPER_FX_POLICY.pair,
            source=PAPER_FX_POLICY.source,
            rate=Decimal("9.9999999999"),
            observed_at=_NOW,
            available_at=_NOW,
        )

        with pytest.raises(Exception):  # noqa: B017 - the trigger's DBAPIError
            async with tenant_session(factory, ledger_tenant.org_id) as session:
                await open_paper_wallet(
                    session,
                    organization_id=ledger_tenant.org_id,
                    workspace_id=ledger_tenant.workspace_id,
                    fx=tampered,
                    as_of=_NOW,
                )

        assert await _count(ledger_engine, "portfolios", ledger_tenant.org_id) == 0
        assert await _count(ledger_engine, "portfolio_risk_state", ledger_tenant.org_id) == 0
        assert await _count(ledger_engine, "portfolio_currency_anchor", ledger_tenant.org_id) == 0


class TestPermanence:
    async def test_a_second_opening_in_the_same_workspace_is_refused(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        """D7: a new wallet is a reset by another name, and there is no reset."""
        observation_id = await observe_fx(observed_at=_NOW)

        async with tenant_session(factory, ledger_tenant.org_id) as session:
            await open_paper_wallet(
                session,
                organization_id=ledger_tenant.org_id,
                workspace_id=ledger_tenant.workspace_id,
                fx=await _fx(session, observation_id),
                as_of=_NOW,
            )

        with pytest.raises(WalletAlreadyOpen):
            async with tenant_session(factory, ledger_tenant.org_id) as session:
                await open_paper_wallet(
                    session,
                    organization_id=ledger_tenant.org_id,
                    workspace_id=ledger_tenant.workspace_id,
                    fx=await _fx(session, observation_id),
                    as_of=_NOW + timedelta(seconds=30),
                )

        assert await _count(ledger_engine, "portfolios", ledger_tenant.org_id) == 1
        assert await _count(ledger_engine, "portfolio_currency_anchor", ledger_tenant.org_id) == 1

    async def test_an_archived_wallet_does_not_free_a_second_one(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        observation_id = await observe_fx(observed_at=_NOW)
        async with tenant_session(factory, ledger_tenant.org_id) as session:
            result = await open_paper_wallet(
                session,
                organization_id=ledger_tenant.org_id,
                workspace_id=ledger_tenant.workspace_id,
                fx=await _fx(session, observation_id),
                as_of=_NOW,
            )
        async with ledger_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE portfolios SET status = 'archived', deleted_at = now() WHERE id = :id"
                ),
                {"id": result.portfolio_id},
            )

        with pytest.raises(WalletAlreadyOpen):
            async with tenant_session(factory, ledger_tenant.org_id) as session:
                await open_paper_wallet(
                    session,
                    organization_id=ledger_tenant.org_id,
                    workspace_id=ledger_tenant.workspace_id,
                    fx=await _fx(session, observation_id),
                    as_of=_NOW + timedelta(minutes=1),
                )

    async def test_a_second_workspace_in_the_same_organization_gets_no_second_wallet(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        """T3.1b's security review of ``0006``: the principal wallet is unique
        per **organization**, not per ``(organization, workspace)`` — a fresh
        workspace inside the same organization must not open a second one."""
        other_workspace_id = uuid.uuid4()
        async with ledger_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, objective) "
                    "VALUES (:id, :org, 'second-workspace', 'paper_trading')"
                ),
                {"id": other_workspace_id, "org": ledger_tenant.org_id},
            )
        observation_id = await observe_fx(observed_at=_NOW)

        async with tenant_session(factory, ledger_tenant.org_id) as session:
            await open_paper_wallet(
                session,
                organization_id=ledger_tenant.org_id,
                workspace_id=ledger_tenant.workspace_id,
                fx=await _fx(session, observation_id),
                as_of=_NOW,
            )

        with pytest.raises(WalletAlreadyOpen, match="organization"):
            async with tenant_session(factory, ledger_tenant.org_id) as session:
                await open_paper_wallet(
                    session,
                    organization_id=ledger_tenant.org_id,
                    workspace_id=other_workspace_id,
                    fx=await _fx(session, observation_id),
                    as_of=_NOW + timedelta(seconds=30),
                )

        assert await _count(ledger_engine, "portfolios", ledger_tenant.org_id) == 1

    async def test_two_concurrent_openings_in_the_same_scope_do_not_leak_a_raw_db_error(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Deve-corrigir 7: two real, concurrent transactions race the unique
        index — Postgres itself serialises the two ``INSERT``s, so exactly one
        wins and the other must see :class:`WalletAlreadyOpen`, never the
        driver's own ``IntegrityError``.

        A bare ``asyncio.gather`` does not guarantee this branch is what runs:
        if the winner's whole transaction finishes before the loser's precheck
        even executes, the loser is refused by ``principal_paper_id`` and the
        ``except IntegrityError`` branch this test means to exercise never
        runs at all (Astra's tightening of this same review). The barrier below
        holds both transactions until **both** real ``SELECT``s have returned
        "no wallet yet", so both then race the same ``INSERT``.
        """
        from hunter_core.db.repositories.portfolio import PortfolioRepository

        observation_id = await observe_fx(observed_at=_NOW)
        both_prechecked = asyncio.Barrier(2)
        original_precheck = PortfolioRepository.principal_paper_id

        async def _barriered_precheck(self: PortfolioRepository) -> uuid.UUID | None:
            found = await original_precheck(self)
            await both_prechecked.wait()
            return found

        monkeypatch.setattr(PortfolioRepository, "principal_paper_id", _barriered_precheck)

        async def _open() -> object:
            async with tenant_session(factory, ledger_tenant.org_id) as session:
                fx = await _fx(session, observation_id)
                return await open_paper_wallet(
                    session,
                    organization_id=ledger_tenant.org_id,
                    workspace_id=ledger_tenant.workspace_id,
                    fx=fx,
                    as_of=_NOW,
                )

        results = await asyncio.gather(_open(), _open(), return_exceptions=True)
        failures = [r for r in results if isinstance(r, BaseException)]
        successes = [r for r in results if not isinstance(r, BaseException)]

        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], WalletAlreadyOpen)
        assert isinstance(failures[0].__cause__, IntegrityError)

        assert await _count(ledger_engine, "portfolios", ledger_tenant.org_id) == 1
        assert await _count(ledger_engine, "portfolio_currency_anchor", ledger_tenant.org_id) == 1
        assert await _count(ledger_engine, "portfolio_risk_state", ledger_tenant.org_id) == 1
        assert await _count(ledger_engine, "portfolio_equity_snapshots", ledger_tenant.org_id) == 1
        async with ledger_engine.connect() as connection:
            audited = await connection.scalar(
                text(
                    "SELECT count(*) FROM audit_logs WHERE organization_id = :org "
                    "AND action = 'portfolio.opened'"
                ),
                {"org": ledger_tenant.org_id},
            )
        assert audited == 1


class TestAnInvalidObservationDoesNotOpen:
    @pytest.mark.parametrize(
        ("kwargs", "reason"),
        [
            ({"source": "some.blog.rss"}, "source"),
            ({"pair": "USDBRL"}, "pair"),
            (
                {
                    "observed_at": _NOW - timedelta(minutes=15),
                    "available_at": _NOW - timedelta(minutes=1),
                },
                "observed_at is",
            ),
            ({"observed_at": _NOW - timedelta(minutes=8)}, "available_at is"),
            ({"observed_at": _NOW + timedelta(minutes=1)}, "ahead of"),
        ],
    )
    async def test_it_is_refused_and_writes_nothing(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
        kwargs: dict[str, object],
        reason: str,
    ) -> None:
        observation_id = await observe_fx(**{"observed_at": _NOW, **kwargs})

        with pytest.raises(FxObservationRejected, match=reason):
            async with tenant_session(factory, ledger_tenant.org_id) as session:
                await open_paper_wallet(
                    session,
                    organization_id=ledger_tenant.org_id,
                    workspace_id=ledger_tenant.workspace_id,
                    fx=await _fx(session, observation_id),
                    as_of=_NOW,
                )

        assert await _count(ledger_engine, "portfolios", ledger_tenant.org_id) == 0
        assert await _count(ledger_engine, "portfolio_currency_anchor", ledger_tenant.org_id) == 0


class TestCapitalIsFixed:
    """Adversarial review of ``8a6a69f``, suggestion 14: the directive's §1
    fixes the paper wallet's opening capital at R$100.000; ``capital_brl`` is
    not a free parameter of the service."""

    async def test_a_non_default_capital_is_refused_and_writes_nothing(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_engine: AsyncEngine,
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        observation_id = await observe_fx(observed_at=_NOW)

        with pytest.raises(ValueError, match="capital_brl must be"):
            async with tenant_session(factory, ledger_tenant.org_id) as session:
                await open_paper_wallet(
                    session,
                    organization_id=ledger_tenant.org_id,
                    workspace_id=ledger_tenant.workspace_id,
                    fx=await _fx(session, observation_id),
                    as_of=_NOW,
                    capital_brl=Decimal("50000"),
                )

        assert await _count(ledger_engine, "portfolios", ledger_tenant.org_id) == 0

    async def test_the_testing_override_lets_a_test_open_at_a_different_capital(
        self,
        factory: async_sessionmaker[AsyncSession],
        ledger_tenant: LedgerTenant,
        observe_fx: Callable[..., Awaitable[uuid.UUID]],
    ) -> None:
        """The override exists so a test of the conversion arithmetic itself
        can use a round, easy-to-check number; it is never reached from
        production code (``test_no_funding_route.py`` proves that by scanning
        the source)."""
        observation_id = await observe_fx(observed_at=_NOW)

        async with tenant_session(factory, ledger_tenant.org_id) as session:
            result = await open_paper_wallet(
                session,
                organization_id=ledger_tenant.org_id,
                workspace_id=ledger_tenant.workspace_id,
                fx=await _fx(session, observation_id),
                as_of=_NOW,
                capital_brl=Decimal("50000"),
                _testing_capital_override=True,
            )

        assert result.conversion.origin_amount == Decimal("50000")
