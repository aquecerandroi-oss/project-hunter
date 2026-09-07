"""§11 — two real sessions, two connections, one wallet.

Never two tasks over one ``AsyncSession`` (§12 trap 8): each side below opens its
own transaction on its own connection, and the ordering is forced by the
database's own locks or by an explicit barrier — never by a sleep (§12 trap 1).

What the three races have to show:

- **one request is one place in the queue.** The same idempotency key from two
  sessions produces one proposal, one reservation and one FIFO place; the loser
  revalidates the winner's request instead of deciding again;
- **the second decision is taken against the first's committed reservation**, not
  against a copy of the wallet read before it;
- **the lock order system -> organization -> portfolio is real**: while an
  admission holds the tenant row, an organization-wide block cannot slip in
  between the read and the write; once it commits, the next entry is refused.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import KillSwitchState, ReservationState
from hunter_core.domain.types import uuid7
from hunter_core.risk import effective_state
from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.decision import RiskDecision

from .conftest import (
    CASH_MULTIPLIER,
    CREDITED,
    ENGINE_ROLE,
    MEDIAN_MINUTE,
    Wallet,
    admit_entry,
    admit_in,
    at,
    liquidity_for,
    read_proposal,
    read_risk_state,
    request_for,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

FULL_NOTIONAL = Decimal("1851.800")
CEILING = Decimal("46.0510")
"""1 % of the median minute of 4.605,10 — the ceiling the two sessions contend for."""

ORG_BLOCK = text("UPDATE organizations SET kill_switch_state = 'TRADING_DISABLED' WHERE id = :org")
ORG_TRANSITION = text(
    "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, from_state, "
    "to_state, reason, actor_type, actor_id, evidence) VALUES (:id, :org, 'organization', :org, "
    "'ACTIVE', 'TRADING_DISABLED', 'org-wide halt by the owner', 'user', :actor, "
    '\'{"scope": "organization"}\'::jsonb)'
)


def base_marks(wallet: Wallet) -> dict[uuid.UUID, Decimal]:
    return {market.id: Decimal(100) for market in wallet.markets.values()}


async def _block_the_organization(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet, *, lock_timeout: str | None = None
) -> None:
    """The other session: an OWNER halting the whole tenant, audited, as the API."""
    async with tenant_session(
        factory, wallet.org_id, wallet.user_id, db_role="hunter_app"
    ) as session:
        if lock_timeout is not None:
            await session.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout}'"))
        await session.execute(
            ORG_TRANSITION, {"id": uuid7(), "org": wallet.org_id, "actor": wallet.user_id}
        )
        await session.execute(ORG_BLOCK, {"org": wallet.org_id})


# --------------------------------------------------------------------------
# One request is one place in the queue
# --------------------------------------------------------------------------


async def test_the_same_request_from_two_sessions_reserves_once_and_the_second_revalidates(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Two concurrent admissions of one agent request: one row, one hold, one seq.

    ``source='agent'`` with a decision taken in the same call — the deduplication
    of a *pending* manual request is a known defect (review of T3.1b/T3.6/T3.12,
    must-fix 1) and this test deliberately does not exercise it.

    Refuted by two proposals, two reservations, two places in the FIFO queue, or
    a loser that answers with a decision of its own rather than the winner's.
    """
    marks = base_marks(wallet)
    agent_id = wallet.agent_id
    first, second = await asyncio.gather(
        admit_entry(
            factory,
            wallet,
            wallet.market("SOLUSDT"),
            now=at(),
            marks=marks,
            client_key="s11-same-request",
            source="agent",
            agent_id=agent_id,
        ),
        admit_entry(
            factory,
            wallet,
            wallet.market("SOLUSDT"),
            now=at(),
            marks=marks,
            client_key="s11-same-request",
            source="agent",
            agent_id=agent_id,
        ),
    )

    assert first.proposal_id == second.proposal_id
    assert first.admission_seq == second.admission_seq == 1
    assert {first.replayed, second.replayed} == {False, True}
    assert first.decision.sizing is not None
    assert second.decision.sizing is not None
    assert first.decision.sizing.notional == second.decision.sizing.notional == FULL_NOTIONAL

    async with engine.connect() as connection:
        proposals = await connection.scalar(
            text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
        held = await connection.scalar(
            text(
                "SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf "
                "AND reservation_state = 'held'"
            ),
            {"pf": wallet.portfolio_id},
        )
        reserved = await connection.scalar(
            text(
                "SELECT coalesce(sum(notional), 0) FROM participation_consumptions "
                "WHERE portfolio_id = :pf AND kind = 'reserved'"
            ),
            {"pf": wallet.portfolio_id},
        )
    assert (proposals, held) == (1, 1)
    assert reserved == FULL_NOTIONAL, "the market's budget was charged exactly once"
    assert (await read_risk_state(engine, wallet)).last_admission_seq == 1


# --------------------------------------------------------------------------
# The second decision sees the first reservation
# --------------------------------------------------------------------------


async def test_the_second_admission_decides_against_the_first_committed_reservation(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The wallet lock serialises, and the loser re-reads instead of reusing a copy.

    Two markets so both may be approved (D3 forbids two commitments on one coin);
    the one that took the second FIFO place must carry ceilings computed **after**
    the other's reservation: 8.000 − 1.851,800 of room in the total exposure, and
    an aggregate budget of 200 − 49,9986.

    The two sizes differ by the recorded lot size and nothing else: SOLUSDT steps
    by 0,001 (1.851,800) and ETHUSDT by 0,0001 (1.851,850), both floored from the
    same ceiling of 1.851,851851…

    Refuted by a second decision whose ceilings still describe an empty wallet —
    the classic read-before-lock, which is how two entries each "fit" and
    together do not.
    """
    by_symbol = {"SOLUSDT": Decimal("1851.800"), "ETHUSDT": Decimal("1851.850")}
    marks = base_marks(wallet)
    results = await asyncio.gather(
        admit_entry(
            factory,
            wallet,
            wallet.market("SOLUSDT"),
            now=at(),
            marks=marks,
            client_key="s11-sol",
        ),
        admit_entry(
            factory,
            wallet,
            wallet.market("ETHUSDT"),
            now=at(),
            marks=marks,
            client_key="s11-eth",
        ),
    )
    ordered = sorted(results, key=lambda item: item.admission_seq or 0)
    assert [item.admission_seq for item in ordered] == [1, 2]
    assert all(item.approved for item in ordered)

    row = await read_proposal(engine, ordered[1].proposal_id)
    stored = RiskDecision.model_validate(row.risk_decision)
    assert stored.sizing is not None
    caps = {cap.name: cap for cap in stored.sizing.caps}
    first_notional = by_symbol[
        RiskDecision.model_validate(
            (await read_proposal(engine, ordered[0].proposal_id)).risk_decision
        ).market.symbol
    ]
    assert caps["total_exposure"].notional == Decimal(8000) - first_notional
    assert caps["cash"].limit == CREDITED - first_notional * CASH_MULTIPLIER
    # The aggregate budget of the second decision, computed in the engine's own
    # decimal context: 1 % of the equity minus the risk the first one committed.
    # An "empty wallet" reading would be 200 / 0,027 = 7.407,407…
    with localcontext(CONTEXT):
        room = CREDITED * Decimal("0.01") - first_notional * Decimal("0.027")
        expected_aggregate = room / Decimal("0.027")
    aggregate = caps["aggregate_risk"].notional
    assert aggregate is not None
    assert aggregate == expected_aggregate
    assert aggregate < Decimal(200) / Decimal("0.027")
    assert stored.sizing.notional == by_symbol[stored.market.symbol]

    async with engine.connect() as connection:
        committed = await connection.scalar(
            text(
                "SELECT coalesce(sum(reserved_notional), 0) FROM trade_proposals "
                "WHERE portfolio_id = :pf AND reservation_state = 'held'"
            ),
            {"pf": wallet.portfolio_id},
        )
    assert committed == sum(by_symbol.values())
    assert committed <= CREDITED * Decimal("0.40"), "the total exposure ceiling held"


# --------------------------------------------------------------------------
# The lock order, system -> organization -> portfolio
# --------------------------------------------------------------------------


async def test_an_organization_block_cannot_commit_while_an_admission_holds_the_tenant_row(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The ``FOR SHARE`` rung, proved by making the other session fail on it.

    Session A takes the effective state under the contract's lock order and keeps
    its transaction open. Session B — an OWNER blocking the organization —
    cannot take the exclusive row lock and dies on ``lock_timeout``: there is no
    window in which A decides against ACTIVE while B's block is already visible.
    Then B commits for real, and the next entry is refused.

    ``lock_timeout`` rather than a sleep: the wait is bounded by the database and
    the assertion is on the error it raises, not on how long anything took.

    Refuted by B succeeding while A holds the lock (the two never contended — the
    exact race §5 names), or by A's entry being approved *after* B's block was
    committed.
    """
    marks = base_marks(wallet)
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as a_session:
        scopes = await effective_state(
            a_session, wallet.portfolio_id, system=KillSwitchState.ACTIVE, lock=True
        )
        assert scopes.effective is KillSwitchState.ACTIVE

        with pytest.raises(DBAPIError, match="lock timeout"):
            await _block_the_organization(factory, wallet, lock_timeout="250ms")

        approved = await admit_in(
            a_session,
            wallet,
            wallet.market("SOLUSDT"),
            request_for(wallet, wallet.market("SOLUSDT"), client_key="s11-under-lock"),
            now=at(),
            marks=marks,
        )
    assert approved.approved is True, "A decided under the state it locked"

    await _block_the_organization(factory, wallet)
    refused = await admit_entry(
        factory,
        wallet,
        wallet.market("ETHUSDT"),
        now=at(seconds=1),
        marks=marks,
        client_key="s11-after-block",
    )
    assert refused.approved is False
    assert "kill_switch" in refused.decision.rejection_reasons
    assert refused.decision.effective_kill_switch is KillSwitchState.TRADING_DISABLED
    assert refused.reservation_state is ReservationState.NONE

    row = await read_proposal(engine, refused.proposal_id)
    assert row.kill_switch_snapshot["organization"] == KillSwitchState.TRADING_DISABLED.value
    assert row.kill_switch_snapshot["portfolio"] == KillSwitchState.ACTIVE.value, (
        "the wallet's own latch never copied the organization's block"
    )


async def test_a_block_committed_first_is_seen_by_the_admission_that_starts_after_it(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The other ordering of the same race, with an explicit barrier.

    B commits the organization's block and sets the event; A only then begins.
    The effective state A decides under is read **inside** its own transaction,
    so the block is visible even though A never read the organization before.

    Refuted by an approval — a service that had cached the organization's switch,
    or read it once outside the admitting transaction.
    """
    blocked = asyncio.Event()

    async def block() -> None:
        await _block_the_organization(factory, wallet)
        blocked.set()

    async def enter() -> Any:
        await blocked.wait()
        return await admit_entry(
            factory,
            wallet,
            wallet.market("SOLUSDT"),
            now=at(),
            marks=base_marks(wallet),
            client_key="s11-after-barrier",
        )

    _, result = await asyncio.gather(block(), enter())
    assert result.approved is False
    assert result.decision.cancel_pending is True
    assert result.reservation_state is ReservationState.NONE

    async with engine.connect() as connection:
        held = await connection.scalar(
            text(
                "SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf "
                "AND reservation_state = 'held'"
            ),
            {"pf": wallet.portfolio_id},
        )
    assert held == 0


# --------------------------------------------------------------------------
# The participation budget under contention (§11 step 5)
# --------------------------------------------------------------------------


async def test_two_concurrent_entries_never_reserve_more_than_the_minute_allows(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """30 + 30 is 60 and the ceiling is 46,0510 — so 60 must never be reserved.

    In this wallet the rule that stops it is not the participation subtraction
    but ``duplicate_position`` (D3: never two commitments on one coin), which is
    why the second session is refused outright instead of being sized down to
    16,0510. Both readings satisfy the invariant; the difference is recorded in
    ``notes-T3.9a.md`` §3.

    Refuted by a sum of reservations above the ceiling, or by two holds on the
    same market at once.
    """
    sol = wallet.market("SOLUSDT")
    marks = base_marks(wallet)
    liquidity = liquidity_for(sol, as_of=at(), minute_volume=MEDIAN_MINUTE)
    first, second = await asyncio.gather(
        admit_entry(
            factory,
            wallet,
            sol,
            now=at(),
            marks=marks,
            client_key="s11-budget-a",
            liquidity=liquidity,
            requested_notional=Decimal(30),
        ),
        admit_entry(
            factory,
            wallet,
            sol,
            now=at(),
            marks=marks,
            client_key="s11-budget-b",
            liquidity=liquidity,
            requested_notional=Decimal(30),
        ),
    )
    approved = [item for item in (first, second) if item.approved]
    refused = [item for item in (first, second) if not item.approved]
    assert len(approved) == 1
    assert approved[0].reserved_notional == Decimal("30.000")
    assert "duplicate_position" in refused[0].decision.rejection_reasons
    assert refused[0].reservation_state is ReservationState.NONE

    async with engine.connect() as connection:
        reserved = await connection.scalar(
            text(
                "SELECT coalesce(sum(notional), 0) FROM participation_consumptions "
                "WHERE portfolio_id = :pf AND market_id = :market AND kind = 'reserved'"
            ),
            {"pf": wallet.portfolio_id, "market": sol.id},
        )
    assert reserved <= CEILING
    assert reserved == Decimal("30.000")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "notes-T3.9a.md §3: §11 step 5 assumes two reservations can share one "
        "market's minute inside one wallet. D3 (duplicate_position) forbids the "
        "second commitment on the same coin, so the 16,0510 remainder is never "
        "sized. The number is not adjusted; the invariant is proved by the test "
        "above."
    ),
)
async def test_s11_step5_the_second_session_takes_the_remaining_16_051(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """§11 step 5 read literally: 30 reserved, then 16,051 available to the other.

    Refuted (it would pass) only if a wallet were allowed two standing
    commitments on the same coin — which D3 exists to prevent.
    """
    sol = wallet.market("SOLUSDT")
    marks = base_marks(wallet)
    liquidity = liquidity_for(sol, as_of=at(), minute_volume=MEDIAN_MINUTE)
    first = await admit_entry(
        factory,
        wallet,
        sol,
        now=at(),
        marks=marks,
        client_key="s11-step5-a",
        liquidity=liquidity,
        requested_notional=Decimal(30),
    )
    assert first.reserved_notional == Decimal("30.000")

    second = await admit_entry(
        factory,
        wallet,
        sol,
        now=at(seconds=1),
        marks=marks,
        client_key="s11-step5-b",
        liquidity=liquidity_for(sol, as_of=at(seconds=1), minute_volume=MEDIAN_MINUTE),
        requested_notional=Decimal(30),
    )
    assert second.approved is True
    assert second.decision.sizing is not None
    assert second.decision.sizing.notional == Decimal("16.000")
