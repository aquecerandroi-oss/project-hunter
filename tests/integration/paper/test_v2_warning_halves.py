"""V2 — AVISO really halves the entry, on the persisted path.

The route to WARNING here is the honest one: a real position, marked down by a
real mark to market until the day's loss is exactly 1 %, evaluated by
``evaluate_and_persist``, which writes the transition and moves
``portfolios.kill_switch_state``. Nothing is written into the column
(§12 trap 10), and no ``size_multiplier`` is passed by hand — the admission
reads the latch under the wallet lock, as the Risk Center will.

The wallet then **recovers** to 20.000 before the entry is proposed. That is
deliberate and it is what makes this file about the *durable* latch: at the
moment of the decision the automatic ladder says ACTIVE and only the latched
WARNING is left to halve the size. A multiplier read from the state instead of
from the row would produce 1.851,800 here, and that is exactly the R-KS-1 defect
V2 exists to catch.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.domain.enums import KillSwitchState, ProposalStatus, ReservationState
from hunter_risk.decision import RiskDecision

from .conftest import (
    CASH_MULTIPLIER,
    CREDITED,
    MEDIAN_MINUTE,
    Wallet,
    admit_entry,
    at,
    buy_filled,
    liquidity_for,
    mark_to_market,
    read_latch,
    read_proposal,
    read_risk_state,
    read_transitions,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

ACTIVE_NOTIONAL = Decimal("1851.800")
WARNING_NOTIONAL = Decimal("925.900")
WARNING_QTY = Decimal("9.259")
MULTIPLIER = Decimal("0.5")
"""``paper_v1.warning_size_multiplier`` — the 0,5 of the directive §5."""

POSITION_QTY = Decimal(10)
ENTRY_PRICE = Decimal(100)
LOSS_MARK = Decimal(80)
"""10 units bought at 100 (cash 19.000) marked at 80: equity 19.800, exactly
1 % below the day's opening of 20.000 — the WARNING rung, and only that rung
(the drawdown from a peak of 20.000 is 1 %, far under the 4 % of the same rung)."""


async def _walk_to_warning_and_back(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> dict[uuid.UUID, Decimal]:
    """Buy, lose exactly 1 %, latch WARNING, then recover to the opening equity."""
    btc = wallet.market("BTCUSDT")
    await buy_filled(
        factory,
        wallet,
        btc,
        qty=POSITION_QTY,
        price=ENTRY_PRICE,
        stop=Decimal("99.5"),
        ts=at(),
    )
    flat = {market.id: ENTRY_PRICE for market in wallet.markets.values()}
    down = {**flat, btc.id: LOSS_MARK}

    build, warned = await mark_to_market(
        engine, factory, wallet, marks=down, at_instant=at(minutes=1)
    )
    assert build.equity == Decimal(19800)
    assert warned.latched is KillSwitchState.WARNING
    assert warned.daily_loss_pct == Decimal("0.01")

    _, recovered = await mark_to_market(
        engine, factory, wallet, marks=flat, at_instant=at(minutes=2)
    )
    assert recovered.automatic is KillSwitchState.ACTIVE, "the loss is gone"
    assert recovered.latched is KillSwitchState.WARNING, "the latch is not"
    assert recovered.changed is False
    return flat


async def test_a_real_one_percent_loss_latches_warning_with_its_evidence(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Step 1: the state is produced by the wallet's own movement, never seeded.

    Refuted by a WARNING that appears without a ``kill_switch_transitions`` row
    (the deferred trigger would reject it, and a test that wrote the column
    directly would be proving nothing), by evidence without the numbers that
    justified it, or by a latch that clears itself when the loss goes away
    inside the same trading day.
    """
    await _walk_to_warning_and_back(engine, factory, wallet)

    assert await read_latch(engine, wallet) is KillSwitchState.WARNING
    transitions = await read_transitions(engine, wallet)
    assert [(t.from_state, t.to_state, t.actor_type) for t in transitions] == [
        (KillSwitchState.ACTIVE.value, KillSwitchState.WARNING.value, "system")
    ]
    evidence = transitions[0].evidence
    # Strings in the row, ``Decimal`` in the assertion: the evidence is stored as
    # text precisely so no float ever reaches it (``build_evidence``), and the
    # comparison is exact, never a tolerance.
    assert all(isinstance(evidence[key], str) for key in ("daily_loss_pct", "equity"))
    assert Decimal(evidence["daily_loss_pct"]) == Decimal("0.01")
    assert Decimal(evidence["equity"]) == Decimal(19800)
    assert Decimal(evidence["day_start_equity"]) == CREDITED
    assert Decimal(evidence["warning_daily_loss_pct"]) == Decimal("0.01")

    row = await read_risk_state(engine, wallet)
    assert row.equity_day_start == CREDITED, "a WARNING never redefines the day's opening"
    assert row.peak_equity == CREDITED, "nor raises the peak on the way down"


async def test_the_latched_warning_halves_the_final_size_to_925_900(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """1.851,800 in ACTIVE becomes 925,900 in AVISO — the same proposal, the same wallet.

    Refuted by a persisted ``notional`` equal to the ACTIVE one (R-KS-1: the
    multiplier applied to a budget that another ceiling then overrode), by a
    ``kill_switch_multiplier`` of 1 while the row says WARNING, or by a
    reservation that holds the cash of the *unhalved* size.
    """
    flat = await _walk_to_warning_and_back(engine, factory, wallet)

    result = await admit_entry(
        factory,
        wallet,
        wallet.market("SOLUSDT"),
        now=at(minutes=3),
        marks=flat,
        client_key="v2-warning",
    )
    assert result.approved is True
    assert result.status is ProposalStatus.APPROVED

    row = await read_proposal(engine, result.proposal_id)
    stored = RiskDecision.model_validate(row.risk_decision)
    assert stored.sizing is not None
    assert stored.effective_kill_switch is KillSwitchState.WARNING
    assert stored.sizing.kill_switch_multiplier == MULTIPLIER
    assert stored.sizing.binding_constraint == "risk_per_trade"
    assert stored.sizing.notional_before_multiplier == Decimal("1851.851851851851851851851852")
    assert stored.sizing.notional_after_multiplier == Decimal("925.925925925925925925925926")
    assert stored.sizing.qty == WARNING_QTY
    assert stored.sizing.notional == WARNING_NOTIONAL
    assert stored.sizing.size_without_multipliers.notional == ACTIVE_NOTIONAL

    assert row.kill_switch_snapshot["effective"] == KillSwitchState.WARNING.value
    assert row.kill_switch_snapshot["portfolio"] == KillSwitchState.WARNING.value
    assert row.reservation_state == ReservationState.HELD.value
    assert row.reserved_notional == WARNING_NOTIONAL
    assert row.reserved_cash == WARNING_NOTIONAL * CASH_MULTIPLIER


async def test_the_multiplier_comes_from_the_row_not_from_the_recovered_state(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The two sources that must not disagree: the latch and what the panel shows.

    At the instant of this decision the wallet's equity is back at 20.000 and
    the automatic ladder says ACTIVE — so a size of 1.851,800 would mean the
    admission sized against its *own* re-assessment of the state and ignored the
    durable latch the Risk Center displays. Refuted by exactly that number.
    """
    flat = await _walk_to_warning_and_back(engine, factory, wallet)

    result = await admit_entry(
        factory,
        wallet,
        wallet.market("SOLUSDT"),
        now=at(minutes=3),
        marks=flat,
        client_key="v2-source-of-truth",
    )
    assert result.decision.sizing is not None
    assert result.decision.sizing.notional != ACTIVE_NOTIONAL
    assert result.decision.sizing.notional == WARNING_NOTIONAL
    assert await read_latch(engine, wallet) is KillSwitchState.WARNING

    row = await read_risk_state(engine, wallet)
    assert row.equity_day_start == CREDITED
    assert row.peak_equity == CREDITED, "recovering to the opening does not move the peak"


async def test_the_multiplier_bites_the_participation_ceiling_too(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """R-KS-1: AVISO halves **whatever** ceiling won, not only the risk budget.

    With the median minute of 4.605,10 the winner is ``market_participation``
    (46,000 in ACTIVE, proved in ``test_v1_sizing.py``). Under AVISO the winner
    must stay the same and the size must fall. Refuted by a size that stays at
    46,000 — the multiplier applied to the risk budget alone — or by a
    ``binding_constraint`` that changes because the halving was done before the
    ceilings were compared.
    """
    flat = await _walk_to_warning_and_back(engine, factory, wallet)
    sol = wallet.market("SOLUSDT")

    result = await admit_entry(
        factory,
        wallet,
        sol,
        now=at(minutes=3),
        marks=flat,
        client_key="v2-participation",
        liquidity=liquidity_for(sol, as_of=at(minutes=3), minute_volume=MEDIAN_MINUTE),
    )
    row = await read_proposal(engine, result.proposal_id)
    stored = RiskDecision.model_validate(row.risk_decision)
    assert stored.sizing is not None
    assert stored.sizing.binding_constraint == "market_participation"
    assert stored.sizing.notional < Decimal("46.000")
    # Measured here for the first time (the spec deliberately fixed no third
    # number): 1 % of 4.605,10 halved is 23,0255, floored to the 0,001 step.
    assert stored.sizing.notional == Decimal("23.000")
    assert row.reserved_notional == Decimal("23.000")


async def test_the_halved_size_at_an_equity_of_19_800_is_916_600(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """What the wallet of V2's own preconditions actually gets, measured.

    Equity 19.800 (the -1 % that raised the WARNING, still standing): the risk
    budget is 49,50, the ceiling 1.833,333…, the half 916,666… and the floored
    size 916,600. This is the number ``notes-T3.9a.md`` §2 records against the
    spec's 925,900. Refuted by a size measured on the *opening* equity instead of
    the current one — which would size an entry with money the wallet has lost.
    """
    btc = wallet.market("BTCUSDT")
    await buy_filled(
        factory, wallet, btc, qty=POSITION_QTY, price=ENTRY_PRICE, stop=Decimal("99.5"), ts=at()
    )
    down = {market.id: ENTRY_PRICE for market in wallet.markets.values()}
    down[btc.id] = LOSS_MARK
    build, warned = await mark_to_market(
        engine, factory, wallet, marks=down, at_instant=at(minutes=1)
    )
    assert build.equity == Decimal(19800)
    assert warned.latched is KillSwitchState.WARNING

    result = await admit_entry(
        factory,
        wallet,
        wallet.market("SOLUSDT"),
        now=at(minutes=2),
        marks=down,
        client_key="v2-measured-19800",
    )
    row = await read_proposal(engine, result.proposal_id)
    stored = RiskDecision.model_validate(row.risk_decision)
    assert stored.sizing is not None
    assert stored.sizing.notional_before_multiplier == Decimal("1833.333333333333333333333333")
    assert stored.sizing.qty == Decimal("9.166")
    assert stored.sizing.notional == Decimal("916.600")
    assert row.reserved_notional == Decimal("916.600")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "notes-T3.9a.md §2: V2's own preconditions are arithmetically "
        "inconsistent. 925,900 is half of the budget of a 20.000 wallet; with the "
        "equity actually at 19.800 (the -1 % the spec asks for) the risk budget is "
        "49,50 and the halved size is 916,600. The number is not adjusted."
    ),
)
async def test_v2_the_spec_number_925_900_at_an_equity_of_19_800(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """V2 read literally: equity 19.800 **and** a final size of 925,900.

    Both cannot hold at once. This test states the spec's pair and fails on the
    size, so the divergence is visible in the suite instead of being silently
    corrected in a table. Refuted (it would pass) only if the risk budget stopped
    being measured on the current equity — which the contract requires it to be.
    """
    btc = wallet.market("BTCUSDT")
    await buy_filled(
        factory, wallet, btc, qty=POSITION_QTY, price=ENTRY_PRICE, stop=Decimal("99.5"), ts=at()
    )
    down = {market.id: ENTRY_PRICE for market in wallet.markets.values()}
    down[btc.id] = LOSS_MARK

    build, warned = await mark_to_market(
        engine, factory, wallet, marks=down, at_instant=at(minutes=1)
    )
    assert build.equity == Decimal(19800)
    assert warned.latched is KillSwitchState.WARNING

    result = await admit_entry(
        factory,
        wallet,
        wallet.market("SOLUSDT"),
        now=at(minutes=2),
        marks=down,
        client_key="v2-spec-literal",
    )
    assert result.decision.sizing is not None
    assert result.decision.sizing.notional == WARNING_NOTIONAL
