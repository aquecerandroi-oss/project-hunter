"""FAKE MetaTrader 5 module (``MetaTrader5``-shaped, floats and named tuples). TEST CODE ONLY.

Plug it into ``Mt5Adapter(FakeMt5())``. It simulates, offline: a netting/exchange account, fills
and partial fills, rejects with retcodes, sl/tp triggered at the server by the last trade (with
gaps), netting stop inheritance (including the ``sl=0`` that erases), history deals with
``magic`` and ``reason``, terminal disconnection, "Algo Trading" off, ``comment``/``magic``
dropped by the broker, float noise, malformed answers, scripted faults on ``order_send``
(reject, ``None`` with or without effect, raise, hang then late result), the Everton's manual
trades, ticket changes by a server operation, contract-spec changes and a delisted symbol.

It never talks to anything and has no login: ``login`` only records that it was called, and
``initialize`` records the keywords it received, so a test can prove no credential was passed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from hunter_exchanges.mt5.constants import Retcode

from .mt5_controls import FakeControls
from .mt5_state import NOT_FOUND, SEND_FAILED
from .mt5_types import (
    AccountInfo,
    Deal,
    Fault,
    Ord,
    OrderCheckResult,
    OrderSendResult,
    Pos,
    SymbolInfo,
    TerminalInfo,
    Tick,
    TradeDeal,
    TradeOrder,
    TradePosition,
)


class FakeMt5(FakeControls):
    __version__ = "5.0.6231"
    # distinctive on purpose: tests assert they never appear in any model, log or request
    LOGIN = 987_654_321
    SERVER = "FakeRico-Demo"

    # ------------------------------------------------------------------ the vendor surface
    def initialize(self, path: str | None = None, **kwargs: Any) -> bool:
        self.initialize_kwargs.append({"path": path, **kwargs})
        self.calls.append(("initialize", {"path": path, **kwargs}))
        return True

    def login(self, *args: Any, **kwargs: Any) -> bool:  # the adapter must never call this
        self.login_calls += 1
        return False

    def shutdown(self) -> None:
        self.calls.append(("shutdown", {}))

    def last_error(self) -> tuple[int, str]:
        return self._err

    def version(self) -> Any:
        return (5, self.build, self.version_str) if self._gate("version") else None

    def terminal_info(self) -> Any:
        if not self._gate("terminal_info"):
            return None
        info = TerminalInfo(
            self.connected,
            self.algo_trading,
            self.tradeapi_disabled,
            self.build,
            1200,
            "C:/fake",
            "C:/fake/data",
        )
        return self._emit("terminal_info", info)

    def account_info(self) -> Any:
        if not self._gate("account_info"):
            return None
        b = self.broker
        info = AccountInfo(
            self.LOGIN, self.SERVER, self.trade_mode, self.margin_mode, "BRL", 2,
            self._n(b.balance), self._n(b.equity()), self._n(b.margin()),
            self._n(b.equity() - b.margin()), self.algo_trading, self.algo_trading,
        )  # fmt: skip
        return self._emit("account_info", info)

    def symbol_info(self, symbol: str) -> Any:
        if not self._gate("symbol_info", symbol=symbol):
            return None
        b = self.broker
        if symbol != b.symbol or self.hooks.delisted:
            self._err = NOT_FOUND
            return None
        info = SymbolInfo(
            symbol, True, True, b.digits, b.point, b.tick_size, b.tick_value, 0.2, b.volume_min,
            b.volume_max, b.volume_step, self.symbol_trade_mode, self.filling_mask,
            self.expiration_mask, b.stops_level, 0,
        )  # fmt: skip
        return self._emit("symbol_info", info)

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return self._gate("symbol_select", symbol=symbol) and symbol == self.broker.symbol

    def symbol_info_tick(self, symbol: str) -> Any:
        if not self._gate("symbol_info_tick", symbol=symbol):
            return None
        b = self.broker
        if symbol != b.symbol or self.hooks.delisted:
            self._err = NOT_FOUND
            return None
        tick = Tick(
            b.now_ms // 1000, b.now_ms, self._n(b.bid), self._n(b.ask), self._n(b.last), 1, 0
        )
        return self._emit("symbol_info_tick", tick)

    def _position_row(self, p: Pos) -> Any:
        row = TradePosition(p.ticket, p.position_id, p.time_msc, p.side, p.magic, p.reason, self._n(p.volume),
                            self._n(p.price_open), self._n(p.sl), self._n(p.tp), p.symbol, p.comment)  # fmt: skip
        return self._emit("positions_get", row)

    def positions_get(self, symbol: str | None = None, ticket: int | None = None, **_: Any) -> Any:
        if not self._gate("positions_get", symbol=symbol, ticket=ticket):
            return None
        rows = [
            p
            for p in self.broker.positions
            if symbol in (None, p.symbol) and ticket in (None, p.ticket)
        ]
        return tuple(self._position_row(p) for p in rows)

    def _order_row(self, o: Ord, function: str) -> Any:
        row = TradeOrder(o.ticket, o.time_setup_msc, o.time_done_msc, o.expiration, o.type, o.filling, o.time_type,
                         o.state, o.magic, o.position_id, o.reason, self._n(o.volume_initial),
                         self._n(o.volume_current), self._n(o.price_open), self._n(o.sl), self._n(o.tp),
                         o.symbol, o.comment)  # fmt: skip
        return self._emit(function, row)

    def orders_get(self, symbol: str | None = None, ticket: int | None = None, **_: Any) -> Any:
        if not self._gate("orders_get", symbol=symbol, ticket=ticket):
            return None
        rows = [
            o
            for o in self.broker.orders
            if symbol in (None, o.symbol) and ticket in (None, o.ticket)
        ]
        return tuple(self._order_row(o, "orders_get") for o in rows)

    @staticmethod
    def _secs(value: Any) -> int:
        return int(value.timestamp()) if isinstance(value, datetime) else int(value)

    def history_orders_get(
        self,
        date_from: Any = None,
        date_to: Any = None,
        *,
        ticket: int | None = None,
        position: int | None = None,
        **_: Any,
    ) -> Any:
        if not self._gate("history_orders_get", ticket=ticket, position=position):
            return None
        if self.hooks.history_unavailable:
            self._err = SEND_FAILED
            return None
        rows = [o for o in self.broker.history if o.time_done_msc >= self.hooks.history_floor_ms]
        if ticket is not None:
            rows = [o for o in rows if o.ticket == ticket]
        elif position is not None:
            rows = [o for o in rows if o.position_id == position]
        else:
            lo, hi = self._secs(date_from) * 1000, self._secs(date_to) * 1000
            rows = [o for o in rows if lo <= o.time_done_msc <= hi]
        return tuple(self._order_row(o, "history_orders_get") for o in rows)

    def _deal_row(self, d: Deal) -> Any:
        magic = 0 if self.hooks.drop_magic else d.magic
        row = TradeDeal(d.ticket, d.order, d.time_msc, d.type, d.entry, magic, d.position_id, d.reason, self._n(d.volume),
                        self._n(d.price), d.commission, 0.0, d.profit, 0.0, d.symbol, d.comment)  # fmt: skip
        return self._emit("history_deals_get", row)

    def history_deals_get(
        self,
        date_from: Any = None,
        date_to: Any = None,
        *,
        ticket: int | None = None,
        position: int | None = None,
        **_: Any,
    ) -> Any:
        if not self._gate("history_deals_get", ticket=ticket, position=position):
            return None
        if self.hooks.history_unavailable:
            self._err = SEND_FAILED
            return None
        rows = [d for d in self.broker.deals if d.time_msc >= self.hooks.history_floor_ms]
        if ticket is not None:
            rows = [d for d in rows if d.ticket == ticket]
        elif position is not None:
            rows = [d for d in rows if d.position_id == position]
        else:
            lo, hi = self._secs(date_from) * 1000, self._secs(date_to) * 1000
            rows = [d for d in rows if lo <= d.time_msc <= hi]
        out = tuple(self._deal_row(d) for d in rows)
        return out + out if self.hooks.duplicate_deals else out

    def order_calc_margin(self, action: int, symbol: str, volume: float, price: float) -> Any:
        if not self._gate("order_calc_margin", symbol=symbol, volume=volume, price=price):
            return None
        return self.broker.margin_per_contract * volume

    def order_check(self, request: dict[str, Any]) -> Any:
        if not self._gate("order_check", **request):
            return None
        b = self.broker
        code, comment = b.check(request)
        row = OrderCheckResult(code, b.balance, b.equity(), b.margin_per_contract * float(request["volume"]),
                               b.equity() - b.margin(), comment)  # fmt: skip
        return self._emit("order_check", row)

    # ------------------------------------------------------------------ order_send
    def _result(self, reply: tuple[int, int, int, float, float, str]) -> OrderSendResult:
        code, order, deal, volume, price, comment = reply
        b = self.broker
        return OrderSendResult(
            code, deal, order, self._n(volume), self._n(price), b.bid, b.ask, comment, 1
        )

    def _take_fault(self, action: int) -> Fault | None:
        for i, fault in enumerate(self.hooks.faults):
            if fault.action in (None, action):
                return self.hooks.faults.pop(i)
        return None

    def order_send(self, request: dict[str, Any]) -> Any:
        if not self._gate("order_send", **request):
            return None
        self.sent_requests.append(dict(request))
        fault = self._take_fault(int(request["action"]))
        if fault is not None:
            if fault.kind == "reject":
                return self._result(
                    (fault.retcode or int(Retcode.REJECT), 0, 0, 0.0, 0.0, "scripted reject")
                )
            if fault.kind == "none_no_effect":
                self._err = SEND_FAILED
                return None
            if fault.kind == "raise":
                raise RuntimeError("scripted ipc failure")
            if fault.kind == "hang":
                self.hang_entered.set()
                self.hang_release.wait(timeout=30)
        if not self.algo_trading:
            return self._result(
                (int(Retcode.CLIENT_DISABLES_AT), 0, 0, 0.0, 0.0, "AutoTrading disabled by client")
            )
        body = dict(request)
        if self.hooks.drop_comment:
            body["comment"] = ""
        if self.hooks.drop_magic:
            body["magic"] = 0
        result = self._result(self.broker.handle(body))
        if fault is not None and fault.kind == "none_after_effect":
            self._err = SEND_FAILED
            return None
        return self._emit("order_send", result)
