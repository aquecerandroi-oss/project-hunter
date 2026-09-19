"""``hunter_indicators.meme.launch_lane`` — EXP-M18's launch lane gate: the
four criteria a ``create`` frame alone can answer, unknown refused by name."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from hunter_indicators.meme.curve import INITIAL_REAL_TOKEN_RESERVES, INITIAL_VIRTUAL_TOKEN_RESERVES
from hunter_indicators.meme.launch_lane import (
    LAUNCH_LANE_REFUSALS,
    LaunchFeatures,
    LaunchGate,
    evaluate_launch,
    initial_real_token_reserves_is_sane,
    reconstruct_initial_real_token_reserves,
)

pytestmark = pytest.mark.unit

GATE = LaunchGate(key="pista_de_lancamento", version=1, max_creator_initial_sol=Decimal(2))

CLEAN = LaunchFeatures(
    is_mayhem=False,
    creator_initial_sol=Decimal("0.5"),
    initial_real_token_reserves=INITIAL_REAL_TOKEN_RESERVES,
    symbol_clone_recent=False,
)


def test_gate_rejects_non_positive_ceilings() -> None:
    with pytest.raises(ValueError, match="max_creator_initial_sol"):
        LaunchGate(key="k", version=1, max_creator_initial_sol=Decimal(0))
    with pytest.raises(ValueError, match="version"):
        LaunchGate(key="k", version=0, max_creator_initial_sol=Decimal(1))


def test_a_clean_create_refuses_nothing() -> None:
    assert evaluate_launch(CLEAN, GATE) == ()


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        (replace(CLEAN, is_mayhem=True), ("mayhem",)),
        (replace(CLEAN, is_mayhem=None), ("mayhem_unknown",)),
        (
            replace(CLEAN, creator_initial_sol=Decimal("2.01")),
            ("creator_initial_sol_too_high",),
        ),
        (
            replace(CLEAN, creator_initial_sol=Decimal(2)),
            (),
        ),
        (
            replace(CLEAN, creator_initial_sol=None),
            ("creator_initial_sol_unknown",),
        ),
        (
            replace(CLEAN, initial_real_token_reserves=None),
            ("initial_real_token_reserves_unknown",),
        ),
        (
            replace(CLEAN, initial_real_token_reserves=Decimal(1)),
            ("initial_real_token_reserves_insane",),
        ),
        (replace(CLEAN, symbol_clone_recent=True), ("symbol_clone_recent",)),
    ],
)
def test_each_criterion_refuses_by_name(
    features: LaunchFeatures, expected: tuple[str, ...]
) -> None:
    assert evaluate_launch(features, GATE) == expected
    assert set(expected) <= LAUNCH_LANE_REFUSALS


def test_every_criterion_stacks() -> None:
    dirty = LaunchFeatures(
        is_mayhem=True,
        creator_initial_sol=Decimal(5),
        initial_real_token_reserves=None,
        symbol_clone_recent=True,
    )
    assert evaluate_launch(dirty, GATE) == (
        "mayhem",
        "creator_initial_sol_too_high",
        "initial_real_token_reserves_unknown",
        "symbol_clone_recent",
    )


def test_reconstruction_of_a_standard_curve_is_exact() -> None:
    """A dev that bought nothing: the frame's virtual reserve is still the
    genesis one (``INITIAL_VIRTUAL_TOKEN_RESERVES``), and the real side
    reconciles to the program's own constant."""
    value = reconstruct_initial_real_token_reserves(INITIAL_VIRTUAL_TOKEN_RESERVES, Decimal(0))
    assert value == INITIAL_REAL_TOKEN_RESERVES


def test_reconstruction_of_a_dev_buy_still_reconciles() -> None:
    """T4.45's own live-verified identity: ``initial_virtual - initialBuy ==
    vTokensInBondingCurve`` — worked backwards, a dev buy of any size still
    reconstructs the same launch denominator."""
    bought = Decimal(1_000_000)
    after_buy_virtual = INITIAL_VIRTUAL_TOKEN_RESERVES - bought
    value = reconstruct_initial_real_token_reserves(after_buy_virtual, bought)
    assert value == INITIAL_REAL_TOKEN_RESERVES


def test_reconstruction_is_none_without_the_creators_own_buy_observed() -> None:
    assert reconstruct_initial_real_token_reserves(INITIAL_VIRTUAL_TOKEN_RESERVES, None) is None


def test_sanity_tolerates_a_percent_and_no_more() -> None:
    within = INITIAL_REAL_TOKEN_RESERVES * Decimal("1.005")
    outside = INITIAL_REAL_TOKEN_RESERVES * Decimal("1.02")
    assert initial_real_token_reserves_is_sane(within, GATE) is True
    assert initial_real_token_reserves_is_sane(outside, GATE) is False
    assert initial_real_token_reserves_is_sane(None, GATE) is False
