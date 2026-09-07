"""V3 — BLOQUEADO stops new entries and never touches a protection.

Rule 3 of the directive, in code rather than prose: with the wallet
``TRADING_DISABLED`` after a real 2,5 % loss of the day (and **nothing
realised** — the whole loss is mark to market), a new entry is refused by the
``kill_switch`` check with no reservation, the standing pending entry is
cancelled and gives back exactly what it held, and ``evaluate_exit`` on the open
position is still approved for the whole quantity.

Nothing here liquidates anything: the directive forbids selling the wallet to
protect it, so the position that was open before the block is still open after
it, still carrying its stop.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.admission.reservation import close_reservation
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import (
    ExitReason,
    KillSwitchState,
    ProposalStatus,
    ReservationState,
)
from hunter_core.risk import effective_state
from hunter_risk.decision import CheckState, RiskDecision
from hunter_risk.evaluate import evaluate_exit
from hunter_risk.inputs import ExitProposal
from hunter_risk.kill_switch import KillSwitchInputs, blocks_entries, entry_size_multiplier
from hunter_risk.limits import PAPER_V1

from .conftest import (
    CASH_MULTIPLIER,
    ENGINE_ROLE,
    Wallet,
    admit_entry,
    at,
    buy_filled,
    check_of,
    mark_to_market,
    read_latch,
    read_proposal,
    read_state,
    read_transitions,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

POSITION_QTY = Decimal(10)
ENTRY_PRICE = Decimal(100)
STOP_PRICE = Decimal("99.5")
BLOCK_MARK = Decimal(50)
"""10 units bought at 100 (cash 19.000) marked at 50: equity 19.500, a loss of
2,5 % of the day's opening — past the 2 % rung — with realised PnL at zero."""

PENDING_NOTIONAL = Decimal("1851.800")


class Scene:
    """The V3 pre-conditions, all produced by the durable path."""

    def __init__(self, marks: dict[uuid.UUID, Decimal], position_id: uuid.UUID, pending: uuid.UUID):
        self.marks = marks
        self.position_id = position_id
        self.pending_proposal_id = pending


async def _blocked_wallet(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> Scene:
    """A protected position, a held reservation, and a wallet that then blocks."""
    btc = wallet.market("BTCUSDT")
    sol = wallet.market("SOLUSDT")
    position_id = await buy_filled(
        factory, wallet, btc, qty=POSITION_QTY, price=ENTRY_PRICE, stop=STOP_PRICE, ts=at()
    )
    flat = {market.id: ENTRY_PRICE for market in wallet.markets.values()}
    pending = await admit_entry(
        factory, wallet, sol, now=at(seconds=1), marks=flat, client_key="v3-pending"
    )
    assert pending.approved is True
    assert pending.reservation_state is ReservationState.HELD

    marks = {**flat, btc.id: BLOCK_MARK}
    build, blocked = await mark_to_market(
        engine, factory, wallet, marks=marks, at_instant=at(minutes=1)
    )
    assert build.equity == Decimal(19500)
    assert build.realized_pnl_cum == Decimal(0), "the loss is entirely unrealised"
    assert blocked.latched is KillSwitchState.TRADING_DISABLED
    assert blocked.daily_loss_pct == Decimal("0.025")
    return Scene(marks, position_id, pending.proposal_id)


async def test_a_two_and_a_half_percent_day_blocks_even_with_nothing_realised(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The daily loss is measured on patrimony, not on closed trades.

    Refuted by a wallet that stays ACTIVE because no trade was closed — the
    reading that would let an open position lose any amount without ever
    tripping the switch — or by a block written without its audited transition.
    """
    await _blocked_wallet(engine, factory, wallet)

    assert await read_latch(engine, wallet) is KillSwitchState.TRADING_DISABLED
    transitions = await read_transitions(engine, wallet)
    assert [(t.from_state, t.to_state) for t in transitions] == [
        (KillSwitchState.ACTIVE.value, KillSwitchState.TRADING_DISABLED.value)
    ]
    assert Decimal(transitions[0].evidence["daily_loss_pct"]) == Decimal("0.025")
    assert Decimal(transitions[0].evidence["blocked_daily_loss_pct"]) == Decimal("0.02")
    assert blocks_entries(KillSwitchState.TRADING_DISABLED) is True
    assert entry_size_multiplier(KillSwitchState.TRADING_DISABLED, PAPER_V1) == Decimal(0)


async def test_a_new_entry_is_refused_by_the_kill_switch_and_reserves_nothing(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Step 2: refused, refused **by name**, and with no capital held.

    Refuted by an approval, by a rejection attributed to another check (§12 trap
    9), by a reservation on a refused proposal, or by a decision that does not
    order the pending entries cancelled (``cancel_pending``).
    """
    scene = await _blocked_wallet(engine, factory, wallet)

    refused = await admit_entry(
        factory,
        wallet,
        wallet.market("ETHUSDT"),
        now=at(minutes=2),
        marks=scene.marks,
        client_key="v3-blocked-entry",
    )
    assert refused.approved is False
    assert refused.reservation_state is ReservationState.NONE
    assert refused.decision.cancel_pending is True

    row = await read_proposal(engine, refused.proposal_id)
    assert row.status == ProposalStatus.REJECTED.value
    assert row.reserved_notional is None
    assert row.reserved_slot is False
    stored = RiskDecision.model_validate(row.risk_decision)
    assert stored.effective_kill_switch is KillSwitchState.TRADING_DISABLED
    assert check_of(row.risk_decision, "kill_switch")["state"] == CheckState.FAILED.value
    assert "kill_switch" in stored.rejection_reasons

    async with engine.connect() as connection:
        orders = await connection.scalar(
            text("SELECT count(*) FROM orders WHERE portfolio_id = :pf AND purpose = 'entry'"),
            {"pf": wallet.portfolio_id},
        )
    assert orders == 1, "only the pre-existing position's order; the refusal created none"


async def test_cancelling_the_pending_entry_gives_back_exactly_what_it_held(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Step 3: ``held -> released`` frees the notional, the cash and the slot — no fraction kept.

    Refuted by a cancellation that deletes the row (the proposal is the record of
    a decision about capital and outlives its reservation), by one that keeps any
    part of the exposure, risk or participation budget counted afterwards, or by
    one that rewrites the ``status`` label — vigência and rótulo are separate
    (DATABASE.md §18.3).
    """
    scene = await _blocked_wallet(engine, factory, wallet)
    before = await read_state(factory, wallet, marks=scene.marks, at_instant=at(minutes=2))
    assert before.state is not None
    assert before.state.total_exposure == POSITION_QTY * BLOCK_MARK + PENDING_NOTIONAL
    assert before.state.available_cash == Decimal(19000) - PENDING_NOTIONAL * CASH_MULTIPLIER

    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        released = await close_reservation(
            session,
            organization_id=wallet.org_id,
            proposal_id=scene.pending_proposal_id,
            target=ReservationState.RELEASED,
            now=at(minutes=2, seconds=1),
            reason="kill switch TRADING_DISABLED cancels pending entries",
        )
    assert released.reserved_notional == PENDING_NOTIONAL

    row = await read_proposal(engine, scene.pending_proposal_id)
    assert row.status == ProposalStatus.APPROVED.value, "the label of the decision is untouched"
    assert row.reservation_state == ReservationState.RELEASED.value
    assert row.reserved_slot is False

    after = await read_state(factory, wallet, marks=scene.marks, at_instant=at(minutes=3))
    assert after.state is not None
    assert after.state.pending_entries == ()
    assert after.state.total_exposure == POSITION_QTY * BLOCK_MARK
    assert after.state.available_cash == Decimal(19000), "every unit of cash came back"
    assert after.state.slots_used == 1

    async with engine.connect() as connection:
        released_notional = await connection.scalar(
            text(
                "SELECT coalesce(sum(notional), 0) FROM participation_consumptions "
                "WHERE proposal_id = :id AND kind = 'released'"
            ),
            {"id": scene.pending_proposal_id},
        )
    assert released_notional == PENDING_NOTIONAL, "the market's budget got the whole size back"


async def test_the_protective_exit_is_still_approved_while_entries_are_blocked(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Step 4/5: an entry lock that could reach an exit is a trap, not a lock.

    The position, the wallet state and the effective kill switch all come from
    Postgres; ``evaluate_exit`` is then asked for the whole quantity. Refuted by
    a refusal, by an approved quantity smaller than the position, by an exit
    decision that carries entry checks at all, or by any automatic liquidation of
    the position while the wallet was blocked.
    """
    scene = await _blocked_wallet(engine, factory, wallet)
    build = await read_state(factory, wallet, marks=scene.marks, at_instant=at(minutes=2))
    assert build.state is not None
    position = build.state.position_by_id(scene.position_id)
    assert position is not None

    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        scopes = await effective_state(session, wallet.portfolio_id, system=KillSwitchState.ACTIVE)
    assert scopes.effective is KillSwitchState.TRADING_DISABLED

    decision = evaluate_exit(
        ExitProposal(
            proposal_id=scene.pending_proposal_id,
            portfolio_id=wallet.portfolio_id,
            position_id=scene.position_id,
            market=position.market,
            qty=POSITION_QTY,
            reason=ExitReason.STOP,
        ),
        position,
        PAPER_V1,
        KillSwitchInputs(
            system=scopes.system, organization=scopes.organization, portfolio=scopes.portfolio
        ),
        portfolio=build.state,
    )
    assert decision.approved is True, "a protective exit is never refused by the kill switch"
    assert decision.kind == "exit"
    assert decision.effective_kill_switch is KillSwitchState.TRADING_DISABLED
    assert decision.exit_plan is not None
    assert decision.exit_plan.approved_qty == POSITION_QTY
    assert [check.name for check in decision.checks] != []
    assert "kill_switch" not in [check.name for check in decision.checks]

    async with engine.connect() as connection:
        still_open = await connection.scalar(
            text(
                "SELECT count(*) FROM positions WHERE portfolio_id = :pf AND status = 'open' "
                "AND stop_price IS NOT NULL"
            ),
            {"pf": wallet.portfolio_id},
        )
    assert still_open == 1, "the block liquidated nothing and disarmed no stop"


async def test_the_block_does_not_lift_itself_when_the_loss_goes_away(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Step 5: recovery inside the same day is not a resume.

    Refuted by a latch that returns to ACTIVE on its own — the one path by which
    a wallet could resume trading without the authenticated act the directive §5
    requires — or by a second transition row describing a move nobody made.
    """
    scene = await _blocked_wallet(engine, factory, wallet)
    flat = {market_id: ENTRY_PRICE for market_id in scene.marks}

    _, recovered = await mark_to_market(
        engine, factory, wallet, marks=flat, at_instant=at(minutes=2)
    )
    assert recovered.automatic is KillSwitchState.ACTIVE
    assert recovered.latched is KillSwitchState.TRADING_DISABLED
    assert recovered.changed is False
    assert await read_latch(engine, wallet) is KillSwitchState.TRADING_DISABLED
    assert len(await read_transitions(engine, wallet)) == 1

    still_refused = await admit_entry(
        factory,
        wallet,
        wallet.market("ETHUSDT"),
        now=at(minutes=3),
        marks=flat,
        client_key="v3-after-recovery",
    )
    assert still_refused.approved is False
    assert "kill_switch" in still_refused.decision.rejection_reasons
