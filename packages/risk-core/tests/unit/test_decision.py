"""The decision record: every check kept, the winning ceiling named, canonical JSON."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.decision import CheckState, LimitCap, RiskCheck, RiskDecision

from .factories import SOL

pytestmark = pytest.mark.unit

PROPOSAL_ID = uuid.UUID("00000000-0000-7000-8000-000000000001")
PORTFOLIO_ID = uuid.UUID("00000000-0000-7000-8000-0000000000aa")


def _decision(**over: object) -> RiskDecision:
    base: dict[str, object] = {
        "approved": False,
        "kind": "entry",
        "proposal_id": PROPOSAL_ID,
        "portfolio_id": PORTFOLIO_ID,
        "market": SOL,
        "limits_profile": "paper_v1",
        "effective_kill_switch": KillSwitchState.ACTIVE,
        "cancel_pending": False,
        "shadow_only": False,
        "checks": (
            RiskCheck(name="kill_switch", state=CheckState.PASSED, message="ACTIVE"),
            RiskCheck(
                name="asset_exposure",
                state=CheckState.FAILED,
                value=Decimal("2500"),
                limit=Decimal("2000"),
                message="exposicao por moeda acima do teto",
            ),
            RiskCheck(name="book_depth", state=CheckState.UNAVAILABLE, message="livro ausente"),
        ),
        "sizing": None,
        "exit_plan": None,
    }
    return RiskDecision.model_validate(base | over)


class TestChecks:
    def test_a_check_knows_whether_it_passed(self) -> None:
        assert RiskCheck(name="x", state=CheckState.PASSED).passed is True
        assert RiskCheck(name="x", state=CheckState.FAILED).passed is False
        assert RiskCheck(name="x", state=CheckState.UNAVAILABLE).passed is False

    def test_unavailable_is_a_third_state_not_a_synonym_of_failed(self) -> None:
        # R-OPS-1: "o insumo faltou" and "o limite foi violado" are different facts and
        # the panel has to be able to tell them apart, even though both reject.
        assert CheckState.UNAVAILABLE != CheckState.FAILED

    def test_every_check_is_kept_even_after_the_first_failure(self) -> None:
        decision = _decision()
        assert [c.name for c in decision.checks] == [
            "kill_switch",
            "asset_exposure",
            "book_depth",
        ]

    def test_rejection_reasons_name_every_check_that_did_not_pass(self) -> None:
        assert _decision().rejection_reasons == ("asset_exposure", "book_depth")

    def test_a_decision_may_not_be_approved_while_a_check_did_not_pass(self) -> None:
        with pytest.raises(ValueError, match="approved"):
            _decision(approved=True)

    def test_two_checks_may_not_share_a_name(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            _decision(
                checks=(
                    RiskCheck(name="cash", state=CheckState.PASSED),
                    RiskCheck(name="cash", state=CheckState.PASSED),
                )
            )


class TestSerialisation:
    def test_the_decision_serialises_through_canonical_json(self) -> None:
        body = _decision().to_jsonable()
        assert body["approved"] is False
        assert body["market"]["symbol"] == "SOLUSDT"
        assert body["checks"][1]["value"] == "2500"
        assert body["checks"][1]["limit"] == "2000"
        assert body["checks"][2]["state"] == "unavailable"

    def test_numbers_are_canonical_strings_never_floats(self) -> None:
        raw = json.dumps(_decision().to_jsonable())
        assert '"2500"' in raw
        assert "2500.0" not in raw

    def test_the_same_decision_always_produces_the_same_bytes(self) -> None:
        assert _decision().to_jsonable() == _decision().to_jsonable()


class TestBindingLimit:
    def test_a_cap_may_be_unbounded(self) -> None:
        cap = LimitCap(name="beta_exposure", notional=None, limit=Decimal("10000"))
        assert cap.notional is None

    def test_a_decision_without_sizing_has_no_binding_limit(self) -> None:
        assert _decision().binding_limit is None
