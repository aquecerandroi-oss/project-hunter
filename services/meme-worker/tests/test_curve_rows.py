"""What a curve reading teaches the token row (T4.2d): the two REST-side
signals, the denominator with its source, and ``completed_at`` through the
reducer — over the real fixtures of T4.1/T4.2c."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hunter_meme_worker.curve_rows import token_row_from_curve, tracked_from_curve
from hunter_meme_worker.graduation import GLOBAL_PARAMS, OBSERVED_VIRGIN
from hunter_meme_worker.tracker import TrackedMint

from hunter_exchanges.pumpfun import normalize
from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_exchanges.pumpfun.quote import GlobalParams

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
T0 = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)
PARAMS = GlobalParams(
    slot=354155511,
    signature="x",
    initial_virtual_token_reserves=1073000000000000,
    initial_virtual_sol_reserves=30000000000,
    initial_real_token_reserves=793100000000000,
    token_total_supply=1000000000000000,
    fee_basis_points=95,
    timestamp=1752856476446,
)


def _fixture(name: str) -> NormalizedCurveState:
    raw: dict[str, Any] = json.loads((FIXTURES / name).read_text(), parse_float=Decimal)
    return normalize.parse_curve_state_rest(raw)


def _state(*, real_sol: str, real_token: str, complete: bool = False) -> NormalizedCurveState:
    return NormalizedCurveState(
        mint="MINT",
        virtual_sol_reserves=Decimal("30"),
        virtual_token_reserves=Decimal("1073000000"),
        real_sol_reserves=Decimal(real_sol),
        real_token_reserves=Decimal(real_token),
        total_supply=Decimal("1000000000"),
        complete=complete,
        market_cap_sol=Decimal("27.96"),
        source="pumpfun_rest",
        observed_at=T0,
        received_at=T0,
    )


def test_the_real_graduated_coin_is_rest_complete_with_a_zero_reserve_and_not_completed() -> None:
    """``frontend_api_v3_coin_graduated_raw.json``: ``complete = true``,
    ``real_sol_reserves = 0``, ``real_token_reserves = 0`` — the reserve already
    left for the pool. The photo is a signal; it is not a completion by itself
    (T4.2c stamped ``completed_at`` from it; T4.2d does not)."""
    state = _fixture("frontend_api_v3_coin_graduated_raw.json")
    assert state.complete and state.real_sol_reserves == 0
    row = token_row_from_curve(state, params=PARAMS)
    assert row.rest_complete_seen_at == state.observed_at
    assert row.curve_filled_seen_at is None and row.completed_at is None
    assert (row.initial_real_token_reserves, row.progress_denominator_source) == (
        Decimal("793100000"),
        GLOBAL_PARAMS,
    ), "a finished standard curve still has the record's denominator: progress = 1"


def test_the_real_mid_curve_mayhem_coin_gets_no_denominator_from_the_photo_alone() -> None:
    """``frontend_api_v3_coin_by_mint_response_raw.json`` (``2sduGq…``, paused
    Mayhem): 822,6 M real tokens on the curve, above the record's 793,1 M —
    the photo cannot tell the agent's tokens from the initial, so it claims
    nothing; the chain read does (``test_mayhem.py``)."""
    state = _fixture("frontend_api_v3_coin_by_mint_response_raw.json")
    assert state.real_token_reserves > Decimal("793100000")
    row = token_row_from_curve(state, params=PARAMS)
    assert row.initial_real_token_reserves is None
    assert row.progress_denominator_source is None
    assert row.rest_complete_seen_at is None and row.completed_at is None


def test_a_virgin_curve_is_observed_and_a_bought_standard_curve_takes_the_record() -> None:
    virgin = token_row_from_curve(_state(real_sol="0", real_token="793100000"), params=None)
    assert (virgin.initial_real_token_reserves, virgin.progress_denominator_source) == (
        Decimal("793100000"),
        OBSERVED_VIRGIN,
    )
    bought = token_row_from_curve(_state(real_sol="3", real_token="700000000"), params=PARAMS)
    assert (bought.initial_real_token_reserves, bought.progress_denominator_source) == (
        Decimal("793100000"),
        GLOBAL_PARAMS,
    )
    unknown = token_row_from_curve(_state(real_sol="3", real_token="700000000"), params=None)
    assert unknown.initial_real_token_reserves is None
    assert unknown.progress_denominator_source is None


def test_a_filled_curve_with_sol_in_it_is_completed_at_the_photo() -> None:
    row = token_row_from_curve(
        _state(real_sol="85.005359057", real_token="0", complete=True), params=PARAMS
    )
    assert row.rest_complete_seen_at == T0 and row.curve_filled_seen_at == T0
    assert row.completed_at == T0


def test_the_tracker_learns_the_denominator_the_row_learned() -> None:
    known = TrackedMint(mint="MINT", first_seen_at=T0, created_at=T0)
    tracked = tracked_from_curve(_state(real_sol="3", real_token="700000000"), known, PARAMS)
    assert tracked.initial_real_token_reserves == Decimal("793100000")
    assert tracked.complete is False and tracked.created_at == T0
