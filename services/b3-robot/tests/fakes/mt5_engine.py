"""FAKE exchange-side engine behind ``mt5_fake.FakeMt5``: netting, fills, stops at the server.
TEST CODE ONLY. Modelling choices (the real semantics are what the demo session T1-T17 proves):

* one position per symbol (netting/exchange account); fills use the touch, resting limits fill at
  their own price, liquidity per touch is ``liquidity`` contracts (partial fills);
* an order that increases or inverts REPLACES the position's sl/tp with its own - zero erases;
  a partial close leaves sl/tp alone; a full close deletes them with the position;
* sl/tp trigger on the LAST TRADE (``trade(price)``), not on a quote move, and fill at that
  price (gaps slip). ``stop_fill_cap`` makes a stop fill in part; ``exchange_rejects_stops``
  makes the exchange refuse the triggered order (it fires again on the next trade);
* a reversal is recorded as two deals (OUT on the old position id, IN on a new one).
"""

from __future__ import annotations

from typing import Any

from hunter_exchanges.mt5.constants import (
    DealEntry,
    DealReason,
    Filling,
    OrderState,
    OrderType,
    Retcode,
    TimeMode,
    TradeAction,
)

from .mt5_types import Deal, Hooks, Ord, Pos

R = Retcode
Reply = tuple[int, int, int, float, float, str]  # retcode, order, deal, volume, price, comment


class FakeBroker:
    def __init__(self, symbol: str, t0_ms: int, hooks: Hooks | None = None) -> None:
        self.symbol = symbol
        self.hooks = hooks or Hooks()
        self.now_ms = t0_ms
        self.tick_size, self.tick_value, self.point, self.digits = 5.0, 1.0, 1.0, 0
        self.volume_min, self.volume_step, self.volume_max = 1.0, 1.0, 1000.0
        self.stops_level = 0
        self.bid, self.ask, self.last = 130000.0, 130005.0, 130000.0
        self.liquidity = 1000.0
        self.stop_fill_cap: float | None = None
        self.exchange_rejects_stops = False
        self.balance = 100_000.0
        self.margin_per_contract = 150.0
        self.positions: list[Pos] = []
        self.orders: list[Ord] = []  # active
        self.history: list[Ord] = []  # final
        self.deals: list[Deal] = []
        self._ticket = 1000

    # ------------------------------------------------------------------ account
    def next_ticket(self) -> int:
        self._ticket += 1
        return self._ticket

    def position(self) -> Pos | None:
        return self.positions[0] if self.positions else None

    def pnl(self, pos: Pos, price: float, volume: float) -> float:
        sign = 1.0 if pos.side == 0 else -1.0
        return sign * (price - pos.price_open) / self.tick_size * self.tick_value * volume

    def equity(self) -> float:
        return self.balance + sum(self.pnl(p, self.last, p.volume) for p in self.positions)

    def margin(self) -> float:
        return self.margin_per_contract * sum(p.volume for p in self.positions)

    def on_grid(self, price: float) -> bool:
        steps = price / self.tick_size
        return abs(steps - round(steps)) < 1e-9

    # ------------------------------------------------------------------ fills
    def _record(self, order: Ord, state: int) -> None:
        order.state, order.time_done_msc = state, self.now_ms
        if order in self.orders:
            self.orders.remove(order)
        self.history.append(order)

    def fill(
        self, order: Ord, side: int, volume: float, price: float, reason: int, magic: int
    ) -> None:
        pos = self.position()

        def deal(entry: int, vol: float, pid: int, profit: float = 0.0) -> None:
            commission = -1.0 * vol  # R$ 1 per contract per leg, booked on the balance below
            self.balance += commission
            self.deals.append(
                Deal(self.next_ticket(), order.ticket, self.now_ms, side, entry, magic, pid, reason,
                     vol, price, commission, profit, order.symbol, order.comment)
            )  # fmt: skip

        def open_position(vol: float, pid: int, ticket: int) -> None:
            self.positions.append(
                Pos(pid, ticket, order.symbol, side, vol, price, order.sl, order.tp, magic,
                    order.comment, self.now_ms, order.reason)
            )  # fmt: skip

        if pos is None:
            order.position_id = order.ticket
            open_position(volume, order.ticket, order.ticket)
            deal(int(DealEntry.IN), volume, order.ticket)
        elif pos.side == side:
            order.position_id = pos.position_id
            total = pos.volume + volume
            pos.price_open = (pos.price_open * pos.volume + price * volume) / total
            pos.volume, pos.sl, pos.tp = total, order.sl, order.tp  # inheritance: replaced
            deal(int(DealEntry.IN), volume, pos.position_id)
        elif volume < pos.volume:
            order.position_id = pos.position_id
            profit = self.pnl(pos, price, volume)
            self.balance += profit
            pos.volume -= volume  # a partial close leaves sl/tp alone
            deal(int(DealEntry.OUT), volume, pos.position_id, profit)
        elif volume == pos.volume:
            order.position_id = pos.position_id
            profit = self.pnl(pos, price, volume)
            self.balance += profit
            self.positions.remove(pos)
            deal(int(DealEntry.OUT), volume, pos.position_id, profit)
        else:  # reversal
            profit = self.pnl(pos, price, pos.volume)
            self.balance += profit
            self.positions.remove(pos)
            remainder = volume - pos.volume
            if self.hooks.reversal_new_identifier:  # model B: OUT on the old id, IN on a new one
                order.position_id = order.ticket
                deal(int(DealEntry.OUT), pos.volume, pos.position_id, profit)
                open_position(remainder, order.ticket, order.ticket)
                deal(int(DealEntry.IN), remainder, order.ticket)
            else:  # model A: one INOUT deal; the identifier stays, the ticket changes
                order.position_id = pos.position_id
                open_position(remainder, pos.position_id, self.next_ticket())
                deal(int(DealEntry.INOUT), volume, pos.position_id, profit)

    def _touch(self, side: int) -> float:
        return self.ask if side == 0 else self.bid

    def _marketable(self, side: int, price: float) -> bool:
        return self.ask <= price if side == 0 else self.bid >= price

    def _execute(self, order: Ord, side: int, price: float, *, rest: bool) -> Reply:
        want = order.volume_current
        qty = min(want, self.liquidity)
        if qty <= 0 or (order.filling == Filling.FOK and qty < want):
            self._record(order, int(OrderState.CANCELED if qty > 0 else OrderState.REJECTED))
            return (int(R.CANCEL if qty > 0 else R.REJECT), order.ticket, 0, 0.0, price, "")
        self.fill(order, side, qty, price, int(DealReason.EXPERT), order.magic)
        order.volume_current = want - qty
        deal = self.deals[-1].ticket
        if order.volume_current == 0:
            self._record(order, int(OrderState.FILLED))
            return (int(R.DONE), order.ticket, deal, qty, price, "Request executed")
        if rest and order.filling == Filling.RETURN:
            order.state = int(OrderState.PARTIAL)
            if order not in self.orders:
                self.orders.append(order)
        else:
            self._record(order, int(OrderState.CANCELED))
        return (int(R.DONE_PARTIAL), order.ticket, deal, qty, price, "Partial")

    def fill_resting(self) -> None:
        for order in list(self.orders):
            side = 0 if order.type == OrderType.BUY_LIMIT else 1
            if self._marketable(side, order.price_open):
                self._execute(order, side, order.price_open, rest=True)

    def trade(self, price: float) -> None:
        """A trade printed at ``price``: stops and targets trigger on it."""
        self.last = price
        for pos in list(self.positions):
            long = pos.side == 0
            hit_sl = pos.sl and (price <= pos.sl if long else price >= pos.sl)
            hit_tp = pos.tp and (price >= pos.tp if long else price <= pos.tp)
            if not (hit_sl or hit_tp) or self.exchange_rejects_stops:
                continue
            which = DealReason.SL if hit_sl else DealReason.TP
            qty = min(pos.volume, self.stop_fill_cap or pos.volume)
            order = Ord(self.next_ticket(), pos.symbol, int(OrderType.SELL if long else OrderType.BUY),
                        int(OrderState.FILLED), qty, 0.0, price, 0.0, 0.0, pos.magic,
                        f"[{which.name.lower()} {pos.sl if hit_sl else pos.tp:g}]", pos.position_id,
                        self.now_ms, int(Filling.IOC), int(TimeMode.GTC), 0, int(which))  # fmt: skip
            self.history.append(order)
            self.fill(order, 1 - pos.side, qty, price, int(which), pos.magic)

    def set_quote(self, bid: float, ask: float, last: float | None = None) -> None:
        self.bid, self.ask = bid, ask
        if last is not None:
            self.last = last
        self.fill_resting()

    def expire(self, *, day_end: bool = False) -> None:
        now_s = self.now_ms // 1000
        if day_end:  # the server zeroes sl/tp of exchange positions at the turn of the session
            for pos in self.positions:
                pos.sl = pos.tp = 0.0
        for order in list(self.orders):
            if (day_end and order.time_type == TimeMode.DAY) or (
                order.time_type == TimeMode.SPECIFIED and 0 < order.expiration <= now_s
            ):
                self._record(order, int(OrderState.EXPIRED))

    # ------------------------------------------------------------------ request handlers
    def _invalid(self, request: dict[str, Any]) -> int | None:
        if request.get("symbol") != self.symbol:
            return int(R.INVALID)
        volume = float(request.get("volume", 0.0))
        steps = volume / self.volume_step
        if not (self.volume_min <= volume <= self.volume_max) or abs(steps - round(steps)) > 1e-9:
            return int(R.INVALID_VOLUME)
        if not self.on_grid(float(request.get("price", 0.0))):
            return int(R.INVALID_PRICE)
        if any(not self.on_grid(float(request.get(k, 0.0))) for k in ("sl", "tp")):
            return int(R.INVALID_STOPS)
        return None

    def check(self, request: dict[str, Any]) -> tuple[int, str]:
        code = self._invalid(request)
        if code is not None:
            return code, "Invalid request"
        if self.margin() + self.margin_per_contract * float(request["volume"]) > self.equity():
            return int(R.NO_MONEY), "No money"
        return 0, "Done"

    def new_order(self, request: dict[str, Any]) -> Ord:
        return Ord(
            self.next_ticket(), self.symbol, int(request["type"]), int(OrderState.PLACED),
            float(request["volume"]), float(request["volume"]), float(request.get("price", 0.0)),
            float(request.get("sl", 0.0)), float(request.get("tp", 0.0)), int(request["magic"]),
            str(request.get("comment", "")), 0, self.now_ms, int(request.get("type_filling", 0)),
            int(request.get("type_time", 0)), int(request.get("expiration", 0)),
        )  # fmt: skip

    def handle(self, request: dict[str, Any]) -> Reply:
        action = int(request["action"])
        if action == TradeAction.SLTP:
            return self._sltp(request)
        if action == TradeAction.REMOVE:
            return self._remove(int(request["order"]))
        if action not in (TradeAction.DEAL, TradeAction.PENDING):
            return (int(R.INVALID), 0, 0, 0.0, 0.0, "Unsupported action")
        bad = self._invalid(request)
        if bad is not None:
            return (bad, 0, 0, 0.0, 0.0, "Invalid request")
        order = self.new_order(request)
        side = 0 if order.type in (OrderType.BUY, OrderType.BUY_LIMIT) else 1
        if action == TradeAction.DEAL:
            slack = float(request.get("deviation", 0)) * self.point
            price = float(request["price"])
            touch = self._touch(side)
            if (side == 0 and touch > price + slack) or (side == 1 and touch < price - slack):
                self._record(order, int(OrderState.REJECTED))
                return (int(R.REQUOTE), order.ticket, 0, 0.0, touch, "Requote")
            return self._execute(order, side, touch, rest=False)
        if self._marketable(side, order.price_open):
            return self._execute(order, side, self._touch(side), rest=True)
        self.orders.append(order)
        return (int(R.PLACED), order.ticket, 0, order.volume_current, order.price_open, "Placed")

    def _sltp(self, request: dict[str, Any]) -> Reply:
        pos = next((p for p in self.positions if p.ticket == int(request["position"])), None)
        if pos is None:
            return (int(R.POSITION_CLOSED), 0, 0, 0.0, 0.0, "Position closed")
        sl, tp = float(request["sl"]), float(request["tp"])
        gap = self.stops_level * self.point
        long = pos.side == 0
        sl_bad = sl != 0 and (sl > self.bid - gap if long else sl < self.ask + gap)
        tp_bad = tp != 0 and (tp < self.ask + gap if long else tp > self.bid - gap)
        if not (self.on_grid(sl) and self.on_grid(tp)) or sl_bad or tp_bad:
            return (int(R.INVALID_STOPS), 0, 0, 0.0, 0.0, "Invalid stops")
        if (sl, tp) == (pos.sl, pos.tp):
            return (int(R.NO_CHANGES), 0, 0, 0.0, 0.0, "No changes")
        pos.sl, pos.tp = sl, tp
        return (int(R.DONE), 0, 0, 0.0, 0.0, "Request executed")

    def _remove(self, ticket: int) -> Reply:
        order = next((o for o in self.orders if o.ticket == ticket), None)
        if order is None:
            return (int(R.INVALID_ORDER), 0, 0, 0.0, 0.0, "Order not found")
        self._record(order, int(OrderState.CANCELED))
        return (int(R.DONE), ticket, 0, 0.0, 0.0, "Request executed")
