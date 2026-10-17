"""The day's loss (check 14, docs/RISK_ENGINE_B3.md §8.3) and its deal ledger.

``loss = max(0, −(realized_gross − costs_positive + open_mtm_gross − open_exit_fee))``

Contract, each clause enforced here: every deal counts once (key: deal ticket); cost per
leg = ``max(modelled, |commission| + |fee|)``, always positive — a negative commission never
becomes a gain; non-trading deals stay out of the P&L (deposits/withdrawals go to
``cash_flows``); the sum is reconciled against ``equity_delta − cash_flows`` and a gap above
``pnl_reconcile_tolerance_brl`` is ``unavailable``; the open position discounts only the
exit fee; no anchor, incomplete history or a mark older than ``max_quote_age_s`` is
``unavailable``. **The number that hides a loss is zero**: no absent field becomes 0.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from hunter_risk_b3.base import B3Model
from hunter_risk_b3.decision import B3Check, check_failed, check_passed, check_unavailable
from hunter_risk_b3.frame import FUTURE_TOLERANCE, Frame, is_fresh
from hunter_risk_b3.session import session_date_of

__all__ = ["DayDeal", "DaySummary", "DealKind", "LossAssessment", "assess_loss", "summarize_deals"]

_ZERO = Decimal(0)


class DealKind(StrEnum):
    TRADE = "trade"
    """A buy/sell deal: one leg."""
    CASH_FLOW = "cash_flow"
    """Deposit, withdrawal, credit: outside the P&L, inside ``cash_flows``."""
    OTHER = "other"
    """Any other non-trading deal (correction, charge): outside both."""


class DayDeal(B3Model):
    """One deal as the broker lists it. ``commission`` and ``fee`` are required: an
    unreadable amount must not become 0 (a hidden cost); the caller marks the history
    incomplete instead (Astra, R1 review must-fix 3)."""

    ticket: int
    kind: DealKind
    profit: Decimal
    commission: Decimal
    fee: Decimal


class DaySummary(B3Model):
    realized_gross_brl: Decimal
    costs_positive_brl: Decimal = Field(ge=0)
    cash_flows_brl: Decimal
    trade_legs: int = Field(ge=0)


def summarize_deals(deals: Iterable[DayDeal], *, per_leg_brl: Decimal) -> DaySummary:
    """The ``ops.day`` aggregates from the session's deals. A redelivered deal (same
    ticket, same content) counts once; the same ticket with different content is refused
    (``deal_ticket_conflict``) — the caller marks the history incomplete."""
    seen: dict[int, DayDeal] = {}
    for deal in deals:
        known = seen.get(deal.ticket)
        if known is None:
            seen[deal.ticket] = deal
        elif known != deal:
            raise ValueError(f"deal_ticket_conflict: ticket {deal.ticket} with two contents")
    realized = costs = cash = _ZERO
    legs = 0
    for deal in seen.values():
        if deal.kind is DealKind.TRADE:
            realized += deal.profit
            costs += max(per_leg_brl, abs(deal.commission) + abs(deal.fee))
            legs += 1
        elif deal.kind is DealKind.CASH_FLOW:
            cash += deal.profit
    return DaySummary(
        realized_gross_brl=realized, costs_positive_brl=costs, cash_flows_brl=cash, trade_legs=legs
    )


@dataclass(frozen=True, slots=True)
class LossAssessment:
    loss_brl: Decimal | None
    """``None`` when check 14 is unavailable."""
    check: B3Check


def _anchor_ok(f: Frame, session_date: date) -> bool:
    d = f.ops.day
    if d.anchor_equity is None or d.anchor_at is None or d.equity_delta_brl is None:
        return False
    if d.anchor_at - f.now > FUTURE_TOLERANCE:
        return False  # an anchor from the future is not this session anchor
    return session_date_of(d.anchor_at) == session_date


def assess_loss(f: Frame) -> LossAssessment:
    d, lim, now = f.ops.day, f.limits, f.now
    limit = lim.daily_loss_limit_brl
    delta = d.equity_delta_brl
    if delta is None or not _anchor_ok(f, f.session.session_date):
        msg = "no anchor for this session (or an anchor from another day)"
        return LossAssessment(
            None, check_unavailable(14, "day_anchor_missing", limit=limit, message=msg)
        )
    if (
        not d.history_complete
        or d.realized_gross_brl is None
        or d.costs_positive_brl is None
        or d.cash_flows_brl is None
    ):
        return LossAssessment(
            None, check_unavailable(14, "session_history_incomplete", limit=limit)
        )
    if (
        d.open_mtm_gross_brl is None
        or d.open_exit_fee_brl is None
        or not is_fresh(d.mark_time, now, timedelta(seconds=lim.max_quote_age_s))
    ):
        return LossAssessment(
            None, check_unavailable(14, "mark_stale", limit=limit, input_ts=d.mark_time)
        )
    ours = d.realized_gross_brl - d.costs_positive_brl + d.open_mtm_gross_brl
    broker = delta - d.cash_flows_brl
    gap = abs(ours - broker)
    if gap > lim.pnl_reconcile_tolerance_brl:
        msg = f"ledger {ours} vs broker equity delta net of cash flows {broker}"
        return LossAssessment(
            None,
            check_unavailable(14, "pnl_reconcile_divergent", value=gap,
                              limit=lim.pnl_reconcile_tolerance_brl, message=msg),
        )  # fmt: skip
    loss = max(_ZERO, -(ours - d.open_exit_fee_brl))
    if loss >= limit:
        return LossAssessment(loss, check_failed(14, "daily_loss_limit", value=loss, limit=limit))
    return LossAssessment(loss, check_passed(14, value=loss, limit=limit, input_ts=d.mark_time))
