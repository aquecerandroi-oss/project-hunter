"""FAKE MetaTrader 5: the controls a test uses to drive the market and the broker's quirks."""

from __future__ import annotations

from hunter_exchanges.mt5.constants import DealReason, Retcode, TradeAction

from .mt5_state import FakeState
from .mt5_types import Fault, Ord


class FakeControls(FakeState):
    def set_quote(self, bid: float, ask: float, last: float | None = None) -> None:
        self.broker.set_quote(bid, ask, last)

    def trade(self, price: float) -> None:
        self.broker.trade(price)

    def advance(self, seconds: float) -> None:
        self.broker.now_ms += int(seconds * 1000)
        self.broker.expire()

    def end_of_day(self) -> None:
        self.broker.expire(day_end=True)

    def disconnect(self) -> None:
        self.connected = False

    def reconnect(self) -> None:
        self.connected = True

    def plan_fault(
        self, kind: str, *, action: TradeAction | None = None, retcode: Retcode | None = None
    ) -> None:
        self.hooks.faults.append(
            Fault(
                kind,
                None if action is None else int(action),
                None if retcode is None else int(retcode),
            )
        )

    def malform(self, function: str, mode: str | None, field: str = "") -> None:
        """mode: ``missing`` | ``nan`` | ``wrong_type`` for ``field`` of everything ``function`` returns."""
        if mode is None:
            self._malform.pop(function, None)
        else:
            self._malform[function] = (mode, field)

    def delist(self) -> None:
        self.hooks.delisted = True

    def manual_trade(
        self, side: int, volume: float, price: float, *, sl: float = 0.0, tp: float = 0.0
    ) -> None:
        """The Everton clicks in the terminal: magic 0, reason CLIENT, no comment."""
        b = self.broker
        order = Ord(
            b.next_ticket(),
            b.symbol,
            side,
            4,
            volume,
            0.0,
            price,
            sl,
            tp,
            0,
            "",
            0,
            b.now_ms,
            1,
            0,
            0,
            0,
        )
        b.history.append(order)
        b.fill(order, side, volume, price, int(DealReason.CLIENT), 0)

    def manual_sltp(self, sl: float, tp: float) -> None:
        pos = self.broker.position()
        assert pos is not None
        pos.sl, pos.tp = sl, tp

    def service_change_ticket(self) -> None:
        """A server-side service operation gives the position a new ticket; the id stays."""
        pos = self.broker.position()
        assert pos is not None
        pos.ticket = self.broker.next_ticket()

    def release_hang(self) -> None:
        self.hang_release.set()
