"""T4.98 (EXP-M26 L1) — the two parameters of the support the ``line_broken``
exit reads: ``line_support_causal`` (only a minute folded by the photo, default
``true``) and ``line_support_max_age_s`` (the line's minute closed at most this
long before the photo, default 120). Defaults are the fix for every set; EXP-M26
writes them explicitly; a bet opened before this change reads the defaults.
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_meme_worker.lab_models import EffectiveParams, RuleSetSpec, effective_params

from .test_paper_engine import PARAMS as V0_PARAMS

pytestmark = pytest.mark.unit

LINE_PARAMS: dict[str, Any] = {**V0_PARAMS, "exit_on_line_break": True, "line_break_snapshots": 2}


def _spec(params: dict[str, Any]) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id="01994d00-6c1a-7000-8000-000000000098",
        name="linha_v0",
        version="1",
        kind="research_only",
        exp_ref="EXP-M26",
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params=params,
    )


def _effective(params: dict[str, Any]) -> EffectiveParams:
    effective = effective_params(_spec(params), {})
    assert not isinstance(effective, str)
    return effective


def test_a_set_that_names_neither_key_gets_the_causal_120_s_support() -> None:
    spec = _spec(LINE_PARAMS)
    assert (spec.line_support_causal, spec.line_support_max_age_s) == (True, 120)
    params = _effective(LINE_PARAMS)
    assert (params.line_support_causal, params.line_support_max_age_s) == (True, 120)


def test_a_bet_that_watches_the_line_records_the_support_it_ran_on() -> None:
    params = _effective(LINE_PARAMS)
    written = params.as_json()
    assert written["line_support_causal"] is True
    assert written["line_support_max_age_s"] == 120
    assert EffectiveParams.from_json(written) == params


def test_a_bet_that_does_not_watch_the_line_writes_the_params_it_always_wrote() -> None:
    assert "line_support_causal" not in _effective(V0_PARAMS).as_json()


def test_a_bet_opened_before_the_fix_reads_the_defaults() -> None:
    legacy = {k: v for k, v in _effective(LINE_PARAMS).as_json().items() if "support" not in k}
    params = EffectiveParams.from_json(legacy)
    assert (params.line_support_causal, params.line_support_max_age_s) == (True, 120)


def test_the_experiment_writes_both_keys_explicitly_and_the_bet_carries_them() -> None:
    explicit = {**LINE_PARAMS, "line_support_causal": False, "line_support_max_age_s": 180}
    params = _effective(explicit)
    assert (params.line_support_causal, params.line_support_max_age_s) == (False, 180)
    assert EffectiveParams.from_json(params.as_json()) == params


@pytest.mark.parametrize("bad", [0, -1, "120", True, 120.0])
def test_the_bound_is_a_positive_bare_integer(bad: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        _spec({**LINE_PARAMS, "line_support_max_age_s": bad})
