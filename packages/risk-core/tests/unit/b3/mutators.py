"""TEST HELPERS ONLY — one-input mutations of the all-pass scenario of ``factories``,
used by the 25-check table (``test_checks_table.py``)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from hunter_risk_b3 import BrokerOrder, BrokerPosition, Side

from . import factories as fx
from .factories import Scenario

Mut = Callable[[Scenario], Scenario]


def position_of(magic: int = fx.MAGIC) -> BrokerPosition:
    return BrokerPosition(
        position_id=11, position_ticket=11, symbol="WINZ26", side=Side.BUY,
        volume=Decimal("1"), price_open=Decimal("207000"), sl=Decimal("205975"),
        tp=Decimal("0"), magic=magic, time_msc=1,
    )  # fmt: skip


def order_of(magic: int = fx.MAGIC) -> BrokerOrder:
    return BrokerOrder(
        ticket=21, symbol="WINZ26", type="ORDER_TYPE_BUY_LIMIT",
        volume_current=Decimal("1"), price=Decimal("207000"), magic=magic, comment="HBX",
    )  # fmt: skip


def k(**u: object) -> Mut:
    return lambda sc: sc.with_(kill_switch=sc.kill_switch.model_copy(update=u))


def acc(**u: object) -> Mut:
    return lambda sc: sc.with_(account=sc.account.model_copy(update=u))


def term(**u: object) -> Mut:
    return lambda sc: sc.with_(
        broker=sc.broker.model_copy(update={"terminal": sc.broker.terminal.model_copy(update=u)})
    )


def brk(**u: object) -> Mut:
    return lambda sc: sc.with_(broker=sc.broker.model_copy(update=u))


def cal(**u: object) -> Mut:
    return lambda sc: sc.with_(calendar=sc.calendar.model_copy(update=u))


def ses(**u: object) -> Mut:
    return lambda sc: sc.with_(session=sc.session.model_copy(update=u))


def lim(**u: object) -> Mut:
    return lambda sc: sc.with_(limits=sc.limits.model_copy(update=u))


def prop(**u: object) -> Mut:
    return lambda sc: sc.with_(proposal=sc.proposal.model_copy(update=u))


def q(**u: object) -> Mut:
    return lambda sc: sc.with_(quote=sc.quote.model_copy(update=u))


def op(**u: object) -> Mut:
    return lambda sc: sc.with_(ops=sc.ops.model_copy(update=u))


def dy(**u: object) -> Mut:
    return lambda sc: sc.with_(
        ops=sc.ops.model_copy(update={"day": sc.ops.day.model_copy(update=u)})
    )


def mg(**u: object) -> Mut:
    return lambda sc: sc.with_(margin=sc.margin.model_copy(update=u))


def sp(pin: dict[str, object] | None = None, now: dict[str, object] | None = None) -> Mut:
    return lambda sc: sc.with_(spec=fx.spec(pin=pin, now=now))


def clock(**u: object) -> Mut:
    return lambda sc: sc.with_(
        session=sc.session.model_copy(update={"clock": sc.session.clock.model_copy(update=u)})
    )


def both(*muts: Mut) -> Mut:
    def run(sc: Scenario) -> Scenario:
        for m in muts:
            sc = m(sc)
        return sc

    return run


def same(sc: Scenario) -> Scenario:
    return sc
