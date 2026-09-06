"""Properties that must hold for every proposal, not just for the table cases.

The generators deliberately build **populated** wallets: open positions,
reservations and betas anywhere in ``[-3, 3]``. With an empty wallet and a beta
of exactly 1 the aggregate ceilings (`beta_exposure`, `aggregate_risk`,
`asset_exposure`, `total_exposure`) can never be the binding one, so the samples
proved nothing about them (review of 2026-09-06, finding 9). The observed price
also moves around the reference, which is what exercises the worst-price rule of
finding 2.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import NamedTuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.decision import RiskDecision
from hunter_risk.evaluate import evaluate
from hunter_risk.exposure import OpenPosition, PendingEntry, PortfolioState
from hunter_risk.kill_switch import KillSwitchInputs
from hunter_risk.limits import PAPER_V1

from .factories import (
    beta,
    deep_book,
    liquidity,
    market,
    pending,
    portfolio,
    position,
    proposal,
    spec,
)

pytestmark = pytest.mark.unit

SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])

equities = st.decimals(
    min_value=Decimal("2000"), max_value=Decimal("5000000"), places=2, allow_nan=False
)
stop_pcts = st.decimals(min_value=Decimal("0.001"), max_value=Decimal("0.2"), places=4)
minute_volumes = st.decimals(min_value=Decimal("100"), max_value=Decimal("5000000"), places=2)
cash_fractions = st.decimals(min_value=Decimal("0.05"), max_value=Decimal("1"), places=2)
betas = st.decimals(min_value=Decimal("-3"), max_value=Decimal("3"), places=2)
"""Directive §4 counts ``|notional x beta|``: a short-correlated asset at -2,5 has
to consume the same budget as a long-correlated one at 2,5."""

price_offsets = st.decimals(min_value=Decimal("-0.01"), max_value=Decimal("0.01"), places=4)
"""Where the market sits relative to ``entry_ref``: inside and outside the
±0,5 % entry band, on both sides."""

holdings = st.lists(
    st.tuples(
        st.decimals(min_value=Decimal("0"), max_value=Decimal("0.09"), places=3),
        st.decimals(min_value=Decimal("0"), max_value=Decimal("0.004"), places=4),
        betas,
        st.booleans(),
    ),
    max_size=3,
)
"""Each holding: notional as a fraction of equity, planned risk as a fraction of
equity, its beta, and whether it is already open or still a reservation."""


class Case(NamedTuple):
    """One sampled world: a wallet, a market and a proposal against them."""

    equity: Decimal
    stop_pct: Decimal
    minute_volume: Decimal
    cash_fraction: Decimal
    beta_value: Decimal
    price_offset: Decimal
    held: list[tuple[Decimal, Decimal, Decimal, bool]]


cases = st.builds(
    Case,
    equity=equities,
    stop_pct=stop_pcts,
    minute_volume=minute_volumes,
    cash_fraction=cash_fractions,
    beta_value=betas,
    price_offset=price_offsets,
    held=holdings,
)


def _wallet(
    equity: Decimal,
    cash_fraction: Decimal,
    held: list[tuple[Decimal, Decimal, Decimal, bool]],
) -> PortfolioState:
    positions: list[OpenPosition] = []
    reservations: list[PendingEntry] = []
    for index, (exposure_pct, risk_pct, beta_value, is_open) in enumerate(held):
        notional = (equity * exposure_pct).quantize(Decimal("0.01"))
        risk = (equity * risk_pct).quantize(Decimal("0.01"))
        if notional <= Decimal(0):
            continue
        coin = market(f"C{index}USDT", f"C{index}")
        if is_open:
            positions.append(
                position(
                    position_id=uuid.UUID(int=index + 1),
                    market=coin,
                    notional=notional,
                    planned_risk_quote=risk,
                    beta_btc=beta_value,
                )
            )
        else:
            reservations.append(
                pending(
                    market=coin,
                    reserved_notional=notional,
                    planned_risk_quote=risk,
                    beta_btc=beta_value,
                )
            )
    return portfolio(
        equity=equity,
        cash=(equity * cash_fraction).quantize(Decimal("0.01")),
        open_positions=tuple(positions),
        pending_entries=tuple(reservations),
    )


def _decide(case: Case, state: KillSwitchState) -> RiskDecision:
    entry = Decimal("100")
    observed = _observed(case)
    return evaluate(
        proposal(stop=(entry * (Decimal(1) - case.stop_pct)).quantize(Decimal("0.00000001"))),
        _wallet(case.equity, case.cash_fraction, case.held),
        PAPER_V1,
        liquidity(
            last_price=observed,
            mid_price=observed,
            best_bid=observed - Decimal("0.001"),
            best_ask=observed + Decimal("0.001"),
            asks=deep_book(observed),
            last_minute_quote_volume=case.minute_volume,
            median_30m_quote_volume=case.minute_volume,
        ),
        KillSwitchInputs(portfolio=state),
        beta(value=case.beta_value),
        spec=spec(),
    )


def _observed(case: Case) -> Decimal:
    """Where the market sits for this sample."""
    return (Decimal("100") * (Decimal(1) + case.price_offset)).quantize(Decimal("0.0001"))


@SETTINGS
@given(cases)
def test_the_size_never_exceeds_any_ceiling(case: Case) -> None:
    got = _decide(case, KillSwitchState.ACTIVE)
    assert got.sizing is not None
    for cap in got.sizing.caps:
        if cap.notional is not None:
            assert got.sizing.notional <= cap.notional


@SETTINGS
@given(cases)
def test_the_planned_risk_never_exceeds_the_quarter_percent(case: Case) -> None:
    got = _decide(case, KillSwitchState.ACTIVE)
    assert got.sizing is not None
    assert got.sizing.planned_risk_pct <= PAPER_V1.risk_per_trade_pct


@SETTINGS
@given(cases)
def test_an_approved_entry_never_breaks_an_aggregate_ceiling(case: Case) -> None:
    """The ceilings that only bind on a populated wallet, measured after the entry."""
    got = _decide(case, KillSwitchState.ACTIVE)
    if not got.approved:
        return
    assert got.sizing is not None
    state = _wallet(case.equity, case.cash_fraction, case.held)
    equity = state.equity
    notional = got.sizing.notional
    beta_used = state.beta_exposure()
    assert beta_used is not None
    assert state.total_exposure + notional <= equity * PAPER_V1.max_total_exposure_pct
    assert beta_used + abs(notional * case.beta_value) <= equity * PAPER_V1.max_beta_btc_exposure
    assert (
        state.committed_planned_risk + got.sizing.planned_risk_quote
        <= equity * PAPER_V1.max_aggregate_planned_risk_pct
    )


@SETTINGS
@given(cases)
def test_an_approved_entry_never_spends_more_cash_than_the_reservations_left(case: Case) -> None:
    """Finding 4 as a property: the reservations are subtracted, always."""
    got = _decide(case, KillSwitchState.ACTIVE)
    if not got.approved:
        return
    assert got.sizing is not None
    state = _wallet(case.equity, case.cash_fraction, case.held)
    cash_check = next(check for check in got.checks if check.name == "cash")
    assert cash_check.value is not None and cash_check.limit is not None
    assert cash_check.value <= cash_check.limit
    assert cash_check.limit <= state.cash


@SETTINGS
@given(cases)
def test_the_sizing_price_is_never_kinder_than_the_market(case: Case) -> None:
    """Finding 2 as a property: a stale reference never widens a ceiling."""
    got = _decide(case, KillSwitchState.ACTIVE)
    assert got.sizing is not None
    observed = _observed(case)
    assert got.sizing.sizing_price == max(got.sizing.entry_ref, observed)
    if got.approved:
        deviation = abs(got.sizing.entry_ref - observed) / observed
        assert deviation <= PAPER_V1.max_entry_deviation_pct
        assert got.sizing.stop < observed


@SETTINGS
@given(cases)
def test_warning_never_produces_a_larger_size_than_active(case: Case) -> None:
    full = _decide(case, KillSwitchState.ACTIVE)
    half = _decide(case, KillSwitchState.WARNING)
    assert full.sizing is not None
    assert half.sizing is not None
    assert half.sizing.notional <= full.sizing.notional
    # R-KS-1: whenever the full size was tradable at all, the warning really halves it.
    if full.approved:
        assert half.sizing.notional_after_multiplier == full.sizing.notional_before_multiplier / 2


@SETTINGS
@given(cases)
def test_an_approved_entry_is_always_tradable(case: Case) -> None:
    got = _decide(case, KillSwitchState.ACTIVE)
    if got.approved:
        assert got.sizing is not None
        assert got.sizing.qty > Decimal(0)
        assert got.sizing.notional >= spec().min_notional
        assert got.sizing.qty % spec().step_size == Decimal(0)


@SETTINGS
@given(cases)
def test_the_declared_stop_survives_every_ceiling(case: Case) -> None:
    expected = (Decimal("100") * (Decimal(1) - case.stop_pct)).quantize(Decimal("0.00000001"))
    got = _decide(case, KillSwitchState.ACTIVE)
    assert got.sizing is not None
    assert got.sizing.stop == expected
