"""Our integer constants must equal the official package's (offline: import only, no terminal)."""

from __future__ import annotations

import enum
from typing import Any

import pytest

from hunter_exchanges.mt5 import constants as c

pytestmark = pytest.mark.unit

# Our name -> official prefix. A member `Retcode.DONE` is `mt5.TRADE_RETCODE_DONE`.
ENUMS: dict[type[enum.IntEnum], str] = {
    c.TradeAction: "TRADE_ACTION_",
    c.OrderType: "ORDER_TYPE_",
    c.Filling: "ORDER_FILLING_",
    c.TimeMode: "ORDER_TIME_",
    c.OrderState: "ORDER_STATE_",
    c.PositionType: "POSITION_TYPE_",
    c.DealType: "DEAL_TYPE_",
    c.DealEntry: "DEAL_ENTRY_",
    c.DealReason: "DEAL_REASON_",
    c.AccountTradeMode: "ACCOUNT_TRADE_MODE_",
    c.AccountMarginMode: "ACCOUNT_MARGIN_MODE_",
    c.SymbolTradeMode: "SYMBOL_TRADE_MODE_",
    c.Retcode: "TRADE_RETCODE_",
}


@pytest.fixture(scope="module")
def official() -> Any:
    return pytest.importorskip("MetaTrader5")


@pytest.mark.parametrize("enum_cls", list(ENUMS), ids=lambda e: e.__name__)
def test_every_member_matches_the_official_value(
    official: Any, enum_cls: type[enum.IntEnum]
) -> None:
    prefix = ENUMS[enum_cls]
    for member in enum_cls:
        attr = prefix + member.name
        if not hasattr(official, attr):
            # Documented by MetaQuotes but absent from the 5.0.6231 wheel.
            assert (enum_cls, member.name) in c.NOT_IN_PACKAGE, f"{attr} missing and not declared"
            continue
        assert int(member) == getattr(official, attr), attr


def test_every_official_retcode_is_known_to_us(official: Any) -> None:
    ours = {int(r) for r in c.Retcode}
    theirs = {getattr(official, n) for n in dir(official) if n.startswith("TRADE_RETCODE_")}
    assert theirs <= ours, sorted(theirs - ours)


def test_every_official_action_and_deal_reason_is_known_to_us(official: Any) -> None:
    for cls, prefix in ((c.TradeAction, "TRADE_ACTION_"), (c.DealReason, "DEAL_REASON_")):
        theirs = {getattr(official, n) for n in dir(official) if n.startswith(prefix)}
        assert theirs <= {int(m) for m in cls}, (prefix, sorted(theirs))
