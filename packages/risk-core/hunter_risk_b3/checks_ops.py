"""Checks 19–23 and 25 of docs/RISK_ENGINE_B3.md §8.2: rejection breaker,
reconciliation, audit path, signal validity, spec pin and equity floor."""

from __future__ import annotations

from datetime import timedelta

from hunter_risk_b3.context import SPEC_FIELDS
from hunter_risk_b3.decision import B3Check, check_failed, check_passed, check_unavailable
from hunter_risk_b3.enums import SpecStatus
from hunter_risk_b3.frame import Done, Frame, is_fresh

__all__ = [
    "breaker_trips_now",
    "check_audit_path",
    "check_broker_reject_breaker",
    "check_equity_floor",
    "check_reconciliation_ok",
    "check_signal_validity",
    "check_spec_unchanged",
]

_VERSION_FIELDS = ("terminal_version", "package_version")


def _recent_rejects(f: Frame) -> int:
    window = timedelta(seconds=f.limits.reject_window_s)
    return sum(1 for r in f.ops.entry_rejects if f.now - r <= window)


def breaker_trips_now(f: Frame) -> bool:
    """True when the window count crosses ``max_rejects`` and the breaker is not latched
    yet — the only case in which ``broker_reject_breaker`` is emitted as a trigger."""
    return not f.ops.breaker_latched and _recent_rejects(f) >= f.limits.max_rejects


def check_broker_reject_breaker(f: Frame, done: Done) -> B3Check:
    recent, limit = _recent_rejects(f), f.limits.max_rejects
    if f.ops.breaker_latched:
        return check_failed(19, "broker_reject_breaker", value=recent, limit=limit,
                            message="latched: manual re-arm only")  # fmt: skip
    if recent >= limit:
        return check_failed(19, "broker_reject_breaker", value=recent, limit=limit)
    return check_passed(19, value=recent, limit=limit)


def check_reconciliation_ok(f: Frame, done: Done) -> B3Check:
    last = f.ops.last_reconcile
    max_age = timedelta(seconds=2 * f.limits.reconcile_interval_s)
    if last is None or not is_fresh(last.at, f.now, max_age):
        return check_unavailable(
            20, "reconciliation_stale", input_ts=None if last is None else last.at
        )
    if not last.clean:
        return check_failed(20, "reconciliation_divergent", input_ts=last.at)
    if last.consistent_passes < 2:
        return check_failed(20, "reconciliation_settling", value=last.consistent_passes, limit=2,
                            input_ts=last.at)  # fmt: skip
    return check_passed(20, value=last.consistent_passes, limit=2, input_ts=last.at)


def check_audit_path(f: Frame, done: Done) -> B3Check:
    a = f.ops.audit
    fresh = timedelta(seconds=f.limits.entries_api_freshness_s)
    if not is_fresh(a.api_last_ok_at, f.now, fresh):
        return check_failed(21, "audit_api_unreachable", input_ts=a.api_last_ok_at)
    if a.buffer_len > 0:
        return check_failed(21, "audit_buffer_not_empty", value=a.buffer_len, limit=0)
    if not a.buffer_writable:
        return check_failed(21, "audit_buffer_unwritable")
    return check_passed(21, input_ts=a.api_last_ok_at)


def check_signal_validity(f: Frame, done: Done) -> B3Check:
    """Three separate clocks (§8.2): the signal's own deadline is never renewed, the
    approval lives ``approval_ttl_s`` from ``created_at``, market inputs live seconds
    (check 8)."""
    p, now, armed = f.proposal, f.now, f.kill_switch.armed_strategy
    if p.signal_published_at > p.signal_deadline_utc:
        return check_failed(22, "signal_late", input_ts=p.signal_published_at)
    if not p.entry_window_start_utc <= now <= p.entry_window_end_utc:
        return check_failed(22, "signal_outside_window", input_ts=now)
    if armed is None or armed.key != p.strategy_key:
        return check_failed(22, "strategy_not_armed", value=p.strategy_key)
    if armed.version != p.strategy_version:
        return check_failed(
            22, "strategy_version_mismatch", value=p.strategy_version, limit=armed.version
        )
    if armed.params_hash != p.params_hash:
        return check_failed(
            22, "params_hash_mismatch", value=p.params_hash, limit=armed.params_hash
        )
    age = now - p.created_at
    if age > timedelta(seconds=f.limits.approval_ttl_s):
        return check_failed(22, "proposal_stale", value=int(age.total_seconds()),
                            limit=f.limits.approval_ttl_s, input_ts=p.created_at)  # fmt: skip
    return check_passed(22, input_ts=p.created_at)


def check_spec_unchanged(f: Frame, done: Done) -> B3Check:
    pin, now = f.spec.pin, f.spec.now
    if now.status is SpecStatus.UNREADABLE:
        return check_unavailable(23, "spec_unreadable")
    diff = [name for name in SPEC_FIELDS if getattr(pin, name) != getattr(now, name)]
    spec_diff = [name for name in diff if name not in _VERSION_FIELDS]
    if now.status is SpecStatus.CHANGED or spec_diff:
        return check_failed(23, "spec_changed", value=",".join(spec_diff) or now.status.value)
    if "terminal_version" in diff:
        return check_failed(23, "terminal_version_changed", value=now.terminal_version,
                            limit=pin.terminal_version)  # fmt: skip
    if "package_version" in diff:
        return check_failed(23, "package_version_changed", value=now.package_version,
                            limit=pin.package_version)  # fmt: skip
    return check_passed(23, value=pin.spec_pin_id)


def check_equity_floor(f: Frame, done: Done) -> B3Check:
    floor = f.limits.equity_floor_brl
    if floor is None:
        return check_passed(25, limit=None, message="desligado")
    acc = f.account
    if not acc.read_ok or acc.equity is None:
        return check_unavailable(25, "account_unreadable", limit=floor)
    if acc.equity < floor:
        return check_failed(25, "equity_below_floor", value=acc.equity, limit=floor)
    return check_passed(25, value=acc.equity, limit=floor)
