# pyright: reportPrivateUsage=false
"""T4.16 — the gate step with the flow set (EXP-M5) and the pedigree
exclusions (EXP-M6): a 15-second row that passes becomes a research proposal
whose ``reasons`` name the series, the flow block and the pedigree block; a
serial creator or a ticker clone is refused **before** the set's own gate; a
mint the pedigree read did not cover is ``pedigree_unknown``; a set that opts
out is judged without it; and EXP-M1's frozen ``reasons`` do not change."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.pedigree import PedigreeFeatures
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.proposals import SERIES_15S, evaluate_gate

from .test_paper_engine import PARAMS
from .test_proposals import MINT, NOW, T0, _row, _spec

pytestmark = pytest.mark.unit

FLOW_PARAMS: dict[str, Any] = {
    **PARAMS,
    "gate_key": "fluxo_e_holders",
    "clock": "15s",
    "min_age_s": 30,
    "max_age_s": 300,
    "min_progress_pct": "5",
    "max_progress_pct": "100",
    "require_progress_rising": True,
    "require_positive_flow": True,
    "min_unique_buyers": 10,
    "max_sells_to_buys": "0.6",
    "require_holders_rising": True,
    "max_snipers": 2,
    "max_dev_share": "0.10",
    "target_x": "3",
    "trailing_pct": "35",
    "trailing_arm_x": "1.5",
    "max_hold_s": 1800,
    "exit_on_line_break": True,
}
CLEAN = PedigreeFeatures(creator_prior_mints_1h=0, symbol_dup_24h=1)


def _flow_spec(**overrides: Any) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id="01994d00-6c1a-7000-8000-000000000008",
        name="flow_v2",
        version="1",
        kind="research_only",
        exp_ref="EXP-M5",
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params={**FLOW_PARAMS, **overrides},
    )


def _fast_row(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "end_time": T0,
        "created_at": T0 - timedelta(seconds=120),
        "creator_sold": False,
        "curve_volume_1m_sol": Decimal("20"),
        "curve_progress_pct": Decimal("0.12"),
        "net_sol_flow_1m": Decimal("0.9"),
        "mcap_delta_60s": Decimal("6"),
        "buys_1m": 12,
        "sells_1m": 6,
        "unique_buyers_1m": 12,
        "holders_rising": True,
        "progress_rising": True,
        "dev_share": Decimal("0.05"),
        "dev_share_reason": None,
        "snipers": 1,
        "series": SERIES_15S,
    }
    base.update(overrides)
    return _row(**base)


def test_the_flow_set_parses_its_clock_and_its_pedigree_switch() -> None:
    spec = _flow_spec()
    assert spec.clock == "15s" and spec.pedigree_exclusions is True
    assert spec.gate.require_positive_flow and spec.gate.min_unique_buyers == 10
    assert spec.gate.max_sells_to_buys == Decimal("0.6") and spec.trailing_arm_x == Decimal("1.5")
    assert _spec().clock == "1m", "every set frozen before T4.16 reads the minute"
    assert _flow_spec(pedigree_exclusions=False).pedigree_exclusions is False
    with pytest.raises(ValueError, match="unknown clock"):
        _flow_spec(clock="5s")


def test_a_passing_15s_row_becomes_a_proposal_that_names_its_series_flow_and_pedigree() -> None:
    spec = _flow_spec()
    outcome = evaluate_gate(
        spec, [_fast_row()], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={MINT: CLEAN}
    )
    assert outcome.refusals == {} and outcome.evaluated == 1
    (draft,) = outcome.drafts
    assert draft.status == "approved" and draft.decided_by == "rules"
    assert draft.features_end_time == T0, "the instant judged, stamped as the row's end_time"
    assert draft.reasons[0] == {"rule": "fluxo_e_holders/1", "series": SERIES_15S}
    blocks = {r.get("feature"): r for r in draft.reasons[1:]}
    assert blocks["flow"]["net_sol_flow_1m"] == "0.9" and blocks["flow"]["unique_buyers_1m"] == 12
    assert blocks["flow"]["buys_1m"] == 12 and blocks["flow"]["sells_1m"] == 6
    assert blocks["flow"]["holders_rising"] is True and blocks["flow"]["max_sells_to_buys"] == "0.6"
    assert blocks["pedigree"] == {
        "feature": "pedigree",
        "rule": "exclusoes_de_pedigree/1",
        "creator_prior_mints_1h": 0,
        "symbol_dup_24h": 1,
        "max_creator_prior_mints_1h": 1,
        "max_symbol_dup_24h": 2,
    }
    assert draft.suggested["trailing_arm_x"] == "1.5" and draft.suggested["exit_on_line_break"]


@pytest.mark.parametrize(
    ("lineage", "refusal"),
    [
        (PedigreeFeatures(2, 0), "creator_serial"),
        (PedigreeFeatures(0, 3), "symbol_clone"),
        (PedigreeFeatures(None, 0), "creator_unknown"),
        (PedigreeFeatures(0, None), "symbol_unknown"),
    ],
)
def test_the_pedigree_refuses_alongside_the_gate_and_by_name(
    lineage: PedigreeFeatures, refusal: str
) -> None:
    outcome = evaluate_gate(
        _flow_spec(),
        [_fast_row(net_sol_flow_1m=Decimal("-1"))],  # the gate says flow_not_positive too
        now=NOW,
        ttl_s=120,
        already_open=frozenset(),
        pedigree={MINT: lineage},
    )
    assert dict(outcome.refusals) == {refusal: 1, "flow_not_positive": 1}, (
        "both counted: the pedigree does not hide what the gate would have said"
    )
    assert outcome.drafts == []


def test_a_mint_the_pedigree_read_missed_is_unknown_and_an_opted_out_set_ignores_it() -> None:
    missing = evaluate_gate(
        _flow_spec(), [_fast_row()], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={}
    )
    assert dict(missing.refusals) == {"pedigree_unknown": 1}, "a passing row, an unread pedigree"
    opted_out = evaluate_gate(
        _flow_spec(pedigree_exclusions=False),
        [_fast_row()],
        now=NOW,
        ttl_s=120,
        already_open=frozenset(),
        pedigree={MINT: PedigreeFeatures(9, 9)},
    )
    assert len(opted_out.drafts) == 1
    assert all(r.get("feature") != "pedigree" for r in opted_out.drafts[0].reasons)


def test_the_flow_gate_refuses_churn_and_blindness_by_name() -> None:
    churn = evaluate_gate(
        _flow_spec(),
        [_fast_row(sells_1m=10, unique_buyers_1m=4, holders_rising=False)],
        now=NOW,
        ttl_s=120,
        already_open=frozenset(),
        pedigree={MINT: CLEAN},
    )
    assert dict(churn.refusals) == {
        "buyers_below_min": 1,
        "sells_ratio_above_max": 1,
        "holders_not_rising": 1,
    }
    blind = evaluate_gate(
        _flow_spec(),
        [
            _fast_row(
                net_sol_flow_1m=None,
                mcap_delta_60s=None,
                buys_1m=None,
                sells_1m=None,
                unique_buyers_1m=None,
                curve_volume_1m_sol=None,
                tape_reason="not_polled",
                holders_rising=None,
                holders_reason="too_few_readings",
            )
        ],
        now=NOW,
        ttl_s=120,
        already_open=frozenset(),
        pedigree={MINT: CLEAN},
    )
    assert dict(blind.refusals) == {
        "curve_volume_1m_unknown": 1,
        "flow_not_polled": 1,
        "buyers_unknown": 1,
        "sells_ratio_unknown": 1,
        "holders_too_few_readings": 1,
    }


def test_exp_m1_reasons_do_not_change_and_its_gate_still_takes_the_pedigree() -> None:
    row = _row(creator_sold=False, curve_volume_1m_sol=Decimal("20"))
    before = evaluate_gate(_spec(), [row], now=NOW, ttl_s=120, already_open=frozenset())
    (draft,) = before.drafts
    assert [r.get("feature", r.get("rule")) for r in draft.reasons] == [
        "comprar_cedo_na_curva/1",
        "age_s",
        "curve_progress_pct",
        "creator_net_seller",
        "participation_pct",
    ], "no series, no flow, no pedigree block: the frozen decomposition"
    serial = evaluate_gate(
        _spec(),
        [row],
        now=NOW,
        ttl_s=120,
        already_open=frozenset(),
        pedigree={MINT: PedigreeFeatures(2, 0)},
    )
    assert dict(serial.refusals) == {"creator_serial": 1}, "EXP-M6 is cross-cutting"
