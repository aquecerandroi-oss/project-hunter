# pyright: reportPrivateUsage=false
"""T4.31 (EXP-M9) — E2-b inside the gate step, and the tape row as the
criterion reads it.

No database and no clock: ``evaluate_gate`` is a function of a rule set, the
rows of one instant, the pedigree and the E2-b mapping the caller read. What
is proved here: only a set with ``pedigree_e2b`` is judged by it; the mapping
is keyed by ``(mint, end_time)`` so a row never reads a later row's tape; a
judged pair the caller did not read refuses ``e2b_top_buyer_unknown``; the
decomposition of an approved proposal carries the two legs and the frozen
thresholds; and the lamport counters become an exact ``Decimal`` share.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.pedigree import PedigreeFeatures
from hunter_indicators.meme.pedigree_e2b import E2bFeatures
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_repo_e2b import e2b_features_from_counts
from hunter_meme_worker.proposals import GateOutcome, evaluate_gate

from .test_proposals import MINT, NOW, T0, _row, _spec

pytestmark = pytest.mark.unit

CREATED = T0 - timedelta(seconds=120)
CLEAN_PEDIGREE = {MINT: PedigreeFeatures(creator_prior_mints_1h=0, symbol_dup_24h=0)}


def _allowed_row() -> Any:
    """The row ``test_proposals`` proves the frozen gate approves."""
    return _row(creator_sold=False, curve_volume_1m_sol=Decimal(10))


def _evaluate(spec: RuleSetSpec, e2b: dict[tuple[str, Any], E2bFeatures] | None) -> GateOutcome:
    return evaluate_gate(
        spec,
        [_allowed_row()],
        now=NOW,
        ttl_s=120,
        already_open=frozenset(),
        pedigree=CLEAN_PEDIGREE,
        e2b=e2b,
    )


def _forged(share: str | None, buyers: int | None, fill_seconds: int | None) -> E2bFeatures:
    return E2bFeatures(
        top_buyer_share=None if share is None else Decimal(share),
        buyers=buyers,
        fill_seconds=fill_seconds,
        tape_reason=None if share is not None else "no_tape",
    )


def test_a_set_without_the_switch_is_never_judged_by_e2b() -> None:
    """The falsification discipline: E2-b applies to the arm that says so."""
    outcome = _evaluate(_spec(), {(MINT, T0): _forged("0.99", 40, 5)})
    assert len(outcome.drafts) == 1
    assert outcome.refusals == {}


def test_the_concentration_leg_refuses_by_name() -> None:
    outcome = _evaluate(_spec(pedigree_e2b=True), {(MINT, T0): _forged("0.42", 21, None)})
    assert outcome.drafts == []
    assert dict(outcome.refusals) == {"e2b_top_buyer_share": 1}


def test_the_guard_keeps_a_young_tape_from_refusing_by_youth() -> None:
    """Nine buyers at 0,99: the share is high by construction (KB-0105 §4)."""
    outcome = _evaluate(_spec(pedigree_e2b=True), {(MINT, T0): _forged("0.99", 9, None)})
    assert len(outcome.drafts) == 1
    assert outcome.refusals == {}


def test_born_full_refuses_by_its_own_name() -> None:
    outcome = _evaluate(_spec(pedigree_e2b=True), {(MINT, T0): _forged("0.05", 40, 12)})
    assert dict(outcome.refusals) == {"e2b_born_full": 1}


def test_a_pair_the_caller_did_not_read_refuses_unknown() -> None:
    """A datum absent is not a clean coin — and the row judged at ``T0`` does
    not get to read the tape summed at a **later** instant either."""
    later = {(MINT, T0 + timedelta(seconds=15)): _forged("0.01", 40, None)}
    for mapping in ({}, later):
        outcome = _evaluate(_spec(pedigree_e2b=True), mapping)
        assert outcome.drafts == []
        assert dict(outcome.refusals) == {"e2b_top_buyer_unknown": 1}


def test_an_unread_mapping_means_the_criterion_is_not_applied() -> None:
    """``e2b=None`` = the caller never asked (a unit test of the gate alone,
    the scale step): the set's other criteria still judge the row."""
    outcome = _evaluate(_spec(pedigree_e2b=True), None)
    assert len(outcome.drafts) == 1


def test_the_decomposition_carries_the_two_legs_and_the_thresholds() -> None:
    outcome = _evaluate(_spec(pedigree_e2b=True), {(MINT, T0): _forged("0.21", 30, None)})
    block = next(r for r in outcome.drafts[0].reasons if r.get("feature") == "pedigree_e2b")
    assert block == {
        "feature": "pedigree_e2b",
        "rule": "pedigree_e2b/1",
        "top_buyer_share": "0.21",
        "buyers": 30,
        "fill_seconds": None,
        "tape_reason": None,
        "e2b_top_buyer_share_max": "0.35",
        "e2b_min_buyers": "10",
        "e2b_born_full_s": "60",
    }


@pytest.mark.parametrize(
    ("counts", "share", "buyers", "reason"),
    [
        (
            {"buyers": 4, "top_lamports": 350_000_000, "total_lamports": 1_000_000_000},
            "0.35",
            4,
            None,
        ),
        ({"buyers": 3, "top_lamports": 1, "total_lamports": 3}, None, 3, None),
        ({"buyers": None, "top_lamports": None, "total_lamports": None}, None, None, "no_tape"),
        ({"buyers": 2, "top_lamports": 0, "total_lamports": 0}, None, 2, "no_sol_bought"),
    ],
)
def test_the_lamport_counters_become_an_exact_decimal_share(
    counts: dict[str, int | None], share: str | None, buyers: int | None, reason: str | None
) -> None:
    features = e2b_features_from_counts(created_at=CREATED, completed_at=None, **counts)  # type: ignore[arg-type]
    if share is None and reason is None:  # 1/3 is exact only under the project's context
        assert features.top_buyer_share == Decimal(1) / Decimal(3)
    else:
        assert features.top_buyer_share == (None if share is None else Decimal(share))
    assert (features.buyers, features.tape_reason) == (buyers, reason)


def test_the_fill_stamp_is_seconds_and_survives_the_same_block_negative() -> None:
    """KB-0103 §5: 42,7 % of the graduated coins carry ``completed_at`` at or
    before ``created_at`` (same block, rounding) — that is still born full."""
    features = e2b_features_from_counts(
        created_at=CREATED,
        completed_at=CREATED - timedelta(seconds=3),
        buyers=None,
        top_lamports=None,
        total_lamports=None,
    )
    assert features.fill_seconds == -3
