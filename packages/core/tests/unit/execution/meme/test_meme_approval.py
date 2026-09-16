"""The desk decision's rules, shared by the API click and the executor's stage-1
auto-approval (T4.28): every refusal is named, every rule has a passing and a
failing case, and the SQL is the one guarded statement both callers run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.execution.meme.approval import (
    AUTO_STAGE1_DECIDED_BY,
    DECIDE_PROPOSAL,
    ProposalDecision,
    live_mode_refusal,
    max_sol_per_bet_of,
    proposal_state_refusal,
    size_cap_refusal,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 16, 4, 30, tzinfo=UTC)


class TestProposalState:
    def test_a_proposed_row_before_its_deadline_may_be_decided(self) -> None:
        assert (
            proposal_state_refusal("proposed", NOW + timedelta(seconds=90), NOW, approving=True)
            is None
        )

    @pytest.mark.parametrize("status", ["approved", "rejected", "expired", "filled", "unfilled"])
    def test_anything_but_proposed_is_not_proposed(self, status: str) -> None:
        assert (
            proposal_state_refusal(status, NOW + timedelta(seconds=90), NOW, approving=True)
            == "not_proposed"
        )

    def test_approving_at_or_after_the_deadline_is_expired(self) -> None:
        assert proposal_state_refusal("proposed", NOW, NOW, approving=True) == "expired"
        assert (
            proposal_state_refusal("proposed", NOW - timedelta(seconds=1), NOW, approving=True)
            == "expired"
        )

    def test_rejecting_after_the_deadline_is_still_allowed(self) -> None:
        """The loop stamps ``expired`` on its own tick; a rejection in between is a decision."""
        assert (
            proposal_state_refusal("proposed", NOW - timedelta(seconds=1), NOW, approving=False)
            is None
        )


class TestSizeCap:
    def test_within_the_set_ceiling_passes(self) -> None:
        assert size_cap_refusal(Decimal("0.05"), Decimal("0.05")) is None

    def test_above_the_set_ceiling_is_refused_by_name(self) -> None:
        assert size_cap_refusal(Decimal("0.05"), Decimal("0.0501")) == "exceeds_max_sol_per_bet"

    def test_a_set_without_a_ceiling_refuses_nothing_here(self) -> None:
        assert size_cap_refusal(None, Decimal("9")) is None

    def test_the_ceiling_is_read_from_the_set_params(self) -> None:
        assert max_sol_per_bet_of({"max_sol_per_bet": "0.05"}) == Decimal("0.05")
        assert max_sol_per_bet_of({"max_sol_per_bet": 0.05}) == Decimal("0.05")
        assert max_sol_per_bet_of({}) is None
        assert max_sol_per_bet_of({"max_sol_per_bet": "abc"}) is None
        assert max_sol_per_bet_of({"max_sol_per_bet": True}) is None


class TestLiveMode:
    def test_paper_never_needs_the_flag(self) -> None:
        assert live_mode_refusal("paper", live_enabled=False) is None

    def test_live_without_the_flag_is_refused_by_name(self) -> None:
        assert live_mode_refusal("live", live_enabled=False) == "meme_live_disabled"

    def test_live_with_the_flag_passes(self) -> None:
        assert live_mode_refusal("live", live_enabled=True) is None


class TestDecisionRow:
    def test_the_statement_is_guarded_on_proposed(self) -> None:
        sql = str(DECIDE_PROPOSAL)
        assert "status = 'proposed'" in sql
        assert "UPDATE meme_proposals" in sql
        for column in ("status", "decision", "decided_by", "decided_at", "mode"):
            assert f"{column} = " in sql or f"{column} = CAST" in sql

    def test_parameters_serialize_the_decision_as_json_and_null_as_null(self) -> None:
        decided = ProposalDecision(
            proposal_id="01994d00-6c1a-7000-8000-000000000099",
            status="approved",
            decision={"size_sol": "0.05", "note": None},
            decided_by=AUTO_STAGE1_DECIDED_BY,
            decided_at=NOW,
            mode="live",
        )
        params = decided.parameters()
        assert params["decision"] == '{"size_sol": "0.05", "note": null}'
        assert params["decided_by"] == "executor:auto_stage1"
        assert params["mode"] == "live" and params["status"] == "approved"
        rejected = ProposalDecision(
            proposal_id=decided.proposal_id,
            status="rejected",
            decision=None,
            decided_by="user_x",
            decided_at=NOW,
            mode="paper",
        )
        assert rejected.parameters()["decision"] is None

    def test_only_the_two_decisions_exist(self) -> None:
        with pytest.raises(ValueError, match="filled"):
            ProposalDecision(
                proposal_id="01994d00-6c1a-7000-8000-000000000099",
                status="filled",  # type: ignore[arg-type]
                decision=None,
                decided_by="x",
                decided_at=NOW,
                mode="paper",
            )
