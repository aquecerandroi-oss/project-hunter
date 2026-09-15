"""``hunter_indicators.meme.pedigree`` — EXP-M6's cross-cutting refusals:
the serial creator and the ticker clone, unknown refused by name, the
thresholds frozen at the study's numbers."""

from __future__ import annotations

import pytest

from hunter_indicators.meme.pedigree import (
    PEDIGREE_REFUSALS,
    PEDIGREE_V1,
    REPEAT_DUMPER_REFUSAL,
    PedigreeFeatures,
    PedigreeGate,
    evaluate_pedigree,
    evaluate_repeat_dumper,
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


# ---- T4.24 (EXP-M6, braço 2) — the repeat dumper, independent of PEDIGREE_V1 ----


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, ()),
        (1, (REPEAT_DUMPER_REFUSAL,)),
        (5, (REPEAT_DUMPER_REFUSAL,)),
        (None, ()),
    ],
)
def test_the_repeat_dumper_refuses_at_least_one_prior_dump_and_unknown_refuses_nothing(
    count: int | None, expected: tuple[str, ...]
) -> None:
    features = PedigreeFeatures(0, 0, creator_prior_dump_count=count)
    assert evaluate_repeat_dumper(features) == expected
    assert set(expected) <= PEDIGREE_REFUSALS


def test_the_dead_count_is_diagnostic_only_and_never_moves_the_verdict() -> None:
    alive = PedigreeFeatures(0, 0, creator_prior_dump_count=0, creator_prior_dead_count=3)
    dead = PedigreeFeatures(0, 0, creator_prior_dump_count=1, creator_prior_dead_count=0)
    assert evaluate_repeat_dumper(alive) == ()
    assert evaluate_repeat_dumper(dead) == (REPEAT_DUMPER_REFUSAL,)


def test_a_gate_refuses_nonsense_thresholds() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        PedigreeGate("x", 1, "d", max_creator_prior_mints_1h=-1, max_symbol_dup_24h=0)
    with pytest.raises(ValueError, match="starts at 1"):
        PedigreeGate("x", 0, "d", max_creator_prior_mints_1h=1, max_symbol_dup_24h=1)
    with pytest.raises(ValueError, match="at least one second"):
        PedigreeGate("x", 1, "d", 1, 1, creator_window_s=0)
