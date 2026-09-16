"""``hunter_indicators.meme.pedigree_e2b`` — E2-b (T4.31, EXP-M9): the curve
born full and the single wallet that paid a third of the rise, with the
buyers guard, the unknown refused by name and the thresholds frozen at the
numbers KB-0103/KB-0105 measured."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_indicators.meme.pedigree_e2b import (
    E2B_REFUSALS,
    E2B_UNKNOWN_REFUSAL,
    E2B_V1,
    E2bFeatures,
    E2bGate,
    evaluate_e2b,
)

pytestmark = pytest.mark.unit


def _features(
    share: str | None = None, buyers: int | None = None, fill_seconds: int | None = None
) -> E2bFeatures:
    return E2bFeatures(
        top_buyer_share=None if share is None else Decimal(share),
        buyers=buyers,
        fill_seconds=fill_seconds,
        tape_reason=None if share is not None else "no_tape",
    )


def test_the_frozen_gate_reads_the_measured_thresholds() -> None:
    assert (E2B_V1.key, E2B_V1.version) == ("pedigree_e2b", 1)
    assert E2B_V1.as_parameters() == {
        "e2b_top_buyer_share_max": "0.35",
        "e2b_min_buyers": "10",
        "e2b_born_full_s": "60",
    }
    assert "meme_trades.trader" in E2B_V1.inputs


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        # clean: a spread-out tape on a curve that took its time
        (_features("0.12", 40, 900), ()),
        # the concentration leg, at and above the bound (the measurement is ">= 0,35")
        (_features("0.35", 10, None), ("e2b_top_buyer_share",)),
        (_features("0.97", 21, None), ("e2b_top_buyer_share",)),
        (_features("0.3499999", 21, None), ()),
        # the guard: nine buyers say nothing, ten do
        (_features("0.90", 9, None), ()),
        (_features("0.90", 10, None), ("e2b_top_buyer_share",)),
        # born full — at the bound, and the same-block negative of KB-0103 §5
        (_features("0.05", 40, 60), ("e2b_born_full",)),
        (_features("0.05", 40, 61), ()),
        (_features("0.05", 40, -3), ("e2b_born_full",)),
        # both legs are counted, each by its own name
        (_features("0.80", 12, 12), ("e2b_born_full", "e2b_top_buyer_share")),
        # unknown refuses by name — with or without a fill stamp
        (_features(None, None, None), (E2B_UNKNOWN_REFUSAL,)),
        (_features(None, None, 10), ("e2b_born_full", E2B_UNKNOWN_REFUSAL)),
    ],
)
def test_every_refusal_is_named_and_the_unknown_share_refuses(
    features: E2bFeatures, expected: tuple[str, ...]
) -> None:
    refusals = evaluate_e2b(features, E2B_V1)
    assert refusals == expected
    assert set(refusals) <= E2B_REFUSALS


def test_a_coin_that_never_filled_is_not_born_full() -> None:
    """``fill_seconds is None`` = the completion was not observed at or before
    the judged instant; reading a later ``completed_at`` would be look-ahead."""
    assert evaluate_e2b(_features("0.10", 30, None), E2B_V1) == ()


def test_the_guard_is_a_parameter_not_a_constant() -> None:
    loose = E2bGate(
        key="pedigree_e2b",
        version=2,
        description="a variant of KB-0105 §3: <= 30 s or >= 45 %, guard of 5 buyers",
        top_buyer_share_max=Decimal("0.45"),
        min_buyers=5,
        born_full_s=30,
    )
    assert evaluate_e2b(_features("0.40", 12, 45), loose) == ()
    assert evaluate_e2b(_features("0.40", 12, 45), E2B_V1) == (
        "e2b_born_full",
        "e2b_top_buyer_share",
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"version": 0},
        {"top_buyer_share_max": Decimal("0")},
        {"top_buyer_share_max": Decimal("1.5")},
        {"min_buyers": 0},
        {"born_full_s": 0},
    ],
)
def test_an_illegal_gate_refuses_to_exist(kwargs: dict[str, object]) -> None:
    base = {
        "key": "pedigree_e2b",
        "version": 1,
        "description": "d",
        "top_buyer_share_max": Decimal("0.35"),
        "min_buyers": 10,
        "born_full_s": 60,
    }
    with pytest.raises(ValueError, match=r".+"):
        E2bGate(**{**base, **kwargs})  # type: ignore[arg-type]
