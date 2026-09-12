"""T4.11 — the moonshot parameters through the Lab's shapes: a rule set that
holds through the migration, the trailing armed at 3×, the ``dead`` exit, the
operator's 7 200 s hold that the loop must not truncate, and the frozen sets
reading byte for byte as they did.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.rules import ExitState, evaluate_exit
from hunter_meme_worker.lab_bets_pool import holds_through_migration
from hunter_meme_worker.lab_models import EffectiveParams, RuleSetSpec, effective_params
from hunter_meme_worker.lab_rows import OpenBet

from .test_paper_engine import PARAMS as V0_PARAMS
from .test_paper_engine import _bet  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)

MOONSHOT_PARAMS: dict[str, Any] = {
    "gate_key": "sonda_de_hype",
    "gate_version": 1,
    "exit_key": "alvo_10x_trailing_50_apos_3x_tempo_2h",
    "exit_version": 1,
    "min_age_s": 30,
    "max_age_s": 300,
    "min_progress_pct": "0",
    "max_progress_pct": "100",
    "require_progress": False,
    "max_participation_pct": "1",
    "require_creator_not_net_seller": True,
    "min_hype_score": "0.6",
    "max_dev_share": "0.10",
    "dev_share_unknown_allowed": True,
    "max_snipers": 2,
    "size_sol": "0.02",
    "target_x": "10",
    "trailing_pct": "50",
    "trailing_arm_x": "3",
    "max_hold_s": 7200,
    "max_loss_pct": "100",
    "exit_on_migration": False,
    "exit_on_dead": True,
    "dead_stale_s": 900,
    "dead_mark_pct": "50",
    "wallet_max_sol": "2.0",
    "max_sol_per_bet": "0.02",
    "daily_loss_cap_sol": "0.20",
    "max_open_positions": 8,
    "max_exposure_per_mint_sol": "0.02",
    "fee_pct": "1.75",
    "priority_fee_sol": "0",
}


def _spec(params: dict[str, Any], **identity: Any) -> RuleSetSpec:
    base: dict[str, Any] = {
        "id": "01994d00-6c1a-7000-8000-000000000005",
        "name": "moonshot_v0",
        "version": "1",
        "kind": "research_only",
        "exp_ref": "EXP-M4",
        "status": "active",
        "code_ref": "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
    }
    return RuleSetSpec.from_params(**{**base, **identity}, params=params)


def test_the_moonshot_set_parses_and_suggests_its_switches() -> None:
    spec = _spec(MOONSHOT_PARAMS)
    assert spec.exit_on_migration is False and spec.trailing_arm_x == Decimal(3)
    assert spec.exit_on_dead and (spec.dead_stale_s, spec.dead_mark_pct) == (900, Decimal(50))
    assert spec.gate.min_hype_score == Decimal("0.6") and spec.gate.max_snipers == 2
    assert spec.suggested() == {
        "size_sol": "0.02",
        "target_x": "10",
        "trailing_pct": "50",
        "max_hold_s": 7200,
        "exit_on_migration": False,
        "trailing_arm_x": "3",
        "exit_on_dead": True,
    }
    assert not spec.scales


def test_the_frozen_set_suggests_exactly_the_four_keys_it_always_had() -> None:
    spec = _spec(V0_PARAMS, name="meme_paper_v0", exp_ref="EXP-M1")
    assert spec.exit_on_migration is True and spec.trailing_arm_x is None and not spec.exit_on_dead
    assert spec.suggested() == {
        "size_sol": "0.05",
        "target_x": "2",
        "trailing_pct": "30",
        "max_hold_s": 900,
    }
    params = effective_params(spec, {})
    assert not isinstance(params, str)
    assert params.as_json() == {
        "size_sol": "0.05",
        "target_x": "2",
        "trailing_pct": "30",
        "max_hold_s": 900,
        "max_loss_pct": "50",
        "exit_on_line_break": False,
        "line_break_snapshots": 2,
    }, "a bet of a frozen set writes the params it always wrote"
    rules = params.exit_rules()
    assert rules.exit_on_migration and rules.exit_on_curve_complete and not rules.exit_on_dead


def test_the_effective_params_carry_the_switches_and_round_trip() -> None:
    spec = _spec(MOONSHOT_PARAMS)
    params = effective_params(spec, dict(spec.suggested()))
    assert not isinstance(params, str)
    assert params.as_json() == {
        "size_sol": "0.02",
        "target_x": "10",
        "trailing_pct": "50",
        "max_hold_s": 7200,
        "max_loss_pct": "100",
        "exit_on_line_break": False,
        "line_break_snapshots": 2,
        "exit_on_migration": False,
        "trailing_arm_x": "3",
        "exit_on_dead": True,
        "dead_stale_s": 900,
        "dead_mark_pct": "50",
    }
    assert EffectiveParams.from_json(params.as_json()) == params
    rules = params.exit_rules()
    assert not rules.exit_on_migration and not rules.exit_on_curve_complete
    assert rules.trailing_arm_multiple == Decimal(3) and rules.exit_on_dead
    assert effective_params(spec, {"size_sol": "0.03"}) == "exceeds_max_sol_per_bet"


def test_the_operator_may_ask_for_two_hours_and_the_time_stop_honours_them() -> None:
    """operator/2's suggested defaults, approved as they are: ``max_hold_s`` 7 200
    is a number the loop keeps whole — the stop fires at 7 200 s, not before."""
    operator = _spec(
        {**MOONSHOT_PARAMS, "size_sol": "0.05", "max_sol_per_bet": "0.05"},
        name="operator",
        version="2",
        kind="operator",
        exp_ref=None,
    )
    decision = {"size_sol": "0.05", "target_x": "10", "trailing_pct": "50", "max_hold_s": 7200}
    params = effective_params(operator, decision)
    assert not isinstance(params, str)
    assert params.max_hold_s == 7200 and params.exit_on_migration is False
    rules = params.exit_rules()
    state = ExitState(
        mark_sol=Decimal("0.05"),
        cost_basis_sol=Decimal("0.05"),
        peak_mark_sol=Decimal("0.05"),
        held_s=7199,
        migrated=True,
        curve_complete=True,
        rug_suspected=False,
        creator_net_seller=False,
        mark_stale_s=0,
    )
    assert evaluate_exit(state, rules).should_exit is False, "migrated, complete: still held"
    assert evaluate_exit(replace(state, held_s=7200), rules).reason == "time_stop"
    # The operator may also hand the sheet's own numbers back over the suggested ones.
    edited = effective_params(operator, {**decision, "max_hold_s": 10800, "trailing_pct": "40"})
    assert not isinstance(edited, str)
    assert (edited.max_hold_s, edited.trailing_pct) == (10800, Decimal(40))


def test_the_pool_path_applies_only_to_a_migrated_bet_of_a_holding_set() -> None:
    frozen = _bet()
    moon = _bet(
        params=EffectiveParams.from_json({**frozen.params.as_json(), "exit_on_migration": False})
    )
    assert not holds_through_migration(OpenBet(frozen, None, None, None))
    assert not holds_through_migration(OpenBet(frozen, T0, T0, None)), "the frozen set sells on it"
    assert not holds_through_migration(OpenBet(moon, None, None, None)), "not migrated yet"
    assert holds_through_migration(OpenBet(moon, T0, T0, None))
