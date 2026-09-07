"""Two real sessions racing for the same wallet — T3.12, §11 of the T3.9 spec.

Two distinct ``AsyncSession``s on two connections, coordinated by
``asyncio.Event`` instead of a sleep: the point of the exercise is the *order*
of two commits, and a wall clock proves nothing about it (§12 of that spec, "o
relógio de parede").

Three races, each with a number that must not appear:

- **the wallet lock serialises admission.** Two entries in the same market
  cannot both reserve; the second one revalidates against the first's standing
  reservation and is refused by name;
- **the participation budget is not split.** With the ceiling of 46,0510 and a
  first reservation of 30, the second may take at most 16,0510 — never 30;
- **one request is one place in the queue.** The same idempotency key from two
  sessions produces one proposal, one ``admission_seq``, and the loser recovers
  the winner's identity.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hunter_core.db.session import create_session_factory, tenant_session
from hunter_core.domain.enums import KillSwitchState, ReservationState
from packages.core.tests.integration.admission_fixtures import (
    ENGINE_ROLE,
    Wallet,
    admit_default,
    apply_pending_grants,
    liquidity_for,
    open_wallet,
    request_for,
)

if TYPE_CHECKING:
    from packages.core.tests.integration.conftest import LedgerTenant

pytestmark = pytest.mark.integration

MINUTE_VOLUME = Decimal("4605.10")
CEILING = Decimal("46.0510")


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


async def _admit_in_own_session(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    *,
    client_key: str,
    ready: asyncio.Event | None = None,
    after: asyncio.Event | None = None,
    **overrides: Any,
) -> Any:
    """One admission in a transaction of its own, optionally sequenced by events."""
    if after is not None:
        await after.wait()
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        result = await admit_default(
            session, wallet, request_for(wallet, client_key=client_key), **overrides
        )
        if ready is not None:
            ready.set()
        return result


class TestTheWalletLockSerialisesAdmission:
    async def test_two_entries_in_the_same_market_never_both_reserve(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        first, second = await asyncio.gather(
            _admit_in_own_session(factory, wallet, client_key="a"),
            _admit_in_own_session(factory, wallet, client_key="b"),
        )
        approved = [item for item in (first, second) if item.approved]
        refused = [item for item in (first, second) if not item.approved]
        assert len(approved) == 1
        assert len(refused) == 1
        assert "duplicate_position" in refused[0].decision.rejection_reasons
        assert refused[0].reservation_state is ReservationState.NONE
        assert {first.admission_seq, second.admission_seq} == {1, 2}

        async with ledger_engine.begin() as connection:
            held = await connection.scalar(
                text(
                    "SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf "
                    "AND reservation_state = 'held'"
                ),
                {"pf": wallet.portfolio_id},
            )
        assert held == 1

    async def test_the_second_session_sees_an_organization_block_committed_first(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """The effective state is read **inside** the admitting transaction.

        A commits ``TRADING_DISABLED`` on the *organization* — a scope the
        admission never read before taking the wallet lock; the admission then
        starts and is refused, because the state it decides under is read on the
        way in, in its own transaction, not carried from before.

        Honest limit of this test: the two transactions do **not** overlap. What
        it refutes is a service that read the organization's switch once, at
        start-up or in an earlier transaction, and decided against that copy.
        Making the two windows overlap needs a hook inside ``admit`` that this
        service deliberately does not have; the ordering guarantee under real
        contention is the ``FOR SHARE`` on the tenant row, which forces the
        organization's own ``UPDATE`` to wait for a reader that already holds it.
        """
        blocked = asyncio.Event()

        async def block_the_organization() -> None:
            async with ledger_engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO kill_switch_transitions (id, organization_id, scope, "
                        "scope_id, from_state, to_state, reason, actor_type, actor_id, evidence) "
                        "VALUES (:id, :org, 'organization', :org, 'ACTIVE', 'TRADING_DISABLED', "
                        "'org-wide halt', 'system', NULL, '{\"probe\": true}')"
                    ),
                    {"id": uuid.uuid4(), "org": wallet.org_id},
                )
                await connection.execute(
                    text(
                        "UPDATE organizations SET kill_switch_state = 'TRADING_DISABLED' "
                        "WHERE id = :id"
                    ),
                    {"id": wallet.org_id},
                )
            blocked.set()

        await block_the_organization()
        result = await _admit_in_own_session(factory, wallet, client_key="a", after=blocked)

        assert result.approved is False
        assert "kill_switch" in result.decision.rejection_reasons
        assert result.decision.effective_kill_switch is KillSwitchState.TRADING_DISABLED
        assert result.reservation_state is ReservationState.NONE


class TestTheParticipationBudgetIsNotSplit:
    async def test_two_concurrent_entries_never_exceed_the_minute(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """V1 step 3's ceiling, contended: 30 + 30 is 60 and 60 > 46,0510."""
        liquidity = liquidity_for(wallet.tenant, minute_volume=MINUTE_VOLUME)
        first, second = await asyncio.gather(
            _admit_in_own_session(factory, wallet, client_key="a", liquidity=liquidity),
            _admit_in_own_session(factory, wallet, client_key="b", liquidity=liquidity),
        )
        async with ledger_engine.begin() as connection:
            reserved = await connection.scalar(
                text(
                    "SELECT coalesce(sum(notional), 0) FROM participation_consumptions "
                    "WHERE portfolio_id = :pf AND market_id = :market AND kind = 'reserved'"
                ),
                {"pf": wallet.portfolio_id, "market": wallet.market_id},
            )
        assert reserved <= CEILING
        assert sum(1 for item in (first, second) if item.approved) == 1


class TestOneRequestIsOnePlaceInTheQueue:
    async def test_the_same_key_from_two_sessions_produces_one_proposal(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        first, second = await asyncio.gather(
            _admit_in_own_session(factory, wallet, client_key="same"),
            _admit_in_own_session(factory, wallet, client_key="same"),
        )
        assert first.proposal_id == second.proposal_id
        assert first.admission_seq == second.admission_seq == 1
        assert {first.replayed, second.replayed} == {False, True}

        async with ledger_engine.begin() as connection:
            proposals = await connection.scalar(
                text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
                {"pf": wallet.portfolio_id},
            )
            counter = await connection.scalar(
                text(
                    "SELECT last_admission_seq FROM portfolio_risk_state WHERE portfolio_id = :pf"
                ),
                {"pf": wallet.portfolio_id},
            )
            events = await connection.scalar(
                text(
                    "SELECT count(*) FROM outbox_events "
                    "WHERE payload -> 'payload' ->> 'proposal_id' = :id"
                ),
                {"id": str(first.proposal_id)},
            )
        assert (proposals, counter, events) == (1, 1, 1)


class TestTheApiRoleCannotAdmitToday:
    async def test_the_wallet_counter_is_refused_to_hunter_app(
        self, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        """A blocking coupling for T3.8, kept as a test instead of a paragraph.

        ``fifo_v1`` lives on ``portfolio_risk_state``, and T3.1b gives the API
        role ``UPDATE (updated_at)`` on that row — enough to take the lock,
        never enough to write a value (``ddl/paper.py``,
        ``PAPER_LOCK_ONLY_TABLES``). So the manual order route cannot run this
        service inside a ``hunter_app`` transaction as it stands: either the
        privilege is widened to ``last_admission_seq`` or the route hands the
        admission to a worker-role unit of work. Recorded in
        ``.claude/state/notes-T3.12.md`` §2; when it is decided, this test is
        the one that changes.
        """
        with pytest.raises(Exception, match="permission denied|may not be updated") as caught:
            async with tenant_session(factory, wallet.org_id) as session:
                await admit_default(session, wallet, request_for(wallet))
        assert "portfolio_risk_state" in str(caught.value)

    async def test_the_engine_role_cannot_take_the_organization_lock_either(
        self, factory: async_sessionmaker[AsyncSession], ledger_engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """The other half of the coupling, proved on the schema **as delivered**.

        ``apply_pending_grants`` adds a privilege the migrations do not have yet;
        this test removes it for the length of one admission and shows what the
        delivered schema actually does — *permission denied for table
        organizations*, because ``SELECT ... FOR SHARE`` is charged
        ``ACL_UPDATE`` and ``hunter_worker`` holds ``SELECT`` and ``DELETE``
        only. Without it the green suite above would be claiming an integration
        the database does not provide (notes-T3.12.md §2, coupling A).
        """
        async with ledger_engine.begin() as connection:
            await connection.execute(text("REVOKE UPDATE ON organizations FROM hunter_worker"))
        try:
            with pytest.raises(Exception, match="permission denied") as caught:
                await _admit_in_own_session(factory, wallet, client_key="ungranted")
            assert "organizations" in str(caught.value)
        finally:
            await apply_pending_grants(ledger_engine)
