"""``hunter_indicators.meme.pedigree`` — EXP-M6's cross-cutting refusals:
the serial creator and the ticker clone, unknown refused by name, the
thresholds frozen at the study's numbers."""

from __future__ import annotations

import pytest

from hunter_indicators.meme.pedigree import (
    PEDIGREE_REFUSALS,
    PEDIGREE_V1,
    PedigreeFeatures,
    PedigreeGate,
    evaluate_pedigree,
)

pytestmark = pytest.mark.unit


def test_the_frozen_gate_reads_the_study_thresholds() -> None:
    assert (PEDIGREE_V1.key, PEDIGREE_V1.version) == ("exclusoes_de_pedigree", 1)
    assert PEDIGREE_V1.as_parameters() == {
        "max_creator_prior_mints_1h": "1",
        "max_symbol_dup_24h": "2",
        "creator_window_s": "3600",
        "symbol_window_s": "86400",
    }


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        (PedigreeFeatures(0, 0), ()),
        (PedigreeFeatures(1, 2), ()),
        (PedigreeFeatures(2, 0), ("creator_serial",)),
        (PedigreeFeatures(0, 3), ("symbol_clone",)),
        (PedigreeFeatures(5, 9), ("creator_serial", "symbol_clone")),
        (PedigreeFeatures(None, 0), ("creator_unknown",)),
        (PedigreeFeatures(0, None), ("symbol_unknown",)),
        (PedigreeFeatures(None, None), ("creator_unknown", "symbol_unknown")),
    ],
)
def test_every_refusal_is_named_and_unknown_refuses(
    features: PedigreeFeatures, expected: tuple[str, ...]
) -> None:
    refusals = evaluate_pedigree(features, PEDIGREE_V1)
    assert refusals == expected
    assert set(refusals) <= PEDIGREE_REFUSALS


def test_a_gate_refuses_nonsense_thresholds() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        PedigreeGate("x", 1, "d", max_creator_prior_mints_1h=-1, max_symbol_dup_24h=0)
    with pytest.raises(ValueError, match="starts at 1"):
        PedigreeGate("x", 0, "d", max_creator_prior_mints_1h=1, max_symbol_dup_24h=1)
    with pytest.raises(ValueError, match="at least one second"):
        PedigreeGate("x", 1, "d", 1, 1, creator_window_s=0)
