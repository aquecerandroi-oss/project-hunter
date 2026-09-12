"""T4.10 — the probe → scale step: a second leg is proposed **only** while the
probe is open, only once per probe, and only when the line set's gate is
satisfied for the same mint at the scale size.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from hunter_meme_worker.lab_models import RuleSetSpec, effective_params
from hunter_meme_worker.paper_fill import evaluate_fill
from hunter_meme_worker.proposals import GateRow, evaluate_gate
from hunter_meme_worker.proposals_scale import evaluate_scale

from .test_paper_engine import PARAMS
from .test_proposals import MINT, _row, _snapshot  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 12, 12, 1, 30, tzinfo=UTC)
PROBE_ID = "01994d00-6c1a-7000-8000-0000000000aa"
HYPE_ID = "01994d00-6c1a-7000-8000-000000000004"
TREND_ID = "01994d00-6c1a-7000-8000-000000000003"

TREND_PARAMS: dict[str, Any] = {
    **PARAMS,
    "gate_key": "a_linha_manda",
    "min_age_s": 300,
    "require_higher_lows": True,
    "require_breakout_15m": True,
    "min_distance_to_support_pct": "0",
    "max_distance_to_support_pct": "0.25",
    "exit_on_line_break": True,
    "line_break_snapshots": 2,
}
HYPE_PARAMS: dict[str, Any] = {
    **PARAMS,
    "gate_key": "sonda_de_hype",
    "min_age_s": 30,
    "max_age_s": 300,
    "require_progress": False,
    "min_hype_score": "0.6",
    "max_dev_share": "0.10",
    "dev_share_unknown_allowed": True,
    "max_snipers": 2,
    "size_sol": "0.01",
    "target_x": "3",
    "trailing_pct": "40",
    "max_hold_s": 600,
    "max_sol_per_bet": "0.04",
    "max_open_positions": 5,
    "max_exposure_per_mint_sol": "0.05",
    "scale_size_sol": "0.04",
    "scale_gate": "trendline_v0/1",
}


def _spec(name: str, params: dict[str, Any], rule_set_id: str) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id=rule_set_id,
        name=name,
        version="1",
        kind="research_only",
        exp_ref="EXP-M3" if name == "hype_probe_v0" else "EXP-M2",
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params=params,
    )


HYPE = _spec("hype_probe_v0", HYPE_PARAMS, HYPE_ID)
TREND = _spec("trendline_v0", TREND_PARAMS, TREND_ID)


def _lined_row(**overrides: Any) -> GateRow:
    """A row six minutes old whose line confirms — the trendline gate's yes."""
    base: dict[str, Any] = {
        "created_at": _row().end_time - timedelta(seconds=360),
        "creator_sold": False,
        "curve_volume_1m_sol": Decimal(10),
        "higher_lows": True,
        "breakout_15m": True,
        "distance_to_support_pct": Decimal("0.1"),
        "hype_score": Decimal("0.7"),
        "dev_share": Decimal("0.05"),
        "snipers": 1,
    }
    base.update(overrides)
    return _row(**base)


def test_the_seeded_parameters_parse_into_the_two_gates() -> None:
    assert HYPE.scales and HYPE.scale_gate == "trendline_v0/1" and HYPE.label == "hype_probe_v0/1"
    assert HYPE.gate.min_hype_score == Decimal("0.6") and HYPE.gate.require_progress is False
    assert TREND.gate.require_higher_lows and TREND.exit_on_line_break
    assert not TREND.scales
    assert HYPE.suggested()["leg"] == "probe" and "leg" not in TREND.suggested()
    assert TREND.suggested()["exit_on_line_break"] is True


def test_no_open_probe_means_no_scale_whatever_the_line_says() -> None:
    outcome = evaluate_scale(
        HYPE, TREND, [_lined_row()], open_probes={}, already_scaled=frozenset(), now=NOW, ttl_s=120
    )
    assert outcome.drafts == [] and outcome.evaluated == 0 and outcome.refusals == {}


def test_an_open_probe_scales_once_when_the_line_confirms() -> None:
    probes = {MINT: PROBE_ID}
    outcome = evaluate_scale(
        HYPE,
        TREND,
        [_lined_row()],
        open_probes=probes,
        already_scaled=frozenset(),
        now=NOW,
        ttl_s=120,
    )
    (draft,) = outcome.drafts
    assert draft.rule_set_id == HYPE_ID and draft.status == "approved"
    assert draft.suggested["leg"] == "scale" and draft.suggested["parent_bet_id"] == PROBE_ID
    assert draft.suggested["size_sol"] == "0.04"
    assert draft.suggested["target_x"] == "2" and draft.suggested["max_hold_s"] == 900
    assert draft.suggested["exit_on_line_break"] is True
    assert draft.decision == draft.suggested
    assert draft.quote["size_sol"] == "0.04"
    assert draft.reasons[0] == {"rule": "a_linha_manda/1", "scale_of": PROBE_ID}
    assert draft.reasons[1] == {"scale_gate": "trendline_v0/1", "probe_rule_set": "hype_probe_v0/1"}
    assert any(r.get("feature") == "line" for r in draft.reasons)
    again = evaluate_scale(
        HYPE,
        TREND,
        [_lined_row()],
        open_probes=probes,
        already_scaled=frozenset({PROBE_ID}),
        now=NOW,
        ttl_s=120,
    )
    assert again.drafts == [] and again.evaluated == 0, "a probe scales once"


def test_the_line_gate_must_be_satisfied_and_its_refusals_are_prefixed() -> None:
    probes = {MINT: PROBE_ID}
    not_yet = _lined_row(
        higher_lows=None, distance_to_support_pct=None, line_reason="too_few_points"
    )
    outcome = evaluate_scale(
        HYPE, TREND, [not_yet], open_probes=probes, already_scaled=frozenset(), now=NOW, ttl_s=120
    )
    assert outcome.drafts == [] and outcome.refusals == {"scale:line_too_few_points": 1}
    lower = _lined_row(higher_lows=False)
    outcome = evaluate_scale(
        HYPE, TREND, [lower], open_probes=probes, already_scaled=frozenset(), now=NOW, ttl_s=120
    )
    assert outcome.refusals == {"scale:no_higher_lows": 1}
    young = _lined_row(created_at=_row().end_time - timedelta(seconds=120))
    outcome = evaluate_scale(
        HYPE, TREND, [young], open_probes=probes, already_scaled=frozenset(), now=NOW, ttl_s=120
    )
    assert outcome.refusals == {"scale:age_below_min": 1}, "a line needs five minutes"


def test_the_second_leg_is_judged_with_its_own_size() -> None:
    thin = _lined_row(curve_volume_1m_sol=Decimal("2"))  # 0.04 / 2 = 2 % > 1 %; 0.01 would pass
    outcome = evaluate_scale(
        HYPE,
        TREND,
        [thin],
        open_probes={MINT: PROBE_ID},
        already_scaled=frozenset(),
        now=NOW,
        ttl_s=120,
    )
    assert outcome.refusals == {"scale:participation_above_cap": 1}


def test_the_probe_gate_opens_probes_and_refuses_the_mint_it_already_holds() -> None:
    young = _lined_row(created_at=_row().end_time - timedelta(seconds=90), curve_progress_pct=None)
    outcome = evaluate_gate(HYPE, [young], now=NOW, ttl_s=120, already_open=frozenset())
    (draft,) = outcome.drafts
    assert draft.suggested["leg"] == "probe" and draft.suggested["size_sol"] == "0.01"
    held = evaluate_gate(HYPE, [young], now=NOW, ttl_s=120, already_open=frozenset({MINT}))
    assert held.drafts == [] and held.refusals == {"already_open": 1}


def test_a_scale_decision_fills_as_a_scale_leg_and_a_scale_without_parent_is_refused() -> None:
    from hunter_meme_worker.lab_models import WalletState

    wallet = WalletState(
        balance_sol=Decimal("1.9"),
        open_positions=5,
        realized_today_sol=Decimal(0),
        exposure_by_mint={MINT: Decimal("0.01")},
    )
    decision = {"size_sol": "0.04", "leg": "scale", "parent_bet_id": PROBE_ID}
    verdict = evaluate_fill(
        HYPE,
        decision,
        wallet,
        _snapshot(120),
        decided_at=NOW,
        now=NOW + timedelta(seconds=40),
        migrated=False,
        fill_window_s=180,
        sol_usd=None,
    )
    assert verdict.kind == "filled" and verdict.entry is not None
    assert verdict.entry.leg == "scale" and verdict.entry.parent_bet_id == PROBE_ID
    assert verdict.entry.entry["leg"] == "scale"
    assert verdict.entry.sol_spent == Decimal("0.04"), (
        "five probes open: the second leg rides on its slot"
    )
    orphan = evaluate_fill(
        HYPE,
        {"size_sol": "0.04", "leg": "scale"},
        wallet,
        _snapshot(120),
        decided_at=NOW,
        now=NOW + timedelta(seconds=40),
        migrated=False,
        fill_window_s=180,
        sol_usd=None,
    )
    assert orphan.kind == "refused" and orphan.refusal == "scale_without_parent"
    probe = evaluate_fill(
        HYPE,
        {"size_sol": "0.01", "leg": "probe"},
        wallet,
        _snapshot(120),
        decided_at=NOW,
        now=NOW + timedelta(seconds=40),
        migrated=False,
        fill_window_s=180,
        sol_usd=None,
    )
    assert probe.kind == "refused" and probe.refusal == "max_open_positions", "the sixth probe"
    params = effective_params(HYPE, decision)
    assert not isinstance(params, str) and params.exit_on_line_break is False
    watched = effective_params(HYPE, {**decision, "exit_on_line_break": True})
    assert not isinstance(watched, str) and watched.exit_rules().exit_on_line_break is True
