# pyright: reportPrivateUsage=false
"""T4.19 — ``operator/3`` on the desk: the same gate as ``flow_v2/1`` (EXP-M5)
with the same pedigree exclusions (EXP-M6), so on one 15-second row the two
sets propose the **same coin** with the same decomposition — the research one
born approved by ``rules``, the operator one born ``proposed`` and waiting
**180 s** (the set's own ``ttl_s``, not the loop's 120) — and every operator
proposal carries ``suggested.manual_plan``: the plan Everton executes by hand,
every number read from the set's ``params``, every hour in Brasília time."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.proposals import SERIES_15S, evaluate_gate
from hunter_meme_worker.proposals_plan import manual_plan, ticker_of

from .test_proposals import MINT, _spec
from .test_proposals_flow import CLEAN, FLOW_PARAMS, _fast_row, _flow_spec

pytestmark = pytest.mark.unit

OPERATOR_3_ID = "01994d00-6c1a-7000-8000-00000000000a"
OPERATOR_3_PARAMS: dict[str, Any] = {**FLOW_PARAMS, "ttl_s": 180, "max_open_positions": 2}
"""``0033``'s seed in miniature: ``FLOW_V2_PARAMS`` plus the two numbers the
brief changes for a buy by hand."""
NOW = datetime(2026, 9, 12, 20, 30, tzinfo=UTC)
"""17:30:00 in Brasília (UTC−3), the afternoon of the directive."""
PLAN = (
    "Comprar 0,05 SOL de PEPE até 17:33:00 (proposta expira). "
    "Vender até 18:00 (30 min) — antes disso se triplicar (3×), se recuar 35 % do topo depois "
    "de 1,5×, se cair pela metade (−50 %), se o dev vender, ou se a linha de suporte quebrar."
)
"""The brief's sentence plus the trailing stop (Astra's must-fix: the engine
sells a 2× → 1,3× retreat; a hand that was not told would hold)."""


def _operator_3(**overrides: Any) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id=OPERATOR_3_ID,
        name="operator",
        version="3",
        kind="operator",
        exp_ref=None,
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params={**OPERATOR_3_PARAMS, **overrides},
    )


def _gate(spec: RuleSetSpec, row: Any) -> Any:
    return evaluate_gate(
        spec, [row], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={MINT: CLEAN}
    )


def test_the_operator_set_parses_its_own_ttl_and_every_older_set_keeps_the_loops() -> None:
    spec, flow = _operator_3(), _flow_spec()
    assert spec.ttl_s == 180 and spec.clock == "15s" and spec.max_open_positions == 2
    assert replace(spec.gate, description=flow.gate.description) == flow.gate, "the same gate"
    assert spec.pedigree_exclusions is flow.pedigree_exclusions is True, "the same exclusions"
    assert flow.ttl_s is None and _spec().ttl_s is None and _spec("operator").ttl_s is None


def test_operator_3_proposes_the_same_coin_as_flow_v2_on_the_same_row_and_waits_180_s() -> None:
    row = _fast_row(symbol="PEPE")
    (research,) = _gate(_flow_spec(), row).drafts
    (proposal,) = _gate(_operator_3(), row).drafts
    assert proposal.mint == research.mint == MINT
    assert proposal.features_end_time == research.features_end_time, "the same instant judged"
    assert (
        proposal.reasons[0]
        == research.reasons[0]
        == {
            "rule": "fluxo_e_holders/1",
            "series": SERIES_15S,
        }
    )
    assert [r.get("feature") for r in proposal.reasons] == [
        r.get("feature") for r in research.reasons
    ]
    assert proposal.rule_set_id == OPERATOR_3_ID and proposal.status == "proposed"
    assert proposal.decision is None and proposal.decided_by is None
    assert proposal.proposed_at == NOW
    assert proposal.expires_at == NOW + timedelta(seconds=180), "the set's ttl_s, not the loop's"
    assert research.expires_at == NOW + timedelta(seconds=120), "flow_v2/1 keeps the loop's"


def test_what_the_flow_gate_refuses_the_operator_gate_refuses_by_the_same_names() -> None:
    churn = _fast_row(sells_1m=10, unique_buyers_1m=4, holders_rising=False)
    assert dict(_gate(_operator_3(), churn).refusals) == dict(_gate(_flow_spec(), churn).refusals)
    assert dict(_gate(_operator_3(), churn).refusals) == {
        "buyers_below_min": 1,
        "sells_ratio_above_max": 1,
        "holders_not_rising": 1,
    }


def test_the_operator_proposal_carries_the_plan_to_execute_by_hand() -> None:
    (proposal,) = _gate(_operator_3(), _fast_row(symbol="PEPE")).drafts
    assert proposal.suggested["manual_plan"] == PLAN
    without_plan = {k: v for k, v in proposal.suggested.items() if k != "manual_plan"}
    assert without_plan == _operator_3().suggested(), "the four numbers and the switches, as before"
    (research,) = _gate(_flow_spec(), _fast_row(symbol="PEPE")).drafts
    assert "manual_plan" not in research.suggested, "a research proposal is nobody's plan"
    assert research.decision is not None and "manual_plan" not in research.decision


def test_a_coin_without_a_ticker_is_named_by_its_mint() -> None:
    (proposal,) = _gate(_operator_3(), _fast_row()).drafts
    assert proposal.suggested["manual_plan"].startswith(f"Comprar 0,05 SOL de {MINT[:6]}… até ")
    assert ticker_of(None, MINT) == f"{MINT[:6]}…" and ticker_of("PEPE", MINT) == "PEPE"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "size_sol": "0.1",
                "target_x": "2",
                "max_loss_pct": "40",
                "max_hold_s": 600,
                "exit_on_line_break": False,
            },
            "Comprar 0,1 SOL de DOGE até 17:31:00 (proposta expira). Vender até 17:40 (10 min) "
            "— antes disso se dobrar (2×), se recuar 35 % do topo depois de 1,5×, se cair 40 %, "
            "ou se o dev vender.",
        ),
        (
            {
                "size_sol": "0.020",
                "target_x": "10",
                "trailing_pct": "40",
                "trailing_arm_x": None,
                "max_loss_pct": "100",
                "max_hold_s": 90,
            },
            "Comprar 0,02 SOL de DOGE até 17:31:00 (proposta expira). Vender até 17:31 (90 s) "
            "— antes disso se chegar a 10×, se recuar 40 % do topo, se cair 100 %, "
            "se o dev vender, ou se a linha de suporte quebrar.",
        ),
    ],
)
def test_every_number_of_the_plan_is_read_from_the_params(
    overrides: dict[str, Any], expected: str
) -> None:
    spec = _operator_3(**overrides)
    assert manual_plan(spec, ticker="DOGE", proposed_at=NOW, ttl_s=60) == expected
    assert spec.size_sol == Decimal(str(overrides["size_sol"]))
