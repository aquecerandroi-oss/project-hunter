"""``MintEventState.absorb`` (T4.79, EXP-M22): the trade stream the event gate
already folds feeds the absorption tracker; a gap propagates; ``build_event_row``
carries the readings onto the ``GateRow``; ``RuleSetSpec`` reads the two
switches; ``evaluate_gate`` refuses by name (unknown on the 15-second row,
``absorb_not_confirmed``/``absorb_sell_not_seen`` on the event row) and the
proposal's decomposition carries the ``absorb`` block; the event lane's cache
keeps the two arms because they are on the 15-second clock."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_meme_worker.absorb import COVERAGE_GAP, RECOVERING
from hunter_meme_worker.absorb_rules import (
    REFUSAL_ABSORB_NOT_CONFIRMED,
    REFUSAL_ABSORB_SELL_NOT_SEEN,
    REFUSAL_ABSORB_UNKNOWN,
)
from hunter_meme_worker.event_gate_caches import EventGateCaches, refresh_event_gate_caches
from hunter_meme_worker.event_gate_rows import EventReserves, build_event_row
from hunter_meme_worker.event_state import MintEventState
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.proposals import evaluate_gate

from .test_proposals_flow import FLOW_PARAMS, _fast_row, _flow_spec

pytestmark = pytest.mark.unit

MINT = "AbsorbMint111111111111111111111111111111111"
CREATOR = "CreatorWa11etAddress1111111111111111111111"
BORN = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)


def _trade(
    s: float,
    side: str,
    lamports: int,
    *,
    v_sol: str,
    v_tok: str,
    real: str,
    tokens: str | None = "20000000",
    trader: str = "Trader111111111111111111111111111111111111",
) -> NormalizedCurveTrade:
    at = BORN + timedelta(seconds=s)
    return NormalizedCurveTrade(
        mint=MINT,
        slot=1000 + int(s),
        signature=f"sig-{s}-{side}",
        trader=trader,
        side=side,  # type: ignore[arg-type]
        lamports=Decimal(lamports),
        token_amount=None if tokens is None else Decimal(tokens),
        virtual_sol_reserves=Decimal(v_sol),
        virtual_token_reserves=Decimal(v_tok),
        real_sol_reserves=Decimal(real),
        real_token_reserves=Decimal("700000000"),
        creator=CREATOR,
        mayhem=False,
        block_time=at,
        received_at=at + timedelta(milliseconds=400),
    )


def _state() -> MintEventState:
    return MintEventState(mint=MINT, subscribed_at=BORN, first_seen_at=BORN, creator=CREATOR)


def _large_sell(state: MintEventState) -> None:
    """A 10 % sell at 40 s (1 SOL out of 10 real; level 40 / 800 M)."""
    state.apply_trade(_trade(40, "sell", 1_000_000_000, v_sol="39", v_tok="820000000", real="9"))


def _absorbed(state: MintEventState) -> None:
    """The sell, then back at the level at 50 s — held through 60 s."""
    _large_sell(state)
    state.apply_trade(_trade(50, "buy", 500_000_000, v_sol="40", v_tok="800000000", real="9.5"))


def test_the_state_feeds_the_tracker_from_the_same_trades_and_a_gap_propagates() -> None:
    state = _state()
    state.apply_trade(_trade(10, "buy", 1_000_000_000, v_sol="41", v_tok="780000000", real="11"))
    f = state.absorb_features(BORN + timedelta(seconds=11))
    assert (f.sell_seen, f.confirmed) == (False, False)
    _large_sell(state)
    f = state.absorb_features(BORN + timedelta(seconds=45))
    assert (f.sell_seen, f.confirmed, f.reason) == (True, False, RECOVERING)
    assert f.sell_share == Decimal("0.1"), "1 SOL out of 10 pre-sell real SOL"
    state.apply_trade(_trade(50, "buy", 500_000_000, v_sol="40", v_tok="800000000", real="9.5"))
    f = state.absorb_features(BORN + timedelta(seconds=60))
    assert (f.sell_seen, f.confirmed, f.reason) == (True, True, None)
    assert f.confirmed_at == BORN + timedelta(seconds=60)
    state.mark_gap(BORN + timedelta(seconds=61))
    f = state.absorb_features(BORN + timedelta(seconds=62))
    assert (f.sell_seen, f.confirmed, f.reason) == (None, None, COVERAGE_GAP)


def test_the_event_row_carries_the_readings_and_the_base_row_has_none() -> None:
    state = _state()
    state.total_supply = Decimal("1000000000")
    _absorbed(state)
    base = _passing_row()
    assert base.absorb is None, "a 15-second row never carries an absorption reading"
    as_of = BORN + timedelta(seconds=60)
    row = build_event_row(
        base,
        state,
        as_of=as_of,
        reserves=EventReserves(Decimal("40"), Decimal("800000000")),
        holders_readings=[],
    )
    assert row.absorb is not None
    assert (row.absorb.sell_seen, row.absorb.confirmed) == (True, True)
    assert row.absorb.sell_at == BORN + timedelta(seconds=40)


def test_the_spec_reads_the_two_switches_off_by_default() -> None:
    spec = _flow_spec()
    assert (spec.require_absorb_confirmed, spec.require_absorb_sell_seen) == (False, False)
    params: dict[str, Any] = dict(_flow_params())
    params["require_absorb_confirmed"] = True
    treatment = _spec_of("absorb_v0", "1", params)
    assert (treatment.require_absorb_confirmed, treatment.require_absorb_sell_seen) == (True, False)


def _flow_params() -> dict[str, Any]:
    return dict(FLOW_PARAMS)


def _spec_of(name: str, version: str, params: dict[str, Any]) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id=f"rs-{name}-{version}",
        name=name,
        version=version,
        kind="research_only",
        exp_ref="EXP-M22",
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params=params,
    )


def _arms() -> tuple[RuleSetSpec, RuleSetSpec]:
    params = _flow_params()
    treatment = _spec_of("absorb_v0", "1", {**params, "require_absorb_confirmed": True})
    control = _spec_of("absorb_v0", "2", {**params, "require_absorb_sell_seen": True})
    return treatment, control


def _passing_row(**overrides: Any) -> Any:
    """``test_proposals_flow``'s own row that passes the flow gate, on this mint."""
    return _fast_row(mint=MINT, **overrides)


def _refusals(spec: RuleSetSpec, row: Any) -> dict[str, int]:
    now = row.end_time + timedelta(seconds=1)
    outcome = evaluate_gate(spec, [row], now=now, ttl_s=120, already_open=frozenset())
    return dict(outcome.refusals)


def test_both_arms_refuse_unknown_on_a_row_without_readings() -> None:
    treatment, control = _arms()
    row = _passing_row()
    assert _refusals(_flow_spec(), row) == {}, "the base row passes the flow gate"
    assert _refusals(treatment, row) == {REFUSAL_ABSORB_UNKNOWN: 1}
    assert _refusals(control, row) == {REFUSAL_ABSORB_UNKNOWN: 1}


def test_the_arms_refuse_by_name_and_the_proposal_carries_the_block() -> None:
    treatment, control = _arms()
    state = _state()
    state.apply_trade(_trade(10, "buy", 1_000_000_000, v_sol="41", v_tok="780000000", real="11"))
    quiet = replace(_passing_row(), absorb=state.absorb_features(BORN + timedelta(seconds=20)))
    assert _refusals(treatment, quiet) == {REFUSAL_ABSORB_NOT_CONFIRMED: 1}
    assert _refusals(control, quiet) == {REFUSAL_ABSORB_SELL_NOT_SEEN: 1}
    _large_sell(state)
    just_sold = replace(_passing_row(), absorb=state.absorb_features(BORN + timedelta(seconds=41)))
    assert _refusals(treatment, just_sold) == {REFUSAL_ABSORB_NOT_CONFIRMED: 1}
    assert _refusals(control, just_sold) == {}, "the control enters right after the sell"
    state.apply_trade(_trade(50, "buy", 500_000_000, v_sol="40", v_tok="800000000", real="9.5"))
    confirmed = replace(_passing_row(), absorb=state.absorb_features(BORN + timedelta(seconds=75)))
    outcome = evaluate_gate(
        treatment, [confirmed], now=confirmed.end_time, ttl_s=120, already_open=frozenset()
    )
    assert dict(outcome.refusals) == {} and len(outcome.drafts) == 1
    block = next(r for r in outcome.drafts[0].reasons if r.get("feature") == "absorb")
    assert (block["sell_seen"], block["confirmed"], block["sells_seen"]) == (False, True, 1)
    assert block["sell_at"] == (BORN + timedelta(seconds=40)).isoformat()
    assert block["confirmed_at"] == (BORN + timedelta(seconds=60)).isoformat()
    assert (block["min_sell_share"], block["recovery_window_s"], block["hold_s"]) == (
        "0.05",
        30,
        10,
    )
    assert _refusals(control, confirmed) == {REFUSAL_ABSORB_SELL_NOT_SEEN: 1}, (
        "the control's window closed 30 s after the sell (at 70 s); the signal lives to 120 s"
    )
    plain = evaluate_gate(
        _flow_spec(), [confirmed], now=confirmed.end_time, ttl_s=120, already_open=frozenset()
    )
    assert not any(r.get("feature") == "absorb" for r in plain.drafts[0].reasons), (
        "a set that does not ask keeps its frozen decomposition"
    )


def test_the_event_lane_cache_keeps_the_two_arms() -> None:
    treatment, control = _arms()
    caches = EventGateCaches()
    refresh_event_gate_caches(
        caches,
        specs=[treatment, control],
        rows=[],
        open_mints={},
        pedigree={},
        e2b=None,
        now=BORN,
    )
    assert [spec.label for spec in caches.specs] == ["absorb_v0/1", "absorb_v0/2"]
