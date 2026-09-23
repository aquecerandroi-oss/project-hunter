"""T4.80 — the optional ``max_buys_1m`` ceiling of the entry gate (R65 §Q2/§6,
KB-0147): a launch whose last 60 s carried more buys than the desk allows is
refused by name. **Absent = not a criterion**, so every set frozen before
today reads exactly as it did; an unmeasured count refuses (fail closed), it
is never read as "nobody bought"."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.rules import EntryFeatures, EntryGate, evaluate_entry

pytestmark = pytest.mark.unit


def _gate(**overrides: Any) -> EntryGate:
    base: dict[str, Any] = {
        "key": "fluxo_e_holders",
        "version": 1,
        "description": "T4.80",
        "min_age_s": 30,
        "max_age_s": 300,
        "min_progress_pct": Decimal(5),
        "max_progress_pct": Decimal(100),
        "max_participation_pct": Decimal(1),
    }
    base.update(overrides)
    return EntryGate(**base)


def _features(**overrides: Any) -> EntryFeatures:
    base: dict[str, Any] = {
        "mint": "MINT",
        "age_s": 120,
        "progress_pct": Decimal(12),
        "creator_net_seller": False,
        "curve_volume_1m_sol": Decimal(20),
        "intended_size_sol": Decimal("0.05"),
        "buys_1m": 12,
        "sells_1m": 6,
        "is_mayhem": False,
    }
    base.update(overrides)
    return EntryFeatures(**base)


def test_absent_is_not_a_criterion_whatever_the_count_says() -> None:
    off = _gate()
    assert off.max_buys_1m is None
    for buys in (0, 25, 26, 10_000, None):
        decision = evaluate_entry(_features(buys_1m=buys), off)
        assert decision.allowed, f"buys_1m={buys} must not be judged by a gate that does not ask"


def test_a_count_at_or_below_the_ceiling_passes() -> None:
    gate = _gate(max_buys_1m=25)
    assert evaluate_entry(_features(buys_1m=25), gate).allowed, "the ceiling itself is allowed"
    assert evaluate_entry(_features(buys_1m=0), gate).allowed


def test_a_count_above_the_ceiling_refuses_by_name() -> None:
    decision = evaluate_entry(_features(buys_1m=26), _gate(max_buys_1m=25))
    assert decision.refusals == ("buys_1m_above_max",)


def test_an_unmeasured_count_refuses_fail_closed() -> None:
    blind = _features(buys_1m=None, tape_reason="no_trade_feed")
    decision = evaluate_entry(blind, _gate(max_buys_1m=25))
    assert decision.refusals == ("buys_1m_unknown",)


def test_the_parameters_list_the_ceiling_only_when_the_gate_asks_it() -> None:
    assert "max_buys_1m" not in _gate().as_parameters()
    assert _gate(max_buys_1m=25).as_parameters()["max_buys_1m"] == "25"


def test_a_negative_ceiling_is_refused_by_name() -> None:
    """A count cannot be negative. The *type* guard (a decimal, a string) lives
    where JSON enters the system — ``hunter_meme_worker.lab_params
    .optional_count``, exercised in ``services/meme-worker/tests/
    test_gate_buys_1m.py`` and ``infra/scripts/tests/``."""
    with pytest.raises(ValueError, match="max_buys_1m cannot be negative"):
        _gate(max_buys_1m=-1)
