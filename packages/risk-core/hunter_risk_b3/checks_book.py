"""Checks 9–13, 15 and 24 of docs/RISK_ENGINE_B3.md §8.2: the book, the account's
exposure and in-flight work, the size requested, the day's count, the stop geometry and
the reference price. A check that needs a usable quote (read, ``0 < bid < ask``) is
``upstream_unavailable:8`` without one, and whenever check 8 itself is ``unavailable``
(e.g. clock offset unmeasured); failures independent of the quote are still reported
first (Astra, R1 review must-fix 4)."""

from __future__ import annotations

from hunter_risk_b3.decision import B3Check, check_failed, check_passed, check_unavailable
from hunter_risk_b3.enums import Side
from hunter_risk_b3.frame import Done, Frame, on_tick, upstream

__all__ = [
    "check_contracts_caps",
    "check_open_positions",
    "check_order_in_flight",
    "check_slippage_guard",
    "check_spread",
    "check_stop_geometry",
    "check_trades_today",
]


def check_spread(f: Frame, done: Done) -> B3Check:
    book = f.book
    if upstream(done, 8) or book is None:
        return check_unavailable(9, "upstream_unavailable:8")
    bid, ask = book
    spread, limit = ask - bid, f.limits.max_spread_ticks * f.tick
    if spread > limit:
        return check_failed(9, "spread_too_wide", value=spread, limit=limit)
    return check_passed(9, value=spread, limit=limit)


def check_open_positions(f: Frame, done: Done) -> B3Check:
    """``max_open_positions = 1`` = enter only when the account is flat (any symbol)."""
    b = f.broker
    if not b.positions_ok:
        return check_unavailable(10, "positions_unreadable")
    count = len(b.positions)
    if count == 0:
        return check_passed(10, value=0, limit=0)
    if any(p.magic not in f.ops.robot_magics for p in b.positions):
        return check_failed(10, "foreign_position_present", value=count, limit=0)
    return check_failed(10, "position_already_open", value=count, limit=0)


def check_order_in_flight(f: Frame, done: Done) -> B3Check:
    """The counts arrive without the proposal under evaluation (§8.1, ``[Astra R0a-1]``)."""
    b, ops = f.broker, f.ops
    if not b.orders_ok:
        return check_unavailable(11, "orders_unreadable")
    if b.orders:
        if any(o.magic not in ops.robot_magics for o in b.orders):
            return check_failed(11, "foreign_order_present", value=len(b.orders), limit=0)
        return check_failed(11, "pending_order_present", value=len(b.orders), limit=0)
    if ops.unknown_intents > 0:
        return check_failed(11, "entry_intent_unknown", value=ops.unknown_intents, limit=0)
    if ops.open_entry_intents > 0:
        return check_failed(11, "entry_intent_in_flight", value=ops.open_entry_intents, limit=0)
    if f.proposal.symbol in ops.orphan_sltp_unknown:
        return check_failed(11, "orphan_sltp_unknown", value=f.proposal.symbol)
    return check_passed(11, value=0, limit=0)


def check_contracts_caps(f: Frame, done: Done) -> B3Check:
    lim, requested = f.limits, f.proposal.requested_contracts
    cap = min(lim.max_contracts_per_order, lim.max_contracts_per_position)
    if requested < 1:
        return check_failed(12, "requested_contracts_invalid", value=requested, limit=cap)
    if requested > lim.max_contracts_per_order or requested > lim.max_contracts_per_position:
        return check_failed(12, "contracts_cap_exceeded", value=requested, limit=cap)
    return check_passed(12, value=requested, limit=cap)


def check_trades_today(f: Frame, done: Done) -> B3Check:
    ops, limit = f.ops, f.limits.max_trades_per_day
    if not ops.day.history_complete:
        return check_unavailable(13, "trade_count_unavailable", limit=limit)
    if ops.entries_today >= limit:
        return check_failed(13, "max_trades_per_day_reached", value=ops.entries_today, limit=limit)
    return check_passed(13, value=ops.entries_today, limit=limit)


def check_stop_geometry(f: Frame, done: Done) -> B3Check:
    p, tick, lim = f.proposal, f.tick, f.limits
    stop, limit_price = p.stop_price, f.limit_price
    if stop is None:
        return check_failed(15, "stop_missing")
    if not on_tick(stop, tick):
        return check_failed(15, "stop_off_tick", value=stop, limit=tick)
    buy = p.side is Side.BUY
    if (buy and stop >= limit_price) or (not buy and stop <= limit_price):
        return check_failed(15, "stop_wrong_side", value=stop, limit=limit_price)
    book = f.book
    if upstream(done, 8) or book is None:
        return check_unavailable(15, "upstream_unavailable:8", value=stop)
    bid, ask = book
    if (buy and stop >= bid) or (not buy and stop <= ask):
        return check_failed(15, "stop_already_crossed", value=stop, limit=bid if buy else ask)
    ticks = abs(limit_price - stop) / tick
    if ticks < lim.min_stop_ticks:
        return check_failed(15, "stop_too_close", value=ticks, limit=lim.min_stop_ticks)
    if ticks > lim.max_stop_ticks:
        return check_failed(15, "stop_too_far", value=ticks, limit=lim.max_stop_ticks)
    target = p.target_price
    if target is not None and (
        not on_tick(target, tick)
        or (buy and target <= limit_price)
        or (not buy and target >= limit_price)
    ):
        return check_failed(15, "target_invalid", value=target, limit=limit_price)
    return check_passed(15, value=ticks, limit=lim.max_stop_ticks)


def check_slippage_guard(f: Frame, done: Done) -> B3Check:
    p, tick, lim = f.proposal, f.tick, f.limits
    if not f.spec.pin.order_lifecycle_proven:
        return check_failed(24, "order_lifecycle_unproven", message="T14 not proven")
    if not on_tick(p.ref_price, tick):
        return check_failed(24, "reference_off_tick", value=p.ref_price, limit=tick)
    book = f.book
    if upstream(done, 8) or book is None:
        return check_unavailable(24, "upstream_unavailable:8")
    touch = book[1] if p.side is Side.BUY else book[0]
    drift = abs(p.ref_price - touch) / tick
    if drift > lim.max_slippage_ticks:
        return check_failed(24, "reference_drifted", value=drift, limit=lim.max_slippage_ticks)
    return check_passed(
        24, value=drift, limit=lim.max_slippage_ticks, message=f"limit {f.limit_price}"
    )
