"""T4.80 (R65/KB-0147): the optional ``max_buys_1m`` ceiling, end to end in
the worker — ``RuleSetSpec`` reads the key (absent = off, a decimal or a
negative refused before the table), both lanes judge the count **observed at
the decision instant** (the 15-second/operator lane from ``buys_60s``, the
event lane from the same ``tape_minute`` fold the flow criteria already use),
an unmeasured count refuses ``buys_1m_unknown``, the refusal is counted per
set so shadow can measure it, the trail decodes ``(value, limit)`` and the
proposal's decomposition names the ceiling.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_indicators.meme.rules_buys import REFUSAL_BUYS_ABOVE_MAX, REFUSAL_BUYS_UNKNOWN
from hunter_meme_worker.event_gate_rows import EventReserves, build_event_row
from hunter_meme_worker.event_state import MintEventState
from hunter_meme_worker.gate_refusal_trail import decode_value_limit
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.proposals import entry_features_of, evaluate_gate

from .test_proposals_flow import FLOW_PARAMS, _fast_row, _flow_spec

pytestmark = pytest.mark.unit

MINT = "BuysMint1111111111111111111111111111111111"
CREATOR = "CreatorWa11etAddress1111111111111111111111"
BORN = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
CEILING = 25
"""R65 §Q2: ``buys_1m <= 25`` — 34 % de alvos e MFE mediano +28,1 %."""


def _spec(**overrides: Any) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id="01994d00-6c1a-7000-8000-00000000t480",
        name="flow_v2",
        version="11",
        kind="research_only",
        exp_ref="EXP-M23",
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params={**FLOW_PARAMS, **overrides},
    )


def _refusals(spec: RuleSetSpec, row: Any) -> dict[str, int]:
    outcome = evaluate_gate(
        spec, [row], now=row.end_time + timedelta(seconds=1), ttl_s=120, already_open=frozenset()
    )
    return dict(outcome.refusals)


# ---- the parameter ----------------------------------------------------------------


def test_absent_is_off_and_an_int_is_read_as_an_int() -> None:
    assert _flow_spec().gate.max_buys_1m is None, "every set frozen before T4.80"
    assert _spec(max_buys_1m=CEILING).gate.max_buys_1m == CEILING


def test_a_decimal_or_a_negative_ceiling_never_loads() -> None:
    with pytest.raises(TypeError, match="max_buys_1m is a count"):
        _spec(max_buys_1m=25.5)
    with pytest.raises(TypeError, match="max_buys_1m is a count"):
        _spec(max_buys_1m="25")  # counts are bare JSON ints, not decimal-strings
    with pytest.raises(TypeError, match="max_buys_1m is a count"):
        _spec(max_buys_1m=True)
    with pytest.raises(ValueError, match="max_buys_1m cannot be negative"):
        _spec(max_buys_1m=-1)


# ---- the 15-second (Lab/operator) lane ---------------------------------------------


def test_the_criterion_absent_changes_the_15s_lane_not_at_all() -> None:
    """Regression over the gate fixture of T4.16: the same row, the same set,
    the same single draft and a decomposition that never mentions the key."""
    row = _fast_row()
    frozen = evaluate_gate(
        _flow_spec(), [row], now=row.end_time, ttl_s=120, already_open=frozenset()
    )
    assert dict(frozen.refusals) == {} and len(frozen.drafts) == 1
    flow = next(r for r in frozen.drafts[0].reasons if r.get("feature") == "flow")
    assert "max_buys_1m" not in flow


def test_the_15s_lane_passes_at_the_ceiling_and_refuses_above_it() -> None:
    spec = _spec(max_buys_1m=CEILING)
    at_ceiling = _fast_row(buys_1m=CEILING, sells_1m=10, unique_buyers_1m=CEILING)
    assert _refusals(spec, at_ceiling) == {}, "R65's own '<= 25' includes 25"
    crowded = _fast_row(buys_1m=CEILING + 1, sells_1m=10, unique_buyers_1m=CEILING + 1)
    assert _refusals(spec, crowded) == {REFUSAL_BUYS_ABOVE_MAX: 1}


def test_the_15s_lane_refuses_a_count_it_could_not_read() -> None:
    blind = _fast_row(buys_1m=None, sells_1m=None, tape_reason="not_polled")
    refusals = _refusals(_spec(max_buys_1m=CEILING), blind)
    assert refusals[REFUSAL_BUYS_UNKNOWN] == 1, "a tape nobody read is not 'nobody bought'"


def test_the_decomposition_names_the_ceiling_it_was_judged_against() -> None:
    row = _fast_row(buys_1m=12)
    outcome = evaluate_gate(
        _spec(max_buys_1m=CEILING), [row], now=row.end_time, ttl_s=120, already_open=frozenset()
    )
    flow = next(r for r in outcome.drafts[0].reasons if r.get("feature") == "flow")
    assert (flow["buys_1m"], flow["max_buys_1m"]) == (12, CEILING)


def test_the_trail_decodes_the_count_and_the_ceiling() -> None:
    spec = _spec(max_buys_1m=CEILING)
    features = entry_features_of(_fast_row(buys_1m=40), spec)
    assert decode_value_limit(REFUSAL_BUYS_ABOVE_MAX, features, spec.gate) == (40, CEILING)


# ---- the event lane ----------------------------------------------------------------


def _trade(s: float, side: str, *, trader: str, lag_s: float = 0.4) -> NormalizedCurveTrade:
    at = BORN + timedelta(seconds=s)
    return NormalizedCurveTrade(
        mint=MINT,
        slot=1000 + int(s),
        signature=f"sig-{s}-{side}-{trader}",
        trader=trader,
        side=side,  # type: ignore[arg-type]
        lamports=Decimal(100_000_000),
        token_amount=Decimal("20000000"),
        virtual_sol_reserves=Decimal("40"),
        virtual_token_reserves=Decimal("800000000"),
        real_sol_reserves=Decimal("10"),
        real_token_reserves=Decimal("700000000"),
        creator=CREATOR,
        mayhem=False,
        block_time=at,
        received_at=at + timedelta(seconds=lag_s),
    )


def _state_with_buys(count: int) -> MintEventState:
    """``count`` distinct buys inside the 60 s ending at ``BORN + 90 s``."""
    state = MintEventState(mint=MINT, subscribed_at=BORN, first_seen_at=BORN, creator=CREATOR)
    state.total_supply = Decimal("1000000000")
    for i in range(count):
        state.apply_trade(_trade(40 + i * 0.5, "buy", trader=f"Buyer{i:03d}"))
    return state


def _event_row(state: MintEventState, *, as_of: datetime) -> Any:
    return build_event_row(
        replace(_fast_row(), mint=MINT),
        state,
        as_of=as_of,
        reserves=EventReserves(Decimal("40"), Decimal("800000000")),
        holders_readings=[],
    )


def _added_by_the_ceiling(row: Any) -> set[str]:
    """What the criterion adds to the very same row's refusals — the control
    is the same set with the key absent, so nothing else may move."""
    control = set(_refusals(_spec(), row))
    return set(_refusals(_spec(max_buys_1m=CEILING), row)) - control


def test_the_event_lane_reads_the_same_count_from_its_own_minute() -> None:
    as_of = BORN + timedelta(seconds=90)
    row = _event_row(_state_with_buys(CEILING), as_of=as_of)
    assert row.buys_1m == CEILING, "the tape fold of the 60 s ending at the decision instant"
    assert _added_by_the_ceiling(row) == set()
    crowded = _event_row(_state_with_buys(CEILING + 1), as_of=as_of)
    assert crowded.buys_1m == CEILING + 1
    assert _added_by_the_ceiling(crowded) == {REFUSAL_BUYS_ABOVE_MAX}


def test_the_event_lane_counts_only_what_happened_before_the_decision() -> None:
    """No look-ahead: a buy at 95 s is invisible to a decision taken at 90 s."""
    state = _state_with_buys(CEILING)
    state.apply_trade(_trade(95, "buy", trader="LateBuyer"))
    row = _event_row(state, as_of=BORN + timedelta(seconds=90))
    assert row.buys_1m == CEILING
    assert _added_by_the_ceiling(row) == set()
    later = _event_row(state, as_of=BORN + timedelta(seconds=96))
    assert later.buys_1m == CEILING + 1, "the same state, judged after the late buy"
    assert _added_by_the_ceiling(later) == {REFUSAL_BUYS_ABOVE_MAX}


def test_a_trade_that_only_reached_us_after_the_decision_is_not_counted() -> None:
    """The other half of "no look-ahead" (Astra, T4.80): a buy that *happened*
    inside the judged minute but landed on our socket two seconds later is not
    in the count — ``tape_for`` keeps only ``received_at <= end_time``."""
    state = _state_with_buys(CEILING)
    state.apply_trade(_trade(89, "buy", trader="SlowToArrive", lag_s=2))
    row = _event_row(state, as_of=BORN + timedelta(seconds=90))
    assert row.buys_1m == CEILING
    assert _added_by_the_ceiling(row) == set()


def test_the_event_lane_refuses_while_its_tape_is_still_warming() -> None:
    state = _state_with_buys(3)
    row = _event_row(state, as_of=BORN + timedelta(seconds=45))
    assert row.buys_1m is None and row.tape_reason is not None
    assert _added_by_the_ceiling(row) == {REFUSAL_BUYS_UNKNOWN}
