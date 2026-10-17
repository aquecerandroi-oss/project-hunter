"""MetaTrader 5 integer constants, owned here so nothing imports the vendor package for them.

The official ``MetaTrader5`` wheel exists for ``win_amd64`` only, so the adapter must import
cleanly on Linux CI. These values are copied from the MQL5 documentation ("Trade Server Return
Codes", "Trade Operation Types", ...) and ``tests/mt5/test_constants_vs_package.py`` compares
every one of them with the installed wheel whenever it is present (Windows dev box).

``NOT_IN_PACKAGE`` lists the members documented by MetaQuotes but absent from wheel 5.0.6231, so
that gap is declared instead of silently skipped by that test.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = [
    "NOT_IN_PACKAGE",
    "AccountMarginMode",
    "AccountTradeMode",
    "DealEntry",
    "DealReason",
    "DealType",
    "Filling",
    "OrderState",
    "OrderType",
    "PositionType",
    "Retcode",
    "SymbolTradeMode",
    "TimeMode",
    "TradeAction",
]


class TradeAction(IntEnum):
    DEAL = 1
    PENDING = 5
    SLTP = 6
    MODIFY = 7
    REMOVE = 8
    CLOSE_BY = 10


class OrderType(IntEnum):
    BUY = 0
    SELL = 1
    BUY_LIMIT = 2
    SELL_LIMIT = 3
    BUY_STOP = 4
    SELL_STOP = 5
    BUY_STOP_LIMIT = 6
    SELL_STOP_LIMIT = 7
    CLOSE_BY = 8


class Filling(IntEnum):
    FOK = 0
    IOC = 1
    RETURN = 2
    BOC = 3


class TimeMode(IntEnum):
    GTC = 0
    DAY = 1
    SPECIFIED = 2
    SPECIFIED_DAY = 3


class OrderState(IntEnum):
    STARTED = 0
    PLACED = 1
    CANCELED = 2
    PARTIAL = 3
    FILLED = 4
    REJECTED = 5
    EXPIRED = 6
    REQUEST_ADD = 7
    REQUEST_MODIFY = 8
    REQUEST_CANCEL = 9


class PositionType(IntEnum):
    BUY = 0
    SELL = 1


class DealType(IntEnum):
    BUY = 0
    SELL = 1
    BALANCE = 2
    CREDIT = 3
    CHARGE = 4
    CORRECTION = 5
    BONUS = 6
    COMMISSION = 7
    COMMISSION_DAILY = 8
    COMMISSION_MONTHLY = 9
    COMMISSION_AGENT_DAILY = 10
    COMMISSION_AGENT_MONTHLY = 11
    INTEREST = 12
    BUY_CANCELED = 13
    SELL_CANCELED = 14


class DealEntry(IntEnum):
    IN = 0
    OUT = 1
    INOUT = 2
    OUT_BY = 3


class DealReason(IntEnum):
    CLIENT = 0
    MOBILE = 1
    WEB = 2
    EXPERT = 3
    SL = 4
    TP = 5
    SO = 6
    ROLLOVER = 7
    VMARGIN = 8
    SPLIT = 9


class AccountTradeMode(IntEnum):
    DEMO = 0
    CONTEST = 1
    REAL = 2


class AccountMarginMode(IntEnum):
    RETAIL_NETTING = 0
    EXCHANGE = 1
    RETAIL_HEDGING = 2


class SymbolTradeMode(IntEnum):
    DISABLED = 0
    LONGONLY = 1
    SHORTONLY = 2
    CLOSEONLY = 3
    FULL = 4


class Retcode(IntEnum):
    """``TRADE_RETCODE_*``. 41 members, all classified in :mod:`hunter_exchanges.mt5.retcodes`."""

    REQUOTE = 10004
    REJECT = 10006
    CANCEL = 10007
    PLACED = 10008
    DONE = 10009
    DONE_PARTIAL = 10010
    ERROR = 10011
    TIMEOUT = 10012
    INVALID = 10013
    INVALID_VOLUME = 10014
    INVALID_PRICE = 10015
    INVALID_STOPS = 10016
    TRADE_DISABLED = 10017
    MARKET_CLOSED = 10018
    NO_MONEY = 10019
    PRICE_CHANGED = 10020
    PRICE_OFF = 10021
    INVALID_EXPIRATION = 10022
    ORDER_CHANGED = 10023
    TOO_MANY_REQUESTS = 10024
    NO_CHANGES = 10025
    SERVER_DISABLES_AT = 10026
    CLIENT_DISABLES_AT = 10027
    LOCKED = 10028
    FROZEN = 10029
    INVALID_FILL = 10030
    CONNECTION = 10031
    ONLY_REAL = 10032
    LIMIT_ORDERS = 10033
    LIMIT_VOLUME = 10034
    INVALID_ORDER = 10035
    POSITION_CLOSED = 10036
    INVALID_CLOSE_VOLUME = 10038
    CLOSE_ORDER_EXIST = 10039
    LIMIT_POSITIONS = 10040
    REJECT_CANCEL = 10041
    LONG_ONLY = 10042
    SHORT_ONLY = 10043
    CLOSE_ONLY = 10044
    FIFO_CLOSE = 10045
    HEDGE_PROHIBITED = 10046


# Documented by MetaQuotes, missing from MetaTrader5==5.0.6231 (checked 2026-10-17).
NOT_IN_PACKAGE: frozenset[tuple[type[IntEnum], str]] = frozenset({(Retcode, "HEDGE_PROHIBITED")})

# `order_check` reports success with retcode 0 (documented); `order_send` uses DONE.
ORDER_CHECK_OK = 0
# `last_error()` code for "no error" (RES_S_OK) and the ones this adapter names.
RES_S_OK = 1
RES_E_AUTO_TRADING_DISABLED = -8
RES_E_INTERNAL_FAIL_CONNECT = -10004
