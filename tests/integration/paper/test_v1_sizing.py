"""V1 — size, exposure and aggregate risk, proved **in the database**.

The pure core already computes 1.851,800 (``test_sizing.py::TestTheWorkedExample``).
What this file adds is the only thing that file cannot say: that the number which
reaches ``trade_proposals.risk_decision`` through the real opening
(``open_paper_wallet``), the real admission (``admit``) and the real schema is
*that same number*, with the winning ceiling and both counterfactuals stored
next to it — not a second arithmetic that happens to agree today.

Each test says in its docstring what would refute it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import KillSwitchState, ProposalStatus, ReservationState
from hunter_core.domain.types import uuid7
from hunter_risk.decision import CheckState, RiskDecision, Sizing
from hunter_risk.evaluate import evaluate
from hunter_risk.inputs import EntryProposal
from hunter_risk.kill_switch import KillSwitchInputs
from hunter_risk.limits import PAPER_V1

from .conftest import (
    CASH_MULTIPLIER,
    COSTS,
    CREDITED,
    ENGINE_ROLE,
    MEDIAN_MINUTE,
    Wallet,
    admit_entry,
    at,
    beta_for,
    buy_filled,
    cap_of,
    check_of,
    liquidity_for,
    read_proposal,
    read_state,
    request_for,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

EXPECTED_NOTIONAL = Decimal("1851.800")
EXPECTED_QTY = Decimal("18.518")
EXPECTED_RISK = Decimal("49.9986")
EXPECTED_RISK_PCT = Decimal("0.00249993")
"""49,9986 / 20.000 = 0,249993 % — the "0,24999 %" of the brief, exact."""

PARTICIPATION_NOTIONAL = Decimal("46.000")
PARTICIPATION_CEILING = Decimal("46.0510")


def base_marks(wallet: Wallet) -> dict[uuid.UUID, Decimal]:
    """Every market of the fixture at 100 — one declared price source, no lookups."""
    return {market.id: Decimal(100) for market in wallet.markets.values()}


STANDING_RESERVATION = uuid.UUID("00000000-0000-7000-8000-00000000d400")
STANDING_RESERVATION_SQL = text(
    "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, source, "
    "status, direction, idempotency_key, admission_seq, reservation_state, "
    "reserved_notional, reserved_cash, reserved_risk, reserved_slot, reserved_until, "
    "risk_decision, decided_at) VALUES (:id, :org, :pf, :market, 'agent', 'approved', "
    "'long', 'v1-step4-standing', 1, 'held', 400, :cash, 0, true, :until, "
    "'{}'::jsonb, :decided)"
)
"""The 400 of V1 step 4, standing. Written by hand — and only in the xfail case
below — because ``admit`` can never produce a reservation that large on this
wallet, which is itself part of what ``notes-T3.9a.md`` §1 records."""


# --------------------------------------------------------------------------
# Step 2 — the base scenario
# --------------------------------------------------------------------------


async def test_the_row_carries_1851_800_at_0_24999_pct_with_risk_per_trade_binding(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """§0 wallet, entry 100, stop 97,5: the persisted decision is the engine's.

    Refuted by: a ``notional`` in ``trade_proposals.risk_decision`` different
    from 1.851,800; a ``binding_constraint`` other than ``risk_per_trade`` when
    the risk budget is mathematically the smallest ceiling; a reservation that
    holds a different amount of cash than the notional plus its declared fees.
    """
    sol = wallet.market("SOLUSDT")
    result = await admit_entry(
        factory, wallet, sol, now=at(), marks=base_marks(wallet), client_key="v1-base"
    )

    assert result.approved is True
    assert result.status is ProposalStatus.APPROVED
    assert result.decision.sizing is not None
    assert result.decision.sizing.stop_distance_pct == Decimal("0.025")
    assert result.decision.sizing.cost_pct == Decimal("0.0020")

    row = await read_proposal(engine, result.proposal_id)
    stored = RiskDecision.model_validate(row.risk_decision)
    assert stored.sizing is not None
    assert stored.sizing.binding_constraint == "risk_per_trade"
    assert stored.sizing.qty == EXPECTED_QTY
    assert stored.sizing.notional == EXPECTED_NOTIONAL
    assert stored.sizing.planned_risk_quote == EXPECTED_RISK
    assert stored.sizing.planned_risk_pct == EXPECTED_RISK_PCT
    assert stored.sizing.kill_switch_multiplier == Decimal(1)
    assert stored.effective_kill_switch is KillSwitchState.ACTIVE

    assert row.reservation_state == ReservationState.HELD.value
    assert row.reserved_notional == EXPECTED_NOTIONAL
    assert row.reserved_cash == EXPECTED_NOTIONAL * CASH_MULTIPLIER
    assert row.reserved_risk == EXPECTED_RISK
    assert row.reserved_slot is True


async def test_the_persisted_decision_equals_the_pure_engine_on_the_same_inputs(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """Step 2 of V1: the row is not a second implementation of the sizing.

    The state is read from Postgres, handed to ``hunter_risk.evaluate`` on its
    own, and the resulting ``Sizing`` is compared **field by field** with the one
    the admission stored. Refuted by any layer that recomputes: a rounding done
    once in the engine and once again on the way to the column, a ceiling
    dropped between the two, a ``planned_risk_quote`` re-derived from the stored
    notional instead of carried.
    """
    sol = wallet.market("SOLUSDT")
    marks = base_marks(wallet)
    moment = at()
    build = await read_state(factory, wallet, marks=marks, at_instant=moment)
    assert build.state is not None

    isolated = evaluate(
        EntryProposal(
            proposal_id=uuid7(),
            portfolio_id=wallet.portfolio_id,
            market=sol.identity,
            direction=request_for(wallet, sol).direction,
            entry_ref=Decimal(100),
            stop=Decimal("97.5"),
            assumed_costs=COSTS,
        ),
        build.state,
        PAPER_V1,
        liquidity_for(sol, as_of=moment),
        KillSwitchInputs(
            system=KillSwitchState.ACTIVE,
            organization=KillSwitchState.ACTIVE,
            portfolio=KillSwitchState.ACTIVE,
        ),
        beta_for(as_of=moment),
        spec=sol.spec,
    )
    result = await admit_entry(
        factory, wallet, sol, now=moment, marks=marks, client_key="v1-mirror"
    )
    row = await read_proposal(engine, result.proposal_id)
    stored = Sizing.model_validate(row.risk_decision["sizing"])

    assert isolated.sizing is not None
    assert stored == isolated.sizing, "the stored sizing diverged from the pure engine's"


async def test_the_wallet_cash_is_untouched_and_the_curve_still_shows_the_opening(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """A reservation commits a *ceiling*, never money — no fill, no cash movement.

    Refuted by an admission that debits the wallet: the entry has not executed,
    and cash that moved without a fill is money the ledger invented.
    """
    marks = base_marks(wallet)
    before = await read_state(factory, wallet, marks=marks, at_instant=at())
    await admit_entry(
        factory,
        wallet,
        wallet.market("SOLUSDT"),
        now=at(),
        marks=marks,
        client_key="v1-cash-untouched",
    )
    after = await read_state(factory, wallet, marks=marks, at_instant=at(seconds=1))

    assert before.cash == after.cash == CREDITED
    assert after.state is not None
    assert after.state.available_cash == CREDITED - EXPECTED_NOTIONAL * CASH_MULTIPLIER
    assert after.state.total_exposure == EXPECTED_NOTIONAL


# --------------------------------------------------------------------------
# Step 3 — the participation ceiling of the median minute
# --------------------------------------------------------------------------


async def test_the_median_minute_makes_participation_win_at_46_000(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """4.605,10 of minute volume: 1 % of it is 46,0510 and the row says 46,000.

    Refuted by a ceiling read from the 24 h volume instead of the reference
    minute, by a rounding *up* to 46,051, or by a ``binding_constraint`` that
    still names ``risk_per_trade`` while the size actually taken was the
    participation one.
    """
    sol = wallet.market("SOLUSDT")
    result = await admit_entry(
        factory,
        wallet,
        sol,
        now=at(),
        marks=base_marks(wallet),
        client_key="v1-participation",
        liquidity=liquidity_for(sol, as_of=at(), minute_volume=MEDIAN_MINUTE),
    )

    row = await read_proposal(engine, result.proposal_id)
    stored = RiskDecision.model_validate(row.risk_decision)
    assert stored.sizing is not None
    assert stored.sizing.binding_constraint == "market_participation"
    assert stored.sizing.notional == PARTICIPATION_NOTIONAL
    ceiling = cap_of(row.risk_decision, "market_participation")["notional"]
    assert isinstance(ceiling, str), "a ceiling stored as a JSON number is a float"
    assert Decimal(ceiling) == PARTICIPATION_CEILING, "1 % of 4.605,10 is 46,0510"
    assert row.reserved_notional == PARTICIPATION_NOTIONAL


async def test_the_two_counterfactuals_are_persisted_and_differ(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """The panel has to be able to say how much the participation rule bit.

    Refuted by counterfactuals equal to each other (a copy of the same number
    under two labels), or by a ``size_without_participation`` that is not the
    1.851,800 the same wallet would have taken without that ceiling.
    """
    sol = wallet.market("SOLUSDT")
    result = await admit_entry(
        factory,
        wallet,
        sol,
        now=at(),
        marks=base_marks(wallet),
        client_key="v1-counterfactual",
        liquidity=liquidity_for(sol, as_of=at(), minute_volume=MEDIAN_MINUTE),
    )
    row = await read_proposal(engine, result.proposal_id)
    stored = Sizing.model_validate(row.risk_decision["sizing"])

    assert stored.size_without_participation.notional == EXPECTED_NOTIONAL
    assert stored.size_without_multipliers.notional == PARTICIPATION_NOTIONAL
    assert stored.size_without_participation.notional != stored.size_without_multipliers.notional


# --------------------------------------------------------------------------
# Aggregate planned risk — §13 decision 1, answered from the code
# --------------------------------------------------------------------------


async def test_a_position_under_water_contributes_zero_planned_risk_never_a_negative(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The aggregate is a sum of non-negatives; nothing offsets anything.

    §13's open question — "is there a path where ``planned_risk_quote`` is
    negative?" — answered against the ledger: a position marked **below** its
    own stop has already lost more than it planned, and
    ``marking._planned_risk`` clamps it to zero. So the aggregate can never be
    freed by a losing position, and never nets a profitable one against a
    losing one.

    Refuted by a negative contribution: 90 marked against a stop of 99,5 would
    return −9,5 per unit and *widen* the budget for the next entry, which is
    precisely the artificial room V1 exists to forbid.
    """
    btc = wallet.market("BTCUSDT")
    eth = wallet.market("ETHUSDT")
    await buy_filled(
        factory, wallet, btc, qty=Decimal(1), price=Decimal(100), stop=Decimal("99.5"), ts=at()
    )
    await buy_filled(
        factory, wallet, eth, qty=Decimal(2), price=Decimal(100), stop=Decimal("90"), ts=at()
    )

    marks = {btc.id: Decimal(90), eth.id: Decimal(100), wallet.market("SOLUSDT").id: Decimal(100)}
    build = await read_state(factory, wallet, marks=marks, at_instant=at(seconds=1))
    assert build.state is not None

    by_asset = {p.market.base_asset: p.planned_risk_quote for p in build.state.open_positions}
    assert by_asset["BTC"] == Decimal(0), "a loss beyond the stop is not negative risk"
    assert by_asset["ETH"] == Decimal(20), "(100 - 90) x 2, the plain stop distance"
    assert build.state.committed_planned_risk == Decimal(20)
    assert all(p.planned_risk_quote >= 0 for p in build.state.open_positions)


async def test_the_aggregate_sums_open_and_pending_without_netting(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Open risk plus reserved risk, added — never ``max(0, Σ assinado)``.

    Refuted by an aggregate that ignores the pending entry (the reservation is
    risk already committed, DATABASE.md §18.3) or that reports the larger of the
    two instead of their sum.
    """
    btc = wallet.market("BTCUSDT")
    sol = wallet.market("SOLUSDT")
    await buy_filled(
        factory, wallet, btc, qty=Decimal(2), price=Decimal(100), stop=Decimal("95"), ts=at()
    )
    marks = base_marks(wallet)
    await admit_entry(
        factory, wallet, sol, now=at(seconds=1), marks=marks, client_key="v1-aggregate"
    )

    build = await read_state(factory, wallet, marks=marks, at_instant=at(seconds=2))
    assert build.state is not None
    open_risk = sum(p.planned_risk_quote for p in build.state.open_positions)
    pending_risk = sum(e.planned_risk_quote for e in build.state.pending_entries)
    assert open_risk == Decimal(10)
    assert pending_risk == EXPECTED_RISK
    assert build.state.committed_planned_risk == Decimal(10) + EXPECTED_RISK


# --------------------------------------------------------------------------
# The market that no longer exists — check 7 of §3.1
# --------------------------------------------------------------------------


async def test_a_reference_of_100_against_a_market_at_110_is_refused_by_signal_validity(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """The reviewer's case of 2026-09-06, persisted: refused, and refused by name.

    Refuted by an approval (the proposal describes a market that no longer
    exists), by a rejection blamed on any other check, or by a reservation held
    for a refused proposal.
    """
    sol = wallet.market("SOLUSDT")
    result = await admit_entry(
        factory,
        wallet,
        sol,
        now=at(),
        marks={**base_marks(wallet), sol.id: Decimal(110)},
        client_key="v1-out-of-zone",
        liquidity=liquidity_for(sol, as_of=at(), last_price=Decimal(110)),
    )

    assert result.approved is False
    assert result.reservation_state is ReservationState.NONE
    row = await read_proposal(engine, result.proposal_id)
    check = check_of(row.risk_decision, "signal_validity")
    assert check["state"] == CheckState.FAILED.value
    assert Decimal(check["value"]).quantize(Decimal("0.000001")) == Decimal("0.090909")
    assert Decimal(check["limit"]) == PAPER_V1.max_entry_deviation_pct
    assert row.status == ProposalStatus.REJECTED.value
    assert row.reserved_notional is None


# --------------------------------------------------------------------------
# §12 — the traps, as negative assertions
# --------------------------------------------------------------------------


async def test_no_float_survives_anywhere_in_the_persisted_decision(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """Trap 5: a ``float`` in the path is the bug, not the test's convenience.

    Every number in ``risk_decision`` has to come back as a JSON *string* (a
    ``Decimal`` serialised, exact) and every money column as ``Decimal``.
    Refuted by any ``float`` in the stored JSON — the value that silently became
    ``0.30000000000000004`` somewhere between the engine and the column.
    """
    result = await admit_entry(
        factory,
        wallet,
        wallet.market("SOLUSDT"),
        now=at(),
        marks=base_marks(wallet),
        client_key="v1-no-float",
    )
    row = await read_proposal(engine, result.proposal_id)

    floats: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, float):
            floats.append(path)
        elif isinstance(node, dict):
            for key, value in cast("dict[str, object]", node).items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(cast("list[object]", node)):
                walk(value, f"{path}[{index}]")

    walk(row.risk_decision, "risk_decision")
    assert floats == [], f"float found in the persisted decision at {floats}"
    assert isinstance(row.reserved_notional, Decimal)
    assert isinstance(row.reserved_cash, Decimal)


async def test_the_market_specs_are_the_recorded_binance_filters(wallet: Wallet) -> None:
    """§0's markets are labelled with the filters the recorder actually measured.

    Refuted by a step size or a minimum notional typed into this suite: the SOL
    numbers of §0 (0,001 / 5 / 0,01) are asserted to *be* the recorded SOLUSDT
    filters, and BTC/ETH are read from the same file (§13 item 3).
    """
    assert wallet.market("SOLUSDT").spec.step_size == Decimal("0.00100000")
    assert wallet.market("SOLUSDT").spec.min_notional == Decimal("5.00000000")
    assert wallet.market("SOLUSDT").spec.tick_size == Decimal("0.01000000")
    assert wallet.market("BTCUSDT").spec.step_size == Decimal("0.00001000")
    assert wallet.market("ETHUSDT").spec.step_size == Decimal("0.00010000")
    assert wallet.market("ETHUSDT").spec.min_notional == Decimal("5.00000000")


# --------------------------------------------------------------------------
# Step 4 — the cash ceiling. The spec's number does not survive the ledger.
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "V1 step 4 is unreachable through the persisted path: notes-T3.9a.md §1. "
        "In the ledger equity = cash + exposure, so cash/1,00100024 < 0,4 x equity - "
        "exposure never holds. Measured winner: 'total_exposure'. The 99,599904 of "
        "available_cash IS reproduced below and passes — only 'cash wins' does not."
    ),
)
async def test_v1_step4_the_cash_ceiling_wins_with_500_of_cash_and_400_reserved(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """The spec's fourth scenario, reproduced as faithfully as the ledger allows.

    500 of cash (19.500 spent on a real fill) and a standing reservation of 400
    in another market: ``available_cash`` is exactly 500 − 400 × 1,00100024 =
    99,599904, and the spec expects ``binding_constraint = "cash"``.

    It is not, and the number is not adjusted: the ceiling that actually wins is
    recorded in ``notes-T3.9a.md``. Refuted (i.e. this test would start passing)
    if the exposure ceilings were removed — which would be a defect, not a fix.
    """
    btc = wallet.market("BTCUSDT")
    eth = wallet.market("ETHUSDT")
    sol = wallet.market("SOLUSDT")
    await buy_filled(
        factory, wallet, btc, qty=Decimal(195), price=Decimal(100), stop=Decimal("99.9"), ts=at()
    )
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        await session.execute(
            STANDING_RESERVATION_SQL,
            {
                "id": STANDING_RESERVATION,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "market": eth.id,
                "until": at(seconds=30),
                "decided": at(),
                "cash": Decimal(400) * CASH_MULTIPLIER,
            },
        )
        # The standing reservation took FIFO place 1, so the wallet's counter has
        # to say so: the next admission asks for the following place, and
        # ``uq_trade_proposals_admission_seq`` is what makes that a fact.
        await session.execute(
            text("UPDATE portfolio_risk_state SET last_admission_seq = 1 WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )

    marks = {btc.id: Decimal(100), eth.id: Decimal(100), sol.id: Decimal(100)}
    build = await read_state(factory, wallet, marks=marks, at_instant=at(seconds=1))
    assert build.state is not None
    assert build.state.cash == Decimal(500)
    assert build.state.available_cash == Decimal("99.599904")

    result = await admit_entry(
        factory, wallet, sol, now=at(seconds=2), marks=marks, client_key="v1-cash"
    )
    row = await read_proposal(engine, result.proposal_id)
    assert row.risk_decision["sizing"]["binding_constraint"] == "cash"
    assert Decimal(cap_of(row.risk_decision, "cash")["limit"]) == Decimal("99.599904")
