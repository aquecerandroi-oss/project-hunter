# pyright: reportPrivateUsage=false
"""T4.22 (EXP-M7, the slow-organic arm): the top-10 holders' share becomes a
criterion of the gate — a ceiling read from ``meme_features_1m.top10_share``
(a fraction), unknown refused by its own reason, off unless the set says so."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from hunter_indicators.meme.rules import EntryGate, evaluate_entry

from .test_meme_rules_flow import FLOW_GATE, _features

ORGANIC_GATE = replace(
    FLOW_GATE,
    key="organica_lenta",
    version=1,
    min_age_s=180,
    max_age_s=1800,
    min_progress_pct=Decimal(10),
    max_progress_pct=Decimal(30),
    max_top10_share=Decimal("0.30"),
    max_snipers=2,
)


def _organic_row(**overrides: object) -> object:
    base: dict[str, object] = {
        "age_s": 600,
        "progress_pct": Decimal(18),
        "top10_share": Decimal("0.25"),
        "top10_reason": None,
        "snipers": 1,
    }
    base.update(overrides)
    return _features(**base)


def test_the_flow_gate_never_asks_for_the_top_10_share() -> None:
    assert FLOW_GATE.max_top10_share is None
    assert "max_top10_share" not in FLOW_GATE.as_parameters()
    assert ORGANIC_GATE.as_parameters()["max_top10_share"] == "0.30"


def test_a_share_within_the_ceiling_passes_and_above_it_refuses_by_name() -> None:
    within = evaluate_entry(_organic_row(), ORGANIC_GATE)  # type: ignore[arg-type]
    assert "top10_above_max" not in within.refusals
    above = evaluate_entry(_organic_row(top10_share=Decimal("0.35")), ORGANIC_GATE)  # type: ignore[arg-type]
    assert "top10_above_max" in above.refusals
    edge = evaluate_entry(_organic_row(top10_share=Decimal("0.30")), ORGANIC_GATE)  # type: ignore[arg-type]
    assert "top10_above_max" not in edge.refusals, "the ceiling is inclusive"


def test_an_unknown_share_refuses_by_its_reason_never_as_a_zero() -> None:
    named = evaluate_entry(
        _organic_row(top10_share=None, top10_reason="no_holders_reader"),  # type: ignore[arg-type]
        ORGANIC_GATE,
    )
    assert "top10_no_holders_reader" in named.refusals
    bare = evaluate_entry(_organic_row(top10_share=None, top10_reason=None), ORGANIC_GATE)  # type: ignore[arg-type]
    assert "top10_unknown" in bare.refusals


def test_the_ceiling_is_a_fraction() -> None:
    with pytest.raises(ValueError, match="max_top10_share"):
        replace(ORGANIC_GATE, max_top10_share=Decimal("30"))
    assert isinstance(ORGANIC_GATE, EntryGate)
