"""Astra's review of R1 (``.claude/state/astra-review-R1-hunter-risk-b3.md``): five
must-fix scenarios she reproduced, each pinned as a test that failed before the fix.

1. a non-positive margin for the final volume approved the entry;
2. a ``float`` nested in a dict (``per_volume={1: 100.1}``) constructed;
3. a deal without its commission/fee defaulted to zero (a cost hidden as 0);
4. check 8 ``unavailable`` did not propagate to checks 9, 15 and 24;
5. a mark (and, same class, any freshness stamp) from the future counted as fresh.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from hunter_risk_b3 import (
    AuditPath,
    CheckState,
    DayDeal,
    DealKind,
    LastReconcile,
    MarginInputs,
    OrderCheckResult,
)

from . import factories as fx
from .factories import NOW, s

pytestmark = pytest.mark.unit
D = Decimal
U = CheckState.UNAVAILABLE


def _two_contracts(per_volume: dict[int, Decimal]) -> fx.Scenario:
    sc = fx.scenario()
    return sc.with_(
        limits=sc.limits.model_copy(
            update={
                "max_contracts_per_order": 2,
                "max_contracts_per_position": 2,
                "max_loss_per_trade_brl": D("500"),
            }  # fmt: skip
        ),
        proposal=sc.proposal.model_copy(update={"requested_contracts": 2}),
        margin=fx.margin(per_volume=per_volume),
    )


@pytest.mark.parametrize("final", [D("-1"), D("0")])
def test_1_non_positive_margin_at_the_final_volume_is_unavailable(final: Decimal) -> None:
    decision = _two_contracts({1: D("100"), 2: final}).evaluate()
    assert decision.sizing is not None
    assert decision.sizing.n_final == 2
    assert (decision.checks[17].state, decision.checks[17].reason) == (U, "margin_unavailable")
    assert not decision.approved


def test_1_non_positive_unit_margin_makes_the_ceilings_uncomputable() -> None:
    decision = _two_contracts({1: D("0"), 2: D("200")}).evaluate()
    assert decision.sizing is not None
    assert decision.sizing.caps["alloc_margin"] is None
    assert not decision.approved


def test_2_a_float_nested_in_a_dict_never_constructs() -> None:
    bad: Any = {1: 100.1}
    with pytest.raises(TypeError, match="float"):
        MarginInputs(per_volume=bad, order_check={1: OrderCheckResult(ok=True)}, read_ok=True)


def test_2_a_float_nested_in_a_tuple_never_constructs() -> None:
    sc = fx.scenario()
    data = sc.ops.model_dump()
    data["entry_rejects"] = (1.5,)
    with pytest.raises(TypeError, match="float"):
        type(sc.ops).model_validate(data)


@pytest.mark.parametrize("missing", ["commission", "fee"])
def test_3_a_deal_without_commission_or_fee_does_not_construct(missing: str) -> None:
    fields: dict[str, Any] = {"ticket": 1, "kind": DealKind.TRADE, "profit": D("-10"),
                              "commission": D("0"), "fee": D("0")}  # fmt: skip
    del fields[missing]
    with pytest.raises(ValueError, match=missing):
        DayDeal.model_validate(fields)


def test_4_unmeasured_clock_propagates_to_spread_stop_and_slippage() -> None:
    sc = fx.scenario()
    clock = sc.session.clock.model_copy(update={"ok": False})
    decision = sc.with_(session=sc.session.model_copy(update={"clock": clock})).evaluate()
    assert decision.checks[7].reason == "clock_offset_unmeasured"
    for cid in (9, 15, 24):
        assert (decision.checks[cid - 1].state, decision.checks[cid - 1].reason) == (
            U,
            "upstream_unavailable:8",
        ), cid


def test_4_independent_stop_failures_still_win_over_the_upstream() -> None:
    sc = fx.scenario()
    clock = sc.session.clock.model_copy(update={"ok": False})
    sc = sc.with_(
        session=sc.session.model_copy(update={"clock": clock}),
        proposal=sc.proposal.model_copy(update={"stop_price": None, "ref_price": D("207006")}),
    )
    decision = sc.evaluate()
    assert decision.checks[14].reason == "stop_missing"
    assert decision.checks[23].reason == "reference_off_tick"


def _day(**u: object) -> fx.Scenario:
    sc = fx.scenario()
    return sc.with_(ops=sc.ops.model_copy(update={"day": sc.ops.day.model_copy(update=u)}))


@pytest.mark.parametrize(
    ("scenario", "cid", "reason"),
    [
        (lambda: _day(mark_time=NOW + s(86400)), 14, "mark_stale"),
        (lambda: _day(anchor_at=NOW + s(60)), 14, "day_anchor_missing"),
        (
            lambda: fx.scenario().with_(
                ops=fx.ops(last_reconcile=LastReconcile(at=NOW + s(60), clean=True, consistent_passes=2))
            ),
            20,
            "reconciliation_stale",
        ),
        (
            lambda: fx.scenario().with_(
                ops=fx.ops(audit=AuditPath(api_last_ok_at=NOW + s(60), buffer_len=0, buffer_writable=True))
            ),
            21,
            "audit_api_unreachable",
        ),
        (
            lambda: fx.scenario().with_(
                session=fx.session(clock=fx.ClockCheck(offset_ms=0, measured_at=NOW + s(60), ok=True))
            ),
            8,
            "clock_offset_unmeasured",
        ),
    ],
)  # fmt: skip
def test_5_a_stamp_from_the_future_is_never_fresh(scenario: Any, cid: int, reason: str) -> None:
    decision = scenario().evaluate()
    assert decision.checks[cid - 1].reason == reason
    assert not decision.approved


def test_5_a_stamp_within_two_seconds_ahead_is_tolerated() -> None:
    decision = _day(mark_time=NOW + s(2)).evaluate()
    assert decision.checks[13].state is CheckState.PASSED
