"""The gate step of the Lab loop — one closed minute in, proposals or named refusals out.

No database and no clock: ``evaluate_gate`` is a function of a rule set, the
rows of one closed minute and ``now``. What is proved here is the first half of
the contract's §Semântica 1: the frozen EXP-M1 gate over a ``meme_features_1m``
row, a ``research_only`` proposal born already approved by ``rules``, an
``operator`` proposal born ``proposed`` and waiting, the quote priced with the
1,75 % fee, and — the honest part — that with today's free sources the frozen
gate refuses **every** row by name (``creator_net_seller_unknown``,
``curve_volume_1m_unknown``), which the loop counts instead of hiding.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.curve import CurveReserves, quote_buy
from hunter_meme_worker.lab_models import RuleSetSpec, Snapshot
from hunter_meme_worker.proposals import GateRow, evaluate_gate

from .test_paper_engine import PARAMS, RULE_SET_ID

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MINT = "5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38"
OPERATOR_ID = "01994d00-6c1a-7000-8000-000000000002"


def _spec(kind: str = "research_only", **overrides: Any) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id=RULE_SET_ID if kind == "research_only" else OPERATOR_ID,
        name="meme_paper_v0" if kind == "research_only" else "operator",
        version="1",
        kind=kind,
        exp_ref="EXP-M1" if kind == "research_only" else None,
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params={**PARAMS, **overrides},
    )


def _snapshot(seconds: int, sol: str = "34", tokens: str = "946000000") -> Snapshot:
    return Snapshot(
        mint=MINT,
        observed_at=T0 + timedelta(seconds=seconds),
        source="pumpfun_rest",
        reserves=CurveReserves(
            virtual_sol_reserves=Decimal(sol),
            virtual_token_reserves=Decimal(tokens),
            real_token_reserves=Decimal(tokens) - Decimal("279900000"),
            initial_real_token_reserves=Decimal("793100000"),
        ),
        real_sol_reserves=Decimal(sol) - Decimal(30),
        total_supply=Decimal(1_000_000_000),
        complete=False,
        mcap_sol=Decimal("35.94"),
    )


def _row(**overrides: Any) -> GateRow:
    base: dict[str, Any] = {
        "mint": MINT,
        "end_time": T0,
        "created_at": T0 - timedelta(seconds=120),
        "curve_progress_pct": Decimal("0.160000"),
        "progress_reason": None,
        "mcap_sol": Decimal("35.94"),
        "creator_sold": None,
        "curve_volume_1m_sol": None,
        "completed_at": None,
        "migrated_at": None,
        "snapshot": _snapshot(-20),
    }
    base.update(overrides)
    return GateRow(**base)


NOW = T0 + timedelta(seconds=75)


def test_todays_free_sources_make_the_frozen_gate_refuse_every_row_by_name() -> None:
    """EXP-M1's P1, measured here as the loop will measure it every minute."""
    outcome = evaluate_gate(_spec(), [_row()], now=NOW, ttl_s=120, already_open=frozenset())
    assert outcome.drafts == []
    assert outcome.refusals == {"creator_net_seller_unknown": 1, "curve_volume_1m_unknown": 1}
    assert outcome.evaluated == 1


def test_a_row_the_gate_allows_becomes_a_research_proposal_already_approved_by_rules() -> None:
    row = _row(creator_sold=False, curve_volume_1m_sol=Decimal(10))
    outcome = evaluate_gate(_spec(), [row], now=NOW, ttl_s=120, already_open=frozenset())
    assert outcome.refusals == {}
    (draft,) = outcome.drafts
    assert draft.mint == MINT and draft.rule_set_id == RULE_SET_ID
    assert draft.origin == "rules"
    assert draft.status == "approved"
    assert draft.decided_by == "rules" and draft.decided_at == NOW
    assert (
        draft.decision
        == draft.suggested
        == {
            "size_sol": "0.05",
            "target_x": "2",
            "trailing_pct": "30",
            "max_hold_s": 900,
        }
    )
    assert draft.proposed_at == NOW and draft.expires_at == NOW + timedelta(seconds=120)
    assert draft.features_end_time == T0, "the closed minute that motivated it"
    quote = quote_buy(row.snapshot.reserves, Decimal("0.05"), Decimal("1.75"))  # type: ignore[union-attr]
    assert draft.quote["observed_at"] == (T0 - timedelta(seconds=20)).isoformat()
    assert draft.quote["source"] == "pumpfun_rest"
    assert draft.quote["curve_progress_pct"] == "16"  # plain digits, never 16.000000
    assert draft.quote["mcap_sol"] == "35.94"
    # The keys the desk reads (contract, Emendas of T4.7), priced with the 1,75 % fee.
    assert {
        k: Decimal(draft.quote[k]) for k in ("size_sol", "fee_pct", "fee_sol", "cost_sol", "tokens")
    } == {
        "size_sol": Decimal("0.05"),
        "fee_pct": Decimal("1.75"),
        "fee_sol": quote.fee_sol,
        "cost_sol": quote.total_sol,
        "tokens": quote.tokens,
    }
    assert draft.quote["reason"] is None and "price_sol_per_token" in draft.quote
    rules = [r for r in draft.reasons if "rule" in r]
    assert rules == [{"rule": "comprar_cedo_na_curva/1"}]
    features = {r["feature"]: r for r in draft.reasons if "feature" in r}
    assert features["age_s"]["value"] == 120
    assert features["curve_progress_pct"]["value"] == "16"
    assert Decimal(features["participation_pct"]["value"]) == Decimal("0.5")


def test_an_operator_proposal_is_born_proposed_and_waits_for_the_desk() -> None:
    row = _row(creator_sold=False, curve_volume_1m_sol=Decimal(10))
    (draft,) = evaluate_gate(
        _spec("operator"), [row], now=NOW, ttl_s=120, already_open=frozenset()
    ).drafts
    assert draft.status == "proposed"
    assert draft.decision is None and draft.decided_by is None and draft.decided_at is None
    assert draft.rule_set_id == OPERATOR_ID


def test_a_mint_already_open_for_the_rule_set_is_not_proposed_again() -> None:
    row = _row(creator_sold=False, curve_volume_1m_sol=Decimal(10))
    outcome = evaluate_gate(_spec(), [row], now=NOW, ttl_s=120, already_open=frozenset({MINT}))
    assert outcome.drafts == [] and outcome.refusals == {"already_open": 1}


@pytest.mark.parametrize(
    ("overrides", "refusal"),
    [
        ({"created_at": None}, "age_unknown"),
        ({"created_at": T0 - timedelta(seconds=10)}, "age_below_min"),
        (
            {"curve_progress_pct": None, "progress_reason": "denominator_unknown"},
            "progress_unknown",
        ),
        ({"curve_progress_pct": Decimal("0.7")}, "progress_above_max"),
        ({"creator_sold": True}, "creator_is_net_seller"),
        ({"curve_volume_1m_sol": Decimal("0.5")}, "participation_above_cap"),
        ({"completed_at": T0}, "curve_complete"),
        ({"migrated_at": T0}, "already_migrated"),
        (
            {"snapshot": None, "curve_progress_pct": None, "progress_reason": "not_polled"},
            "progress_unknown",
        ),
    ],
)
def test_every_gate_refusal_is_named_and_counted(overrides: dict[str, Any], refusal: str) -> None:
    base = {"creator_sold": False, "curve_volume_1m_sol": Decimal(10)}
    outcome = evaluate_gate(
        _spec(), [_row(**{**base, **overrides})], now=NOW, ttl_s=120, already_open=frozenset()
    )
    assert outcome.drafts == []
    assert refusal in outcome.refusals


def test_progress_is_read_as_a_fraction_and_judged_in_percent() -> None:
    """``meme_features_1m.curve_progress_pct`` is a fraction (T4.2); the gate's
    window is in percent (T4.5). 0,016 is 1,6 %, below the 2 % floor."""
    row = _row(
        creator_sold=False, curve_volume_1m_sol=Decimal(10), curve_progress_pct=Decimal("0.016")
    )
    outcome = evaluate_gate(_spec(), [row], now=NOW, ttl_s=120, already_open=frozenset())
    assert outcome.refusals == {"progress_below_min": 1}
