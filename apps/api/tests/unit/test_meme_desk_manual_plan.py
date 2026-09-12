# pyright: reportPrivateUsage=false
"""T4.19 on the API, without a database: an operator proposal's
``suggested.manual_plan`` (written by the loop at proposal time) reaches the
desk as ``manual_plan`` on the row — and a proposal the loop wrote without one
(every research proposal, every row older than T4.19) says ``None``, never a
plan the API made up."""

from __future__ import annotations

import pytest

from hunter_api.repositories.meme_desk_rows import DeskRow
from hunter_api.schemas.meme_desk import ProposalOut
from hunter_api.services.meme_desk_out import build_desk_row_out

from .test_meme_desk_service import _proposal, _rule_set

pytestmark = pytest.mark.unit

PLAN = (
    "Comprar 0,05 SOL de PEPE até 17:33:00 (proposta expira). "
    "Vender até 18:00 (30 min) — antes disso se triplicar (3×), se cair pela metade (−50 %), "
    "se o dev vender, ou se a linha de suporte quebrar."
)


def _row(**suggested: object) -> DeskRow:
    rule_set = _rule_set(name="operator", version="3")
    proposal = _proposal(
        rule_set,
        suggested={
            "size_sol": "0.05",
            "target_x": "3",
            "trailing_pct": "35",
            "max_hold_s": 1800,
            **suggested,
        },
    )
    return DeskRow(proposal=proposal, token=None, bet=None, rule_set=rule_set, rank=0)


def test_the_operator_proposal_carries_the_loops_plan_verbatim() -> None:
    out = build_desk_row_out(_row(manual_plan=PLAN))
    assert out.manual_plan == PLAN
    assert out.suggested.size_sol is not None and out.suggested.max_hold_s == 1800
    assert ProposalOut(row=out).row.manual_plan == PLAN


def test_a_proposal_without_a_plan_says_none_and_a_non_string_is_not_a_plan() -> None:
    assert build_desk_row_out(_row()).manual_plan is None
    assert build_desk_row_out(_row(manual_plan=42)).manual_plan is None
    assert build_desk_row_out(_row(manual_plan=None)).manual_plan is None
