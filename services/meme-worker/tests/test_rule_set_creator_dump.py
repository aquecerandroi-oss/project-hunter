"""H-031b (EXP-M27) — ``exit_on_creator_dump`` read from the rule set and carried
to the bet: ``RuleSetSpec.from_params`` → ``effective_params`` → ``as_json`` /
``exit_rules``. Until H-031b no rule set could turn the exit off (``from_params``
never read the key); the twin ``absorb_semdump_v0/1`` is the first that does.
The bet side (recorded on every bet, honoured by ``evaluate_exit``) is
``test_lab_params_creator_dump.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_indicators.meme.exits import ExitState, evaluate_exit
from hunter_meme_worker.lab_models import EffectiveParams, RuleSetSpec, effective_params

pytestmark = pytest.mark.unit

BASE: dict[str, Any] = {
    "gate_key": "comprar_cedo_na_curva", "gate_version": 1,
    "exit_key": "alvo_2x_trailing_30_tempo_15m", "exit_version": 1,
    "min_age_s": 30, "max_age_s": 600, "min_progress_pct": "2", "max_progress_pct": "50",
    "max_participation_pct": "1", "require_creator_not_net_seller": True,
    "size_sol": "0.05", "target_x": "2", "trailing_pct": "30", "max_hold_s": 900,
    "max_loss_pct": "50", "wallet_max_sol": "2.0", "max_sol_per_bet": "0.05",
    "daily_loss_cap_sol": "0.20", "max_open_positions": 3,
    "max_exposure_per_mint_sol": "0.05", "fee_pct": "1.75", "priority_fee_sol": "0",
}  # fmt: skip
"""``test_paper_engine.PARAMS`` (the ``0022`` document), copied by hand."""
TWIN: dict[str, Any] = {**BASE, "exit_on_creator_dump": False}


def _spec(params: dict[str, Any]) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id="01994d00-6c1a-7000-8000-000000000097",
        name="absorb_semdump_v0",
        version="1",
        kind="research_only",
        exp_ref="EXP-M27",
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params=params,
    )


def _effective(params: dict[str, Any], decision: dict[str, Any] | None = None) -> EffectiveParams:
    effective = effective_params(_spec(params), decision or {})
    assert not isinstance(effective, str)
    return effective


def test_a_set_that_does_not_name_the_switch_keeps_the_exit() -> None:
    assert _spec(BASE).exit_on_creator_dump is True
    effective = _effective(BASE)
    assert effective.exit_on_creator_dump is True
    assert effective.as_json()["exit_on_creator_dump"] is True


def test_the_twin_reaches_the_bet_and_the_exit() -> None:
    assert _spec(TWIN).exit_on_creator_dump is False
    effective = _effective(TWIN)
    assert effective.as_json()["exit_on_creator_dump"] is False
    assert EffectiveParams.from_json(effective.as_json()) == effective
    state = ExitState(
        mark_sol=effective.size_sol,
        cost_basis_sol=effective.size_sol,
        peak_mark_sol=effective.size_sol,
        held_s=10,
        rug_suspected=False,
        creator_net_seller=True,
    )
    assert evaluate_exit(state, _effective(BASE).exit_rules()).reason == "creator_dump"
    assert evaluate_exit(state, effective.exit_rules()).reason is None


def test_the_decision_cannot_turn_the_rule_sets_switch() -> None:
    """The set's word, like the loss floor — never the operator's per bet."""
    assert _effective(BASE, {"exit_on_creator_dump": False}).exit_on_creator_dump is True
    assert _effective(TWIN, {"exit_on_creator_dump": True}).exit_on_creator_dump is False


@pytest.mark.parametrize("bad", ["false", "true", 0, 1, "0", None])
def test_the_switch_is_a_bare_json_boolean(bad: Any) -> None:
    """``bool("false")`` is ``True`` and ``null`` would silently mean the default: refused
    at load (and by ``meme_rule_set.py --set-param``'s validator, which loads the same way)."""
    with pytest.raises(TypeError):
        _spec({**BASE, "exit_on_creator_dump": bad})
