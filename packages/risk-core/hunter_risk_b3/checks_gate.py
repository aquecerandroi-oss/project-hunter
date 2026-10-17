"""Checks 1–8 of docs/RISK_ENGINE_B3.md §8.2: authority, account, terminal, symbol,
calendar, windows and quote. Each returns one :class:`B3Check` with the contract's
``reason``; inside one check the first applicable reason wins, in the order written."""

from __future__ import annotations

from datetime import timedelta

from hunter_risk_b3.decision import B3Check, check_failed, check_passed, check_unavailable
from hunter_risk_b3.enums import AuthorityPhase, KillSwitchState, SpecStatus, TradeMode
from hunter_risk_b3.frame import FUTURE_TOLERANCE, Done, Frame, is_fresh, upstream
from hunter_risk_b3.kill_switch import effective_state

__all__ = [
    "check_account_mode",
    "check_entry_window",
    "check_flatten_margin",
    "check_kill_switch",
    "check_quote_fresh",
    "check_symbol_whitelist",
    "check_terminal_state",
    "check_trading_day",
]

FULL_TRADE_MODE = "SYMBOL_TRADE_MODE_FULL"


def check_kill_switch(f: Frame, done: Done) -> B3Check:
    ks = f.kill_switch
    eff = effective_state(ks)
    auth = ks.authority
    value = eff.value
    if eff is KillSwitchState.EMERGENCY:
        return check_failed(1, "kill_switch_emergency", value=value)
    if eff is KillSwitchState.TRADING_DISABLED:
        return check_failed(1, "kill_switch_trading_disabled", value=value)
    if auth.phase is not AuthorityPhase.ENTRIES:
        return check_failed(1, "entries_not_armed", value=auth.phase.value)
    if auth.instance_id != f.proposal.instance_id:
        return check_failed(1, "arming_other_instance", value=str(auth.instance_id))
    if auth.authority_expires_at is None or f.now >= auth.authority_expires_at:
        return check_failed(1, "authority_expired", input_ts=auth.authority_expires_at)
    return check_passed(1, value=value, input_ts=auth.authority_expires_at)


def check_account_mode(f: Frame, done: Done) -> B3Check:
    acc, ks = f.account, f.kill_switch
    if not acc.read_ok:
        return check_unavailable(2, "account_unreadable")
    if acc.account_hash != ks.registered_account_hash:
        return check_failed(2, "account_mismatch")
    if acc.trade_mode is TradeMode.DEMO:
        return check_passed(2, value=acc.trade_mode.value)
    if acc.trade_mode is TradeMode.REAL:
        if ks.k1_present:
            return check_passed(2, value=acc.trade_mode.value)
        return check_failed(2, "real_account_without_k1", value=acc.trade_mode.value)
    return check_failed(2, "account_mode_unsupported", value=str(acc.trade_mode))


def check_terminal_state(f: Frame, done: Done) -> B3Check:
    t = f.broker.terminal
    if not t.read_ok:
        return check_unavailable(3, "terminal_unreadable")
    if not t.connected:
        return check_failed(3, "terminal_disconnected")
    if not t.trade_allowed:
        return check_failed(3, "algo_trading_off")
    if t.tradeapi_disabled:
        return check_failed(3, "tradeapi_disabled")
    return check_passed(3, value=t.version)


def check_symbol_whitelist(f: Frame, done: Done) -> B3Check:
    cal, symbol = f.calendar, f.proposal.symbol
    contract = cal.current_contract
    if not cal.read_ok or contract is None:
        return check_unavailable(4, "contract_calendar_missing", value=symbol)
    if contract.root not in f.limits.symbol_roots:
        return check_failed(4, "symbol_root_not_allowed", value=contract.root,
                            limit=",".join(f.limits.symbol_roots))  # fmt: skip
    if symbol != contract.symbol:
        return check_failed(4, "symbol_not_current_contract", value=symbol, limit=contract.symbol)
    now = f.spec.now
    if now.status is not SpecStatus.OK or now.trade_mode is None:
        return check_unavailable(4, "upstream_unavailable:23", value=symbol)
    if now.trade_mode != FULL_TRADE_MODE:
        return check_failed(
            4, "symbol_trade_mode_restricted", value=now.trade_mode, limit=FULL_TRADE_MODE
        )
    if cal.is_expiry_day:
        return check_failed(4, "contract_expiry_day", value=contract.expiry_date.isoformat())
    return check_passed(4, value=symbol)


def check_trading_day(f: Frame, done: Done) -> B3Check:
    cal = f.calendar
    if not cal.read_ok:
        return check_unavailable(5, "calendar_unreadable")
    if cal.is_holiday:
        return check_failed(5, "holiday")
    if not cal.has_grid:
        if cal.is_shortened:
            return check_failed(5, "shortened_session_without_grid")
        return check_unavailable(5, "session_grid_missing")
    return check_passed(5, value=f.session.grid_version)


def check_entry_window(f: Frame, done: Done) -> B3Check:
    if upstream(done, 5):
        return check_unavailable(6, "upstream_unavailable:5")
    s, p, now = f.session, f.proposal, f.now
    earliest = s.open_utc + timedelta(minutes=f.limits.no_entry_first_min)
    if now < earliest:
        return check_failed(6, "before_entry_window", input_ts=earliest)
    if s.entry_cutoff_utc is not None and now > s.entry_cutoff_utc:
        return check_failed(6, "after_entry_cutoff", input_ts=s.entry_cutoff_utc)
    if not p.entry_window_start_utc <= now <= p.entry_window_end_utc:
        return check_failed(6, "outside_strategy_window", input_ts=p.entry_window_end_utc)
    return check_passed(6, input_ts=now)


def check_flatten_margin(f: Frame, done: Done) -> B3Check:
    if upstream(done, 5):
        return check_unavailable(7, "upstream_unavailable:5")
    s, lim = f.session, f.limits
    if s.flatten_at_utc is None or s.rico_flatten_utc is None:
        return check_unavailable(7, "flatten_schedule_unset", message="D6 empty: no entries")
    remaining = s.flatten_at_utc - f.now
    minutes = int(remaining.total_seconds() // 60)
    if remaining < timedelta(minutes=lim.min_minutes_before_flatten):
        return check_failed(7, "too_close_to_flatten", value=minutes, limit=lim.min_minutes_before_flatten,
                            input_ts=s.flatten_at_utc)  # fmt: skip
    latest = s.rico_flatten_utc - timedelta(minutes=lim.flatten_lead_min)
    if s.flatten_at_utc > latest:
        return check_failed(7, "flatten_after_rico_cutoff", input_ts=s.rico_flatten_utc)
    return check_passed(
        7, value=minutes, limit=lim.min_minutes_before_flatten, input_ts=s.flatten_at_utc
    )


def check_quote_fresh(f: Frame, done: Done) -> B3Check:
    q, clock, lim, now = f.quote, f.session.clock, f.limits, f.now
    if not q.read_ok or q.time_utc is None:
        return check_unavailable(8, "quote_missing")
    if (
        not clock.ok
        or clock.offset_ms is None
        or not is_fresh(clock.measured_at, now, timedelta(seconds=lim.clock_check_max_age_s))
    ):
        return check_unavailable(8, "clock_offset_unmeasured", input_ts=clock.measured_at)
    if f.book is None:
        return check_failed(8, "quote_invalid", input_ts=q.time_utc)
    age = now - q.time_utc
    if age > timedelta(seconds=lim.max_quote_age_s):
        return check_failed(8, "quote_stale", value=int(age.total_seconds()), limit=lim.max_quote_age_s,
                            input_ts=q.time_utc)  # fmt: skip
    if q.time_utc - now > FUTURE_TOLERANCE:
        return check_failed(8, "quote_from_future", input_ts=q.time_utc)
    if abs(clock.offset_ms) > lim.max_clock_offset_s * 1000:
        return check_failed(8, "clock_offset_exceeded", value=clock.offset_ms,
                            limit=lim.max_clock_offset_s * 1000)  # fmt: skip
    return check_passed(
        8, value=int(age.total_seconds()), limit=lim.max_quote_age_s, input_ts=q.time_utc
    )
