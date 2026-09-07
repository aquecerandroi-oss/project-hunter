"""Reservations, the participation budget and expiry, against Postgres — T3.12.

Three invariants ``docs/DATABASE.md`` §18.3/§18.5 hands to this service, each
proved on real rows rather than argued:

- **the 60 s budget of a market is shared.** A standing reservation is already
  spent; the next entry in the same market finds the ceiling reduced, and the
  numbers are V1's (``max_participation_pct = 1 %`` of 4.605,10 = 46,000);
- **the cycle only closes.** ``held`` -> consumed/released/expired, once, and
  the reverse ``UPDATE`` is refused by the service. The schema does *not* refuse
  it, and that is a fact this suite states out loud instead of implying;
- **expiry runs under the wallet lock, is audited, and gives back only what was
  not executed.**
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hunter_core.admission.participation import ParticipationRepository
from hunter_core.admission.reservation import (
    RESERVATION_TTL,
    ReservationCycleClosed,
    close_reservation,
    expire_reservations,
)
from hunter_core.db.session import create_session_factory, tenant_session
from hunter_core.domain.enums import ParticipationEntryKind, ReservationState
from packages.core.tests.integration.admission_fixtures import (
    ENGINE_ROLE,
    NOW,
    Wallet,
    admit_default,
    apply_pending_grants,
    liquidity_for,
    open_wallet,
    read_proposal,
    request_for,
    stale_reservation,
)

if TYPE_CHECKING:
    from packages.core.tests.integration.conftest import LedgerTenant

pytestmark = pytest.mark.integration

MINUTE_VOLUME = Decimal("4605.10")
"""KB-0067/0071's measured median minute. 1 % of it is the ceiling of V1 step 3."""

PARTICIPATION_CEILING = Decimal("46.0510")


@pytest_asyncio.fixture
async def factory(ledger_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    await apply_pending_grants(ledger_engine)
    yield create_session_factory(ledger_engine)


@pytest_asyncio.fixture
async def wallet(
    factory: async_sessionmaker[AsyncSession],
    ledger_tenant: LedgerTenant,
    observe_fx: Callable[..., Awaitable[uuid.UUID]],
) -> Wallet:
    return await open_wallet(factory, ledger_tenant, observe_fx)


class TestTheParticipationBudgetIsShared:
    async def test_the_ceiling_binds_and_publishes_its_counterfactual(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(
                session,
                wallet,
                request_for(wallet),
                liquidity=liquidity_for(wallet.tenant, minute_volume=MINUTE_VOLUME),
            )
        assert result.approved is True
        sizing = result.decision.sizing
        assert sizing is not None
        assert sizing.binding_constraint == "market_participation"
        assert sizing.notional <= PARTICIPATION_CEILING
        assert sizing.size_without_participation.notional == Decimal("1851.800")

    async def test_a_standing_reservation_is_already_spent_in_the_next_entry(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """RISK_ENGINE.md §4: two 0,8 % orders never both pass."""
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            first = await admit_default(
                session,
                wallet,
                request_for(wallet, client_key="a"),
                liquidity=liquidity_for(wallet.tenant, minute_volume=MINUTE_VOLUME),
            )
        assert first.reserved_notional is not None

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            used = await ParticipationRepository(session, wallet.org_id).used(
                portfolio_id=wallet.portfolio_id,
                market_id=wallet.market_id,
                cut=NOW - timedelta(seconds=60),
            )
        assert used == first.reserved_notional

        async with ledger_engine.begin() as connection:
            entries = (
                await connection.execute(
                    text(
                        "SELECT kind::text AS kind, notional, occurred_at FROM "
                        "participation_consumptions WHERE proposal_id = :id"
                    ),
                    {"id": first.proposal_id},
                )
            ).all()
        assert [(row.kind, row.notional) for row in entries] == [
            (ParticipationEntryKind.RESERVED.value, first.reserved_notional)
        ]
        assert entries[0].occurred_at == first.decided_at

    async def test_the_budget_is_per_market(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """Another market's minute is not this market's minute."""
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            await admit_default(
                session,
                wallet,
                request_for(wallet),
                liquidity=liquidity_for(wallet.tenant, minute_volume=MINUTE_VOLUME),
            )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            used_elsewhere = await ParticipationRepository(session, wallet.org_id).used(
                portfolio_id=wallet.portfolio_id,
                market_id=uuid.uuid4(),
                cut=NOW - timedelta(seconds=60),
            )
        assert used_elsewhere == Decimal(0)


class TestExpiryCompetesForTheSameLock:
    async def test_a_reservation_past_its_tenure_is_expired_and_audited(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))
        await stale_reservation(ledger_engine, wallet, proposal_id=result.proposal_id, seconds=1)

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            expired = await expire_reservations(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                now=NOW,
            )

        assert expired == (result.proposal_id,)
        row = await read_proposal(ledger_engine, result.proposal_id)
        assert row.reservation_state == ReservationState.EXPIRED.value
        assert row.reserved_slot is False
        assert row.reserved_notional == result.reserved_notional
        assert row.status == "approved"

        async with ledger_engine.begin() as connection:
            audit = (
                await connection.execute(
                    text(
                        "SELECT action, metadata AS meta FROM audit_logs WHERE entity_id = :id "
                        "AND action = 'proposal.reservation_expired'"
                    ),
                    {"id": result.proposal_id},
                )
            ).one()
            released = (
                await connection.execute(
                    text(
                        "SELECT notional FROM participation_consumptions WHERE proposal_id = :id "
                        "AND kind = 'released'"
                    ),
                    {"id": result.proposal_id},
                )
            ).one()
        assert Decimal(audit.meta["released_notional"]) == result.reserved_notional
        assert released.notional == result.reserved_notional

    async def test_a_reservation_inside_its_tenure_is_left_alone(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            expired = await expire_reservations(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                now=NOW + RESERVATION_TTL - timedelta(seconds=1),
            )
        assert expired == ()
        row = await read_proposal(ledger_engine, result.proposal_id)
        assert row.reservation_state == ReservationState.HELD.value

    async def test_admission_frees_the_slot_of_a_dead_reservation(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """The expiry sweep runs inside admission, under the same lock."""
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            first = await admit_default(session, wallet, request_for(wallet, client_key="a"))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            blocked = await admit_default(session, wallet, request_for(wallet, client_key="b"))
        assert "duplicate_position" in blocked.decision.rejection_reasons

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            after = await admit_default(
                session,
                wallet,
                request_for(wallet, client_key="c"),
                now=NOW + RESERVATION_TTL + timedelta(seconds=1),
            )
        assert after.approved is True
        assert after.reserved_notional == first.reserved_notional


class TestOneProposalOneCycle:
    async def test_a_fill_consumes_the_reservation_without_returning_the_budget(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            await close_reservation(
                session,
                organization_id=wallet.org_id,
                proposal_id=result.proposal_id,
                target=ReservationState.CONSUMED,
                now=NOW,
                reason="fill",
            )
        row = await read_proposal(ledger_engine, result.proposal_id)
        assert row.reservation_state == ReservationState.CONSUMED.value
        assert row.reserved_slot is False
        async with ledger_engine.begin() as connection:
            released = await connection.scalar(
                text(
                    "SELECT count(*) FROM participation_consumptions WHERE proposal_id = :id "
                    "AND kind = 'released'"
                ),
                {"id": result.proposal_id},
            )
        assert released == 0

    async def test_a_closed_cycle_is_refused_by_the_service(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            await close_reservation(
                session,
                organization_id=wallet.org_id,
                proposal_id=result.proposal_id,
                target=ReservationState.RELEASED,
                now=NOW,
                reason="cancelled",
            )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(ReservationCycleClosed, match="released"):
                await close_reservation(
                    session,
                    organization_id=wallet.org_id,
                    proposal_id=result.proposal_id,
                    target=ReservationState.CONSUMED,
                    now=NOW,
                )

    async def test_the_schema_alone_would_let_a_writer_reopen_the_cycle(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """Declared, not implied (DATABASE.md §18.3).

        A raw ``UPDATE`` back to ``held`` is accepted by the database today: the
        single axis is a schema fact, its **direction** is this service's
        invariant. If a later migration adds the trigger the security review
        suggests (finding 11), this test is the one that has to change — which
        is exactly the signal wanted, instead of a silent overlap.
        """
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            await close_reservation(
                session,
                organization_id=wallet.org_id,
                proposal_id=result.proposal_id,
                target=ReservationState.CONSUMED,
                now=NOW,
            )
        async with ledger_engine.begin() as connection:
            await connection.execute(
                text("UPDATE trade_proposals SET reservation_state = 'held' WHERE id = :id"),
                {"id": result.proposal_id},
            )
            state = await connection.scalar(
                text("SELECT reservation_state::text FROM trade_proposals WHERE id = :id"),
                {"id": result.proposal_id},
            )
        assert state == ReservationState.HELD.value

    async def test_a_proposal_that_never_reserved_has_no_cycle_to_close(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        from hunter_core.domain.enums import KillSwitchState

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            rejected = await admit_default(
                session,
                wallet,
                request_for(wallet),
                system=KillSwitchState.TRADING_DISABLED,
            )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(ReservationCycleClosed, match="none"):
                await close_reservation(
                    session,
                    organization_id=wallet.org_id,
                    proposal_id=rejected.proposal_id,
                    target=ReservationState.RELEASED,
                    now=NOW,
                )
