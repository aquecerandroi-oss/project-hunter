"""Pricing and shape of a copy's bet (H-037) with the Lab's own machinery: priced at the market at
the pricing instant (not the leader's fill), the Mayhem cap stamp from ``close_bet``, a censored exit
that guesses no price, a pool sale through ``pool_mark``. Pure."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_indicators.meme.pool import PoolTrade
from hunter_meme_worker.copy_bets import (
    bet_state_of,
    build_entry,
    censored_exit,
    close_on_curve,
    close_on_pool_trade,
    inert_lab_params,
    snapshot_of,
)
from hunter_meme_worker.copy_events import CloseIntent, OpenIntent, leader_ref
from hunter_meme_worker.copy_spec import CopySpec
from hunter_meme_worker.lab_values import SELL_CAP_MODEL

from .copy_support import LEADER_A, MINT_1, T0, buy, make_spec

pytestmark = pytest.mark.unit


def _state(
    *, vsol: str, vtok: str, real_sol: str, mayhem: bool | None, at: datetime = T0
) -> NormalizedCurveState:  # type: ignore[no-untyped-def]
    return NormalizedCurveState(
        mint=MINT_1,
        virtual_sol_reserves=Decimal(vsol),
        virtual_token_reserves=Decimal(vtok),
        real_sol_reserves=Decimal(real_sol),
        real_token_reserves=Decimal("700000000"),
        total_supply=Decimal("1000000000"),
        complete=False,
        market_cap_sol=Decimal("30"),
        source="solana_rpc",
        mayhem_enabled=mayhem,
        observed_at=at,
        received_at=at,
    )


def _open_intent(latency_ms: int = 300) -> tuple[OpenIntent, CopySpec]:
    spec = make_spec(exec_latency_s=str(Decimal(latency_ms) / 1000))
    event = buy(at=T0)
    decided = T0 + timedelta(milliseconds=4)
    intent = OpenIntent(
        "k1", MINT_1, leader_ref(event, "A"), decided, decided + timedelta(milliseconds=latency_ms)
    )
    return intent, spec


def test_the_entry_is_priced_on_the_market_at_the_pricing_instant_not_the_leaders_fill() -> None:
    intent, spec = _open_intent()
    later = intent.target_at + timedelta(milliseconds=40)
    snap = snapshot_of(_state(vsol="31", vtok="1036000000", real_sol="1", mayhem=False, at=later))
    entry = build_entry(spec, snap, intent, queued_at=intent.decided_at, slot=777)
    assert entry.entry_at == later  # the state we paid is the one read after decision + latency
    assert entry.sol_spent > spec.size_sol - Decimal("0.0001")
    # the priority fee is charged once on the leg, like paper_fill._build_entry does
    assert Decimal(entry.entry["priority_fee_sol"]) == spec.priority_fee_sol == Decimal("0.00005")
    assert entry.sol_spent == Decimal(entry.entry["sol_spent"])
    copy = entry.entry["copy"]
    assert copy["leader_signature"] == intent.leader.signature
    assert copy["leader_wallet"] == LEADER_A and copy["leader"]["stratum"] == "A"
    assert copy["declared_execution_latency_ms"] == 300
    assert copy["priced_slot"] == 777 and copy["leader_slot"] == intent.leader.slot
    ts = copy["ts"]
    assert ts["decided_at"].split(".")[1].startswith("004")
    assert ts["priced_at"] == later.isoformat(timespec="milliseconds")
    assert set(ts) == {
        "leader_block_time", "observed_at", "first_seen_at", "fields_complete_at", "server_ts",
        "decided_at", "target_at", "queued_at", "priced_at", "persisted_at",
    }  # fmt: skip
    assert copy["latency_ms"]["decided_to_priced_ms"] == 340.0  # 300 declared + 40 read
    assert entry.entry["sell_cap_model"] == SELL_CAP_MODEL


def test_the_lab_never_fires_an_exit_on_a_copy_bet() -> None:
    params = inert_lab_params(make_spec(time_cap_s=600))
    rules = params.exit_rules()  # constructs: the numbers are valid
    assert rules.target_multiple >= 1_000_000 and params.exit_on_migration is False
    assert params.exit_on_creator_dump is False and params.max_hold_s > 600 + 86_400


def test_the_exit_goes_through_close_bet_and_a_mayhem_curve_gets_the_cap_stamp() -> None:
    intent, spec = _open_intent()
    entry_snap = snapshot_of(_state(vsol="30", vtok="1073000000", real_sol="0.5", mayhem=True))
    entry = build_entry(spec, entry_snap, intent, queued_at=intent.decided_at, slot=777)
    state = bet_state_of(bet_id="b", rule_set_id="rs", mint=MINT_1, entry=entry, mayhem=True)
    close = CloseIntent(
        "k1", MINT_1, "leader_exit_full", intent.leader, T0 + timedelta(seconds=30),
        T0 + timedelta(seconds=30), None,
    )  # fmt: skip
    exit_snap = snapshot_of(
        _state(
            vsol="30", vtok="1073000000", real_sol="0.5", mayhem=True, at=T0 + timedelta(seconds=31)
        )
    )
    closed = close_on_curve(state, exit_snap, close)
    assert closed.exit["sell_cap_model"] == SELL_CAP_MODEL  # the fixed Mayhem cap is applied
    assert closed.exit["own_curve_sol"] == entry.entry["curve_cost_sol"]
    assert closed.exit["reason"] == "leader_exit_full"
    assert closed.exit["copy"]["trigger"] == "copy_leader"
    assert closed.exit["copy"]["leader_signature"] == intent.leader.signature
    assert closed.exit_at == exit_snap.observed_at


def test_a_censored_exit_prices_nothing_and_is_indeterminate_with_its_reason() -> None:
    intent, spec = _open_intent()
    snap = snapshot_of(_state(vsol="30", vtok="1073000000", real_sol="0.5", mayhem=False))
    entry = build_entry(spec, snap, intent, queued_at=intent.decided_at, slot=777)
    state = bet_state_of(bet_id="b", rule_set_id="rs", mint=MINT_1, entry=entry, mayhem=False)
    close = CloseIntent("k1", MINT_1, "leader_exit_full", intent.leader, T0, T0, "leader_gap_exit")
    closed = censored_exit(state, close, censor="leader_gap_exit", now=T0 + timedelta(seconds=2))
    assert closed.outcome_quality == "indeterminate"
    assert closed.outcome_quality_reason == "leader_gap_exit"
    assert closed.exit["sol_received"] == "0" and closed.exit["snapshot"] is None
    assert closed.pnl_sol == -entry.sol_spent


def test_a_migrated_mint_is_sold_on_the_pool_trade_with_the_pool_marks_arithmetic() -> None:
    intent, spec = _open_intent()
    snap = snapshot_of(_state(vsol="30", vtok="1073000000", real_sol="0.5", mayhem=False))
    entry = build_entry(spec, snap, intent, queued_at=intent.decided_at, slot=777)
    state = bet_state_of(bet_id="b", rule_set_id="rs", mint=MINT_1, entry=entry, mayhem=False)
    when = T0 + timedelta(minutes=2)
    trade = PoolTrade(
        block_time=when, received_at=when, side="buy", sol=Decimal("1"), tokens=Decimal("30000000")
    )
    close = CloseIntent("k1", MINT_1, "leader_exit_full", intent.leader, when, when, None)
    closed = close_on_pool_trade(state, trade, [trade], close)
    assert closed.exit["venue"] == "pump_amm" and closed.exit["fill"] == "next_trade"
    assert closed.exit_at == when and closed.exit["copy"]["trigger"] == "copy_leader"
