"""§8.4 / §8.6: the decision object, determinism, and ``evaluate_exit`` — which always
approves, whatever the kill switch or the position look like."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState as K
from hunter_risk_b3 import (
    SPEC_FIELDS,
    B3Check,
    BrokerPosition,
    CheckState,
    DecisionKind,
    ExitReason,
    ExitRequest,
    QuoteSnapshot,
    RiskDecision,
    Side,
    SpecNow,
    SpecPin,
    evaluate_exit,
)

from . import factories as fx

pytestmark = pytest.mark.unit


def _position() -> BrokerPosition:
    return BrokerPosition(
        position_id=11, position_ticket=12, symbol="WINZ26", side=Side.BUY, volume=Decimal("1"),
        price_open=Decimal("207005"), sl=Decimal("205975"), tp=Decimal("0"), magic=fx.MAGIC,
        time_msc=1,
    )  # fmt: skip


def test_spec_fields_are_carried_by_both_spec_models() -> None:
    assert set(SPEC_FIELDS) == set(SpecPin.model_fields) - {"spec_pin_id"}
    assert set(SPEC_FIELDS) == set(SpecNow.model_fields) - {"status"}


def test_same_inputs_same_decision_hash() -> None:
    a, b = fx.scenario().evaluate(), fx.scenario().evaluate()
    assert a == b
    assert a.decision_hash() == b.decision_hash()
    assert len(a.decision_hash()) == 64


def test_different_inputs_different_hash() -> None:
    sc = fx.scenario()
    other = sc.with_(quote=sc.quote.model_copy(update={"time_utc": fx.NOW - fx.s(2)}))
    assert sc.evaluate().decision_hash() != other.evaluate().decision_hash()


def test_float_never_constructs_an_input() -> None:
    with pytest.raises(TypeError, match="float"):
        QuoteSnapshot(bid=207000.0, ask=Decimal("1"), last=None, time_utc=fx.NOW, read_ok=True)  # type: ignore[arg-type]


def test_naive_datetime_never_constructs_an_input() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        QuoteSnapshot(
            bid=Decimal("1"), ask=Decimal("2"), last=None,
            time_utc=datetime(2026, 10, 20, 19, 30), read_ok=True,  # noqa: DTZ001
        )  # fmt: skip


def test_read_ok_quote_must_carry_its_fields() -> None:
    with pytest.raises(ValueError, match="read_ok"):
        QuoteSnapshot(bid=None, ask=Decimal("2"), last=None, time_utc=fx.NOW, read_ok=True)


def test_a_decision_claiming_approval_with_a_failed_check_is_refused() -> None:
    good = fx.scenario().evaluate()
    bad_checks = list(good.checks)
    bad_checks[0] = B3Check(
        id=1, name="kill_switch", state=CheckState.FAILED, reason="kill_switch_emergency"
    )
    with pytest.raises(ValueError, match="approved"):
        RiskDecision.model_validate({**good.model_dump(), "checks": bad_checks})


@pytest.mark.parametrize("state", list(K))
@pytest.mark.parametrize("with_position", [True, False])
def test_evaluate_exit_always_approves(state: K, with_position: bool) -> None:
    kill = fx.kill(system=state, robot=K.EMERGENCY if state is K.ACTIVE else state)
    decision = evaluate_exit(
        ExitRequest(position_ticket=12, exit_reason=ExitReason.EMERGENCY),
        _position() if with_position else None,
        kill,
    )
    assert decision.approved
    assert decision.kind is DecisionKind.EXIT
    assert decision.reasons == ()
    assert [c.name for c in decision.checks] == ["kill_switch", "position_seen"]
    assert decision.kill_switch_effective is (K.EMERGENCY if state is K.ACTIVE else state)


def test_exit_position_seen_is_informative() -> None:
    seen = evaluate_exit(
        ExitRequest(position_ticket=12, exit_reason=ExitReason.TIME_EXIT), _position(), fx.kill()
    )
    unseen = evaluate_exit(
        ExitRequest(position_ticket=99, exit_reason=ExitReason.TIME_EXIT), _position(), fx.kill()
    )
    assert seen.checks[1].state is CheckState.PASSED
    assert unseen.checks[1].state is CheckState.UNAVAILABLE
    assert unseen.approved


@pytest.mark.parametrize("raw", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_never_construct_an_input(raw: str) -> None:
    """§8.3: non-finite values are refused before sizing — here, at construction."""
    with pytest.raises(ValueError):
        QuoteSnapshot(bid=Decimal(raw), ask=Decimal("2"), last=None, time_utc=fx.NOW, read_ok=True)
