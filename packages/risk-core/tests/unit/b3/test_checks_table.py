"""docs/RISK_ENGINE_B3.md §8.2: each of the 25 checks passes once and fails once, and,
where the contract names an ``unavailable`` reason, is unavailable once — with exactly
the contract's ``reason``. Every case also proves the decision still carries all 25
checks (no short-circuit after the first refusal) and is rejected."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_b3 import (
    AuthorityPhase,
    AuthorityView,
    CheckState,
    LastReconcile,
    OrderCheckResult,
    Side,
    SpecStatus,
    TradeMode,
)

from . import factories as fx
from .factories import NOW, s
from .mutators import (
    Mut,
    acc,
    both,
    brk,
    cal,
    clock,
    dy,
    k,
    lim,
    mg,
    op,
    order_of,
    position_of,
    prop,
    q,
    same,
    ses,
    sp,
    term,
)

pytestmark = pytest.mark.unit

P, F, U = CheckState.PASSED, CheckState.FAILED, CheckState.UNAVAILABLE


@dataclass(frozen=True)
class Case:
    check: int
    label: str
    mutate: Mut
    state: CheckState
    reason: str | None


SELL = prop(side=Side.SELL, ref_price=Decimal("207000"), stop_price=Decimal("208030"))
D = Decimal

CASES: list[Case] = [
    # 1 kill_switch
    Case(1, "active", same, P, None),
    Case(1, "warning passes", k(robot=KillSwitchState.WARNING), P, None),
    Case(1, "disabled", k(organization=KillSwitchState.TRADING_DISABLED), F, "kill_switch_trading_disabled"),
    Case(1, "emergency", k(system=KillSwitchState.EMERGENCY), F, "kill_switch_emergency"),
    Case(1, "management only", k(authority=AuthorityView(phase=AuthorityPhase.MANAGEMENT, instance_id=fx.INSTANCE, authority_expires_at=NOW + s(60))), F, "entries_not_armed"),
    Case(1, "other instance", k(authority=AuthorityView(phase=AuthorityPhase.ENTRIES, instance_id=fx.ORG, authority_expires_at=NOW + s(60))), F, "arming_other_instance"),
    Case(1, "expired", k(authority=AuthorityView(phase=AuthorityPhase.ENTRIES, instance_id=fx.INSTANCE, authority_expires_at=NOW)), F, "authority_expired"),
    # 2 account_mode
    Case(2, "demo", same, P, None),
    Case(2, "real with K1", both(acc(trade_mode=TradeMode.REAL), k(k1_present=True)), P, None),
    Case(2, "mismatch", acc(account_hash="b" * 64), F, "account_mismatch"),
    Case(2, "real without K1", acc(trade_mode=TradeMode.REAL), F, "real_account_without_k1"),
    Case(2, "contest", acc(trade_mode=TradeMode.CONTEST), F, "account_mode_unsupported"),
    Case(2, "unreadable", acc(read_ok=False), U, "account_unreadable"),
    # 3 terminal_state
    Case(3, "ok", same, P, None),
    Case(3, "disconnected", term(connected=False), F, "terminal_disconnected"),
    Case(3, "algo off", term(trade_allowed=False), F, "algo_trading_off"),
    Case(3, "tradeapi disabled", term(tradeapi_disabled=True), F, "tradeapi_disabled"),
    Case(3, "unreadable", term(read_ok=False), U, "terminal_unreadable"),
    # 4 symbol_whitelist
    Case(4, "current WIN", same, P, None),
    Case(4, "old contract", prop(symbol="WINV26"), F, "symbol_not_current_contract"),
    Case(4, "root not allowed", lim(symbol_roots=("WDO",)), F, "symbol_root_not_allowed"),
    Case(4, "close only", sp(now={"trade_mode": "SYMBOL_TRADE_MODE_CLOSEONLY"}), F, "symbol_trade_mode_restricted"),
    Case(4, "expiry day", cal(is_expiry_day=True), F, "contract_expiry_day"),
    Case(4, "no contract", cal(current_contract=None), U, "contract_calendar_missing"),
    # 5 trading_day
    Case(5, "normal day", same, P, None),
    Case(5, "shortened with grid", cal(is_shortened=True), P, None),
    Case(5, "holiday", cal(is_holiday=True), F, "holiday"),
    Case(5, "shortened without grid", cal(is_shortened=True, has_grid=False), F, "shortened_session_without_grid"),
    Case(5, "no grid", cal(has_grid=False), U, "session_grid_missing"),
    Case(5, "calendar unreadable", cal(read_ok=False), U, "calendar_unreadable"),
    # 6 entry_window
    Case(6, "inside", same, P, None),
    Case(6, "first minutes", ses(open_utc=NOW - s(60)), F, "before_entry_window"),
    Case(6, "after cutoff", ses(entry_cutoff_utc=NOW - s(1)), F, "after_entry_cutoff"),
    Case(6, "outside strategy window", prop(entry_window_end_utc=NOW - s(1)), F, "outside_strategy_window"),
    Case(6, "no grid upstream", cal(has_grid=False), U, "upstream_unavailable:5"),
    # 7 flatten_margin
    Case(7, "enough margin", same, P, None),
    Case(7, "too close", ses(flatten_at_utc=NOW + s(14 * 60)), F, "too_close_to_flatten"),
    Case(7, "after rico cutoff", ses(rico_flatten_utc=datetime(2026, 10, 20, 20, 9, tzinfo=UTC)), F, "flatten_after_rico_cutoff"),
    Case(7, "unset (D6)", ses(flatten_at_utc=None), U, "flatten_schedule_unset"),
    # 8 quote_fresh
    Case(8, "fresh", same, P, None),
    Case(8, "crossed book", q(bid=D("207005"), ask=D("207005")), F, "quote_invalid"),
    Case(8, "zero bid", q(bid=D("0")), F, "quote_invalid"),
    Case(8, "stale", q(time_utc=NOW - s(6)), F, "quote_stale"),
    Case(8, "future", q(time_utc=NOW + s(3)), F, "quote_from_future"),
    Case(8, "offset exceeded", clock(offset_ms=2001), F, "clock_offset_exceeded"),
    Case(8, "missing", q(read_ok=False, bid=None, ask=None, last=None, time_utc=None), U, "quote_missing"),
    Case(8, "clock unmeasured", clock(ok=False), U, "clock_offset_unmeasured"),
    Case(8, "clock measurement too old", clock(measured_at=NOW - s(901)), U, "clock_offset_unmeasured"),
    # 9 spread
    Case(9, "tight", same, P, None),
    Case(9, "wide", q(bid=D("206990")), F, "spread_too_wide"),
    Case(9, "no quote", q(read_ok=False, bid=None, ask=None, last=None, time_utc=None), U, "upstream_unavailable:8"),
    # 10 open_positions
    Case(10, "flat", same, P, None),
    Case(10, "ours open", brk(positions=(position_of(),)), F, "position_already_open"),
    Case(10, "foreign", brk(positions=(position_of(magic=0),)), F, "foreign_position_present"),
    Case(10, "unreadable", brk(positions_ok=False), U, "positions_unreadable"),
    # 11 order_in_flight
    Case(11, "nothing in flight", same, P, None),
    Case(11, "our pending", brk(orders=(order_of(),)), F, "pending_order_present"),
    Case(11, "foreign order", brk(orders=(order_of(magic=0),)), F, "foreign_order_present"),
    Case(11, "intent in flight", op(open_entry_intents=1), F, "entry_intent_in_flight"),
    Case(11, "intent unknown", op(unknown_intents=1), F, "entry_intent_unknown"),
    Case(11, "orphan sltp", op(orphan_sltp_unknown=frozenset({"WINZ26"})), F, "orphan_sltp_unknown"),
    Case(11, "orphan elsewhere", op(orphan_sltp_unknown=frozenset({"WDOZ26"})), P, None),
    Case(11, "unreadable", brk(orders_ok=False), U, "orders_unreadable"),
    # 12 contracts_caps
    Case(12, "one", same, P, None),
    Case(12, "zero", prop(requested_contracts=0), F, "requested_contracts_invalid"),
    Case(12, "above cap", prop(requested_contracts=2), F, "contracts_cap_exceeded"),
    # 13 trades_today
    Case(13, "first", same, P, None),
    Case(13, "reached", op(entries_today=1), F, "max_trades_per_day_reached"),
    Case(13, "history incomplete", dy(history_complete=False), U, "trade_count_unavailable"),
    # 14 daily_loss
    Case(14, "no loss", same, P, None),
    Case(14, "limit reached", dy(realized_gross_brl=D("-9000"), equity_delta_brl=D("-9000")), F, "daily_loss_limit"),
    Case(14, "no anchor", dy(anchor_equity=None), U, "day_anchor_missing"),
    Case(14, "yesterday's anchor", dy(anchor_at=datetime(2026, 10, 19, 12, 55, tzinfo=UTC)), U, "day_anchor_missing"),
    Case(14, "history incomplete", dy(history_complete=False), U, "session_history_incomplete"),
    Case(14, "realized missing", dy(realized_gross_brl=None), U, "session_history_incomplete"),
    Case(14, "divergent", dy(equity_delta_brl=D("-6")), U, "pnl_reconcile_divergent"),
    Case(14, "mark stale", dy(mark_time=NOW - s(6)), U, "mark_stale"),
    Case(14, "mark missing", dy(open_mtm_gross_brl=None), U, "mark_stale"),
    # 15 stop_geometry
    Case(15, "buy stop", same, P, None),
    Case(15, "sell stop", SELL, P, None),
    Case(15, "valid target", prop(target_price=D("208000")), P, None),
    Case(15, "missing", prop(stop_price=None), F, "stop_missing"),
    Case(15, "off tick", prop(stop_price=D("205976")), F, "stop_off_tick"),
    Case(15, "wrong side", prop(stop_price=D("207015")), F, "stop_wrong_side"),
    Case(15, "crossed", both(prop(stop_price=D("207000")), q(bid=D("207000"))), F, "stop_already_crossed"),
    Case(15, "too close", prop(stop_price=D("206965")), F, "stop_too_close"),
    Case(15, "too far", prop(stop_price=D("205005")), F, "stop_too_far"),
    Case(15, "target wrong side", prop(target_price=D("206000")), F, "target_invalid"),
    Case(15, "no quote", q(read_ok=False, bid=None, ask=None, last=None, time_utc=None), U, "upstream_unavailable:8"),
    # 16 trade_risk_vs_allowance
    Case(16, "fits allowance", same, P, None),
    Case(16, "exceeds allowance", dy(realized_gross_brl=D("-8800"), equity_delta_brl=D("-8800")), F, "trade_risk_exceeds_daily_allowance"),
    Case(16, "loss unknown", dy(anchor_equity=None), U, "upstream_unavailable:14"),
    Case(16, "no fee schedule", op(fee_schedule=fx.FeeSchedule(per_leg_brl=None, source=None, valid=False)), U, "fee_schedule_missing"),
    # 17 trade_risk_cap
    Case(17, "under cap", same, P, None),
    Case(17, "over cap", lim(max_loss_per_trade_brl=D("200")), F, "trade_risk_exceeds_cap"),
    Case(17, "no fee schedule", op(fee_schedule=fx.FeeSchedule(per_leg_brl=None, source=None, valid=False)), U, "fee_schedule_missing"),
    # 18 margin
    Case(18, "fits", same, P, None),
    Case(18, "not BRL", acc(currency="USD"), F, "account_currency_not_brl"),
    Case(18, "margin mode changed", acc(margin_mode="RETAIL_HEDGING"), F, "margin_mode_changed"),
    Case(18, "over allocation", lim(alloc_per_trade_brl=D("99")), F, "margin_exceeds_allocation"),
    Case(18, "over free margin", acc(margin_free=D("199")), F, "margin_exceeds_free_margin"),
    Case(18, "order_check refused", mg(order_check={1: OrderCheckResult(ok=False, reason="no_money")}), F, "order_check_refused"),
    Case(18, "unreadable", mg(read_ok=False), U, "margin_unavailable"),
    Case(18, "volume missing", mg(per_volume={2: D("200")}), U, "margin_unavailable"),
    # 19 broker_reject_breaker
    Case(19, "quiet", same, P, None),
    Case(19, "old rejects ignored", op(entry_rejects=(NOW - s(601),) * 5), P, None),
    Case(19, "tripped", op(entry_rejects=(NOW - s(10), NOW - s(20), NOW - s(30))), F, "broker_reject_breaker"),
    Case(19, "latched", op(breaker_latched=True), F, "broker_reject_breaker"),
    # 20 reconciliation_ok
    Case(20, "clean", same, P, None),
    Case(20, "divergent", op(last_reconcile=LastReconcile(at=NOW - s(1), clean=False, consistent_passes=2)), F, "reconciliation_divergent"),
    Case(20, "settling", op(last_reconcile=LastReconcile(at=NOW - s(1), clean=True, consistent_passes=1)), F, "reconciliation_settling"),
    Case(20, "stale", op(last_reconcile=LastReconcile(at=NOW - s(11), clean=True, consistent_passes=2)), U, "reconciliation_stale"),
    Case(20, "never", op(last_reconcile=None), U, "reconciliation_stale"),
    # 21 audit_path
    Case(21, "reachable", same, P, None),
    Case(21, "api unreachable", op(audit=fx.AuditPath(api_last_ok_at=NOW - s(16), buffer_len=0, buffer_writable=True)), F, "audit_api_unreachable"),
    Case(21, "buffer not empty", op(audit=fx.AuditPath(api_last_ok_at=NOW, buffer_len=1, buffer_writable=True)), F, "audit_buffer_not_empty"),
    Case(21, "buffer unwritable", op(audit=fx.AuditPath(api_last_ok_at=NOW, buffer_len=0, buffer_writable=False)), F, "audit_buffer_unwritable"),
    # 22 signal_validity
    Case(22, "valid", same, P, None),
    Case(22, "late", prop(signal_published_at=datetime(2026, 10, 20, 14, 31, tzinfo=UTC)), F, "signal_late"),
    Case(22, "outside window", prop(entry_window_start_utc=NOW + s(1)), F, "signal_outside_window"),
    Case(22, "not armed", k(armed_strategy=None), F, "strategy_not_armed"),
    Case(22, "other strategy", prop(strategy_key="other"), F, "strategy_not_armed"),
    Case(22, "version", prop(strategy_version=2), F, "strategy_version_mismatch"),
    Case(22, "params", prop(params_hash="q" * 64), F, "params_hash_mismatch"),
    Case(22, "stale proposal", prop(created_at=NOW - s(31)), F, "proposal_stale"),
    # 23 spec_unchanged
    Case(23, "unchanged", same, P, None),
    Case(23, "tick value changed", sp(now={"trade_tick_value": D("2")}), F, "spec_changed"),
    Case(23, "status changed", sp(now={"status": SpecStatus.CHANGED}), F, "spec_changed"),
    Case(23, "terminal", sp(now={"terminal_version": "5.0.5001"}), F, "terminal_version_changed"),
    Case(23, "package", sp(now={"package_version": "5.0.6"}), F, "package_version_changed"),
    Case(23, "unreadable", sp(now={"status": SpecStatus.UNREADABLE}), U, "spec_unreadable"),
    # 24 slippage_guard
    Case(24, "at touch", same, P, None),
    Case(24, "unproven lifecycle", sp(pin={"order_lifecycle_proven": False}, now={"order_lifecycle_proven": False}), F, "order_lifecycle_unproven"),
    Case(24, "ref off tick", prop(ref_price=D("207006")), F, "reference_off_tick"),
    Case(24, "drifted", prop(ref_price=D("207015")), F, "reference_drifted"),
    Case(24, "no quote", q(read_ok=False, bid=None, ask=None, last=None, time_utc=None), U, "upstream_unavailable:8"),
    # 25 equity_floor
    Case(25, "off", same, P, None),
    Case(25, "above floor", lim(equity_floor_brl=D("5000")), P, None),
    Case(25, "below floor", lim(equity_floor_brl=D("10001")), F, "equity_below_floor"),
    Case(25, "unreadable", both(lim(equity_floor_brl=D("5000")), acc(read_ok=False)), U, "account_unreadable"),
]  # fmt: skip


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.check:02d}-{c.label}")
def test_check_table(case: Case) -> None:
    decision = case.mutate(fx.scenario()).evaluate()
    assert len(decision.checks) == 25
    assert [c.id for c in decision.checks] == list(range(1, 26))
    got = decision.checks[case.check - 1]
    assert (got.state, got.reason) == (case.state, case.reason), got
    if case.state is not P:
        assert not decision.approved
        assert case.reason in decision.reasons


def test_every_check_has_a_passing_and_a_failing_case() -> None:
    for check_id in range(1, 26):
        states = {c.state for c in CASES if c.check == check_id}
        assert P in states, check_id
        assert F in states, check_id


def test_every_unavailable_reason_of_the_contract_has_a_case() -> None:
    covered = {c.reason for c in CASES if c.state is U}
    expected = {
        "account_unreadable", "terminal_unreadable", "contract_calendar_missing",
        "session_grid_missing", "calendar_unreadable", "flatten_schedule_unset", "quote_missing",
        "clock_offset_unmeasured", "upstream_unavailable:8", "positions_unreadable",
        "orders_unreadable", "trade_count_unavailable", "day_anchor_missing",
        "session_history_incomplete", "pnl_reconcile_divergent", "mark_stale",
        "upstream_unavailable:14", "fee_schedule_missing", "margin_unavailable",
        "reconciliation_stale", "spec_unreadable",
    }  # fmt: skip
    assert expected <= covered


def test_the_base_scenario_is_approved_with_one_contract() -> None:
    decision = fx.scenario().evaluate()
    assert decision.approved, decision.reasons
    assert decision.reasons == ()
    assert decision.sizing is not None
    assert decision.sizing.n_final == 1
    assert decision.expires_at == NOW + timedelta(seconds=30)
    assert decision.approved_at == NOW
    assert decision.grid_version == "grid-2026-10-13"
    assert decision.limits_version == "test-v1"
    assert decision.spec_pin_id == "pin-1"


def test_reasons_follow_check_ids_and_all_checks_survive_the_first_refusal() -> None:
    sc = both(k(robot=KillSwitchState.EMERGENCY), acc(read_ok=False), prop(stop_price=None))(
        fx.scenario()
    )
    decision = sc.evaluate()
    assert decision.reasons[:3] == ("kill_switch_emergency", "account_unreadable", "stop_missing")
    assert len(decision.checks) == 25
    assert decision.checks[2].state is P  # terminal still evaluated after two refusals
