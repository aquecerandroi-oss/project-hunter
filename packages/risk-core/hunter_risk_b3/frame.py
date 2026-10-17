"""The arguments of one evaluation, bundled, plus the few values several checks derive.

``now`` is ``broker.as_of`` (§8.1: the engine has no clock); ``tick`` is
``spec.pin.trade_tick_size`` (§8.2 notation; check 23 proves the pin still matches);
``limit_price`` is derived, never received (§8.3, check 24).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_risk_b3.context import (
    CalendarB3,
    KillSwitchB3,
    MarginInputs,
    SessionContext,
    SpecInputs,
)
from hunter_risk_b3.decision import B3Check
from hunter_risk_b3.enums import CheckState, Side
from hunter_risk_b3.inputs import AccountSnapshot, B3EntryProposal, BrokerSnapshot, QuoteSnapshot
from hunter_risk_b3.limits import RiskLimitsB3
from hunter_risk_b3.ops import RobotOpsState

__all__ = [
    "FUTURE_TOLERANCE",
    "Done",
    "Frame",
    "is_fresh",
    "limit_price_for",
    "on_tick",
    "upstream",
]

Done = dict[int, B3Check]
"""Checks already evaluated in this decision, by id (dependents read their state)."""


def limit_price_for(
    side: Side, ref_price: Decimal, tick: Decimal, max_slippage_ticks: int
) -> Decimal:
    """§8.3: the worst admissible price — buy ceiling, sell floor."""
    offset = max_slippage_ticks * tick
    return ref_price + offset if side is Side.BUY else ref_price - offset


def on_tick(price: Decimal, tick: Decimal) -> bool:
    return price % tick == 0


FUTURE_TOLERANCE = timedelta(seconds=2)
"""How far ahead of ``now`` a stamp may be (check 8: ``time_utc - now <= 2 s``)."""


def is_fresh(stamp: datetime | None, now: datetime, max_age: timedelta) -> bool:
    """``-2 s <= now - stamp <= max_age``. A stamp from the future is **not** fresh: a
    clock or conversion error would otherwise make old data look new (Astra, R1 review
    must-fix 5)."""
    if stamp is None:
        return False
    return -FUTURE_TOLERANCE <= now - stamp <= max_age


def upstream(done: Done, cid: int) -> bool:
    """True when check ``cid`` came out ``unavailable`` (its dependents follow)."""
    return done[cid].state is CheckState.UNAVAILABLE


@dataclass(frozen=True, slots=True)
class Frame:
    proposal: B3EntryProposal
    broker: BrokerSnapshot
    account: AccountSnapshot
    limits: RiskLimitsB3
    session: SessionContext
    calendar: CalendarB3
    quote: QuoteSnapshot
    kill_switch: KillSwitchB3
    spec: SpecInputs
    margin: MarginInputs
    ops: RobotOpsState

    @property
    def now(self) -> datetime:
        return self.broker.as_of

    @property
    def tick(self) -> Decimal:
        return self.spec.pin.trade_tick_size

    @property
    def limit_price(self) -> Decimal:
        p = self.proposal
        return limit_price_for(p.side, p.ref_price, self.tick, self.limits.max_slippage_ticks)

    @property
    def book(self) -> tuple[Decimal, Decimal] | None:
        """``(bid, ask)`` when the quote was read and ``0 < bid < ask``, else ``None``."""
        q = self.quote
        if not q.read_ok or q.bid is None or q.ask is None:
            return None
        if not Decimal(0) < q.bid < q.ask:
            return None
        return q.bid, q.ask
