"""The admission service against a real database — T3.12.

What is proved here, with Postgres and the real migrations:

- **the number the engine computed is the number the row carries.** V1 of
  ``.claude/state/spec-T3.9-verificacoes.md``: ``binding_constraint =
  risk_per_trade``, ``qty = 18,518``, ``notional = 1.851,800`` — read back from
  ``trade_proposals.risk_decision``, not recomputed;
- **a decision is atomic with its consequences**: reservation, FIFO place, audit
  row and outbox event all exist, in the same commit;
- **a refusal is a row**, with every check recorded, and holds nothing;
- **a replay is the same answer**: same proposal, same sequence, no second
  reservation, no second event;
- **``research_only`` never becomes a proposal at all.**
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hunter_core.admission.dedupe import IdempotencyConflict
from hunter_core.admission.inputs import MarketMismatch
from hunter_core.admission.reservation import RESERVATION_TTL
from hunter_core.admission.sources import OriginRefused
from hunter_core.db.session import create_session_factory, tenant_session
from hunter_core.domain.enums import (
    KillSwitchState,
    ProposalStatus,
    ReservationState,
    TradeDirection,
)
from hunter_core.strategies.envelope import PURPOSE_RESEARCH_ONLY
from packages.core.tests.integration.admission_fixtures import (
    CASH_MULTIPLIER,
    CREDITED,
    ENGINE_ROLE,
    NOW,
    Wallet,
    admit_default,
    apply_pending_grants,
    beta_for,
    buy_filled,
    liquidity_for,
    open_wallet,
    read_proposal,
    request_for,
)

if TYPE_CHECKING:
    from packages.core.tests.integration.conftest import LedgerTenant

pytestmark = pytest.mark.integration


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


class TestTheApprovedEntry:
    async def test_the_persisted_decision_is_the_engine_own_numbers(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))

        assert result.approved is True
        assert result.status is ProposalStatus.APPROVED
        assert result.decision.sizing is not None
        assert result.decision.sizing.binding_constraint == "risk_per_trade"
        assert result.decision.sizing.qty == Decimal("18.518")
        assert result.decision.sizing.notional == Decimal("1851.800")

        row = await read_proposal(ledger_engine, result.proposal_id)
        assert row.status == "approved"
        assert row.source == "manual"
        assert row.rejection_reason is None
        assert row.risk_decision["sizing"]["binding_constraint"] == "risk_per_trade"
        assert Decimal(row.risk_decision["sizing"]["notional"]) == Decimal("1851.800")
        assert row.kill_switch_snapshot["effective"] == KillSwitchState.ACTIVE.value

    async def test_the_reservation_holds_notional_cash_risk_and_the_slot(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))

        row = await read_proposal(ledger_engine, result.proposal_id)
        assert row.reservation_state == ReservationState.HELD.value
        assert row.reserved_slot is True
        assert row.reserved_notional == Decimal("1851.800")
        assert row.reserved_cash == Decimal("1851.800") * CASH_MULTIPLIER
        assert row.reserved_risk == result.decision.sizing.planned_risk_quote
        # ``decided_at`` is the caller's instant plus the wait for the wallet
        # lock, which is real time and never rounded away — so the tenure is
        # asserted against the instant the decision actually carries.
        assert NOW <= result.decided_at < NOW + timedelta(seconds=5)
        assert row.decided_at == result.decided_at
        assert row.reserved_until == result.decided_at + RESERVATION_TTL
        assert row.expires_at == result.decided_at + RESERVATION_TTL

    async def test_the_fifo_place_is_the_wallet_own_counter(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            first = await admit_default(session, wallet, request_for(wallet, client_key="a"))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            second = await admit_default(session, wallet, request_for(wallet, client_key="b"))

        assert (first.admission_seq, second.admission_seq) == (1, 2)
        async with ledger_engine.begin() as connection:
            counter = await connection.scalar(
                text(
                    "SELECT last_admission_seq FROM portfolio_risk_state WHERE portfolio_id = :pf"
                ),
                {"pf": wallet.portfolio_id},
            )
        assert counter == 2

    async def test_the_audit_row_and_the_event_are_in_the_same_commit(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))

        async with ledger_engine.begin() as connection:
            audit = (
                await connection.execute(
                    text(
                        "SELECT action, actor_type, entity_type, after, metadata AS meta "
                        "FROM audit_logs "
                        "WHERE entity_id = :id"
                    ),
                    {"id": result.proposal_id},
                )
            ).one()
            events = (
                await connection.execute(
                    text(
                        "SELECT stream, payload, dispatched_at FROM outbox_events "
                        "WHERE payload -> 'payload' ->> 'proposal_id' = :id"
                    ),
                    {"id": str(result.proposal_id)},
                )
            ).all()

        assert audit.action == "proposal.admitted"
        assert audit.entity_type == "trade_proposal"
        assert audit.after["admission_seq"] == result.admission_seq
        assert audit.meta["checks"]["kill_switch"] == "passed"
        assert len(events) == 1
        assert events[0].stream == "proposals.decided"
        assert events[0].dispatched_at is None
        assert events[0].payload["payload"]["binding_constraint"] == "risk_per_trade"

    async def test_the_second_entry_sees_the_first_reservation(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """Pendências são exposição: the same coin is already held (D3)."""
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            await admit_default(session, wallet, request_for(wallet, client_key="a"))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            second = await admit_default(session, wallet, request_for(wallet, client_key="b"))

        assert second.approved is False
        assert "duplicate_position" in second.decision.rejection_reasons
        assert second.reservation_state is ReservationState.NONE


class TestARefusalIsARowWithItsChecks:
    async def test_a_blocked_kill_switch_rejects_and_reserves_nothing(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(
                session,
                wallet,
                request_for(wallet),
                system=KillSwitchState.TRADING_DISABLED,
            )

        assert result.approved is False
        assert result.status is ProposalStatus.REJECTED
        assert result.reservation_state is ReservationState.NONE
        assert result.admission_seq == 1

        row = await read_proposal(ledger_engine, result.proposal_id)
        assert row.status == "rejected"
        assert row.reservation_state == "none"
        assert row.reserved_notional is None
        assert row.reserved_until is None
        assert row.expires_at is None
        assert "kill_switch" in row.rejection_reason
        names = [check["name"] for check in row.risk_decision["checks"]]
        assert len(names) == len(set(names))
        assert {"kill_switch", "liquidity_24h", "book_depth", "cash"} <= set(names)
        assert row.kill_switch_snapshot["system"] == KillSwitchState.TRADING_DISABLED.value

    async def test_an_unvalidated_beta_keeps_the_asset_in_shadow(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(
                session, wallet, request_for(wallet), beta=beta_for(validated=False)
            )

        assert result.approved is False
        assert result.decision.shadow_only is True
        assert "beta_validity" in result.decision.rejection_reasons

    async def test_a_rejection_still_publishes_its_decision(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(
                session, wallet, request_for(wallet), system=KillSwitchState.EMERGENCY
            )
        async with ledger_engine.begin() as connection:
            event = (
                await connection.execute(
                    text(
                        "SELECT payload FROM outbox_events "
                        "WHERE payload -> 'payload' ->> 'proposal_id' = :id"
                    ),
                    {"id": str(result.proposal_id)},
                )
            ).one()
            action = await connection.scalar(
                text("SELECT action FROM audit_logs WHERE entity_id = :id"),
                {"id": result.proposal_id},
            )
        assert event.payload["payload"]["approved"] is False
        assert "kill_switch" in event.payload["payload"]["rejection_reasons"]
        assert action == "proposal.rejected"


class TestAReplayIsNeverASecondDecision:
    async def test_the_same_key_returns_the_same_proposal(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            first = await admit_default(session, wallet, request_for(wallet))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            replay = await admit_default(session, wallet, request_for(wallet))

        assert replay.replayed is True
        assert replay.proposal_id == first.proposal_id
        assert replay.admission_seq == first.admission_seq
        assert replay.decision.to_jsonable() == first.decision.to_jsonable()
        assert replay.reserved_notional == first.reserved_notional

        async with ledger_engine.begin() as connection:
            proposals = await connection.scalar(
                text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )
            reserved = await connection.scalar(
                text(
                    "SELECT count(*) FROM participation_consumptions WHERE proposal_id = :id "
                    "AND kind = 'reserved'"
                ),
                {"id": first.proposal_id},
            )
            events = await connection.scalar(
                text(
                    "SELECT count(*) FROM outbox_events "
                    "WHERE payload -> 'payload' ->> 'proposal_id' = :id"
                ),
                {"id": str(first.proposal_id)},
            )
            counter = await connection.scalar(
                text(
                    "SELECT last_admission_seq FROM portfolio_risk_state WHERE portfolio_id = :pf"
                ),
                {"pf": wallet.portfolio_id},
            )
        assert (proposals, reserved, events, counter) == (1, 1, 1, 1)

    async def test_a_reused_key_for_another_order_is_a_conflict(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            await admit_default(session, wallet, request_for(wallet))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(IdempotencyConflict, match="direction"):
                await admit_default(
                    session, wallet, request_for(wallet, direction=TradeDirection.SHORT)
                )

    async def test_a_reused_key_with_another_geometry_is_a_conflict(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """The stored approval carries its price, its stop and the asked ceiling.

        Astra's scenario: the first request is approved with a ceiling of 1.000,
        the client reuses the key with a ceiling of 100 — and would otherwise be
        answered with an approval larger than the one it asked for.
        """
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            await admit_default(
                session, wallet, request_for(wallet, requested_notional=Decimal(1000))
            )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(IdempotencyConflict, match="requested_notional"):
                await admit_default(
                    session, wallet, request_for(wallet, requested_notional=Decimal(100))
                )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(IdempotencyConflict, match="stop"):
                await admit_default(
                    session,
                    wallet,
                    request_for(wallet, stop=Decimal("98.5"), requested_notional=Decimal(1000)),
                )


class TestWhatNeverBecomesAProposal:
    async def test_research_only_leaves_no_row(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(OriginRefused, match=PURPOSE_RESEARCH_ONLY):
                await admit_default(
                    session, wallet, request_for(wallet, purpose=PURPOSE_RESEARCH_ONLY)
                )

        async with ledger_engine.begin() as connection:
            rows = await connection.scalar(
                text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )
        assert rows == 0

    async def test_an_unknown_origin_is_refused_by_name(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(OriginRefused, match="shadow_bridge"):
                await admit_default(session, wallet, request_for(wallet), source="shadow_bridge")

    async def test_a_market_id_that_names_another_market_is_refused(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """The row and the identity the engine compares have to be one market."""
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            with pytest.raises(MarketMismatch):
                await admit_default(
                    session,
                    wallet,
                    request_for(
                        wallet,
                        market=liquidity_for(wallet.tenant).market.model_copy(
                            update={"symbol": "OTHERUSDT"}
                        ),
                    ),
                )


class TestTheCheckIsAlsoTheDetector:
    async def test_a_rejection_by_daily_loss_records_the_loss_without_latching(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """What happens today, and the gap it documents — notes-T3.12.md §2/D.

        RISK_ENGINE.md §3.1 says failing check 16 or 17 also *moves* the kill
        switch. It does not move here: ``portfolios`` is writable by
        ``hunter_app`` alone while admission has to run as ``hunter_worker`` to
        advance ``fifo_v1``, so the escalation cannot be written in this
        transaction under the delivered privileges — and forcing it would turn
        the rejection into *permission denied for table portfolios*.

        What **is** guaranteed is asserted: the entry is refused by the loss it
        measured, and the decision records the number. When the ownership of
        ``portfolios.kill_switch_state`` is decided, this is the test that flips.
        """
        await buy_filled(
            ledger_engine,
            wallet,
            qty=Decimal(100),
            price=Decimal(100),
            stop=Decimal(90),
        )
        crashed = Decimal(55)
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(
                session,
                wallet,
                request_for(wallet),
                liquidity=liquidity_for(wallet.tenant, last_price=crashed),
                prices={wallet.market_id: crashed},
            )

        assert result.approved is False
        assert "daily_loss" in result.decision.rejection_reasons
        measured = next(check for check in result.decision.checks if check.name == "daily_loss")
        assert measured.value is not None
        assert measured.value > Decimal("0.02")

        async with ledger_engine.begin() as connection:
            latch = await connection.scalar(
                text("SELECT kill_switch_state::text FROM portfolios WHERE id = :pf"),
                {"pf": wallet.portfolio_id},
            )
            transitions = await connection.scalar(
                text("SELECT count(*) FROM kill_switch_transitions WHERE scope_id = :pf"),
                {"pf": wallet.portfolio_id},
            )
        assert latch == KillSwitchState.ACTIVE.value
        assert transitions == 0


class TestAWalletThatCannotBeMeasured:
    async def test_a_missing_daily_reference_rejects_with_the_reason(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """RISK_ENGINE.md §5: entries blocked, protections preserved — and *recorded*.

        The reference is made *unusable* by advancing the trading day past
        ``as_of`` rather than by nulling it: the wallet's own guard refuses to
        unset a day that was already counted, and a test that fought the schema
        to reach this state would be proving something the system cannot be in.
        A reference belonging to another day is exactly what a restart across
        midnight produces, which is the case the contract is about.
        """
        async with ledger_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE portfolio_risk_state SET trading_day = :day, "
                    "trading_day_start_utc = :start WHERE portfolio_id = :pf"
                ),
                {
                    "day": date(2026, 9, 7),
                    "start": datetime(2026, 9, 7, 3, tzinfo=UTC),
                    "pf": wallet.portfolio_id,
                },
            )
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))

        assert result.approved is False
        assert result.unavailable == ("daily_reference",)
        assert result.reservation_state is ReservationState.NONE
        assert result.decision.sizing is None
        states = {check.name: check.state.value for check in result.decision.checks}
        assert states["risk_per_trade" if "risk_per_trade" in states else "sizing"] == "unavailable"
        assert set(states.values()) == {"unavailable"}

        row = await read_proposal(ledger_engine, result.proposal_id)
        assert row.status == "rejected"
        assert "daily_reference" in row.risk_decision["checks"][0]["message"]


class TestTheWalletIsNotDrainedByAdmission:
    async def test_the_cash_of_the_wallet_is_untouched_by_a_reservation(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """A reservation commits cash; it never spends it — only a fill does."""
        from hunter_core.portfolio.state import build_portfolio_state

        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            result = await admit_default(session, wallet, request_for(wallet))
        async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
            build = await build_portfolio_state(
                session,
                organization_id=wallet.org_id,
                portfolio_id=wallet.portfolio_id,
                as_of=NOW,
                marks={wallet.market_id: Decimal(100)},
                exit_cost_rate=Decimal(0),
                betas={wallet.market_id: Decimal(1)},
            )
        assert build.cash == CREDITED
        assert build.state is not None
        assert len(build.state.pending_entries) == 1
        assert build.state.pending_entries[0].reserved_notional == result.reserved_notional
        assert build.state.available_cash == CREDITED - (result.reserved_cash or Decimal(0))
        assert build.state.slots_used == 1
