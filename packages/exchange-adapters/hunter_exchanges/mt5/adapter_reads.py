"""The read half of :class:`~hunter_exchanges.mt5.adapter.Mt5Adapter`.

Every read goes through the single IPC lane (:mod:`.ipc`) and :mod:`.parse`; a ``None`` from the
terminal is :class:`~.errors.Mt5ReadError`, an empty tuple is an empty answer. Positions, orders
and deals are re-read from the broker on every call and **never cached** (contract §4.5: a
cached attribution survives a disconnect it must not survive).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import Any

from .adapter_base import AdapterBase
from .constants import OrderType
from .convert import OffGridError, epoch_from_utc, to_float_on_grid
from .errors import Mt5ReadError
from .models import (
    Mt5Account,
    Mt5Deal,
    Mt5Order,
    Mt5Position,
    Mt5SymbolSpec,
    Mt5TerminalInfo,
    Mt5Tick,
    Side,
)
from .parse import (
    Grid,
    parse_account,
    parse_deal,
    parse_margin,
    parse_order,
    parse_position,
    parse_symbol,
    parse_terminal,
    parse_tick,
)
from .raw import package_version
from .spec import SpecSnapshot


class ReadsMixin(AdapterBase):
    # ------------------------------------------------------------------ session

    async def attach(self) -> None:
        """Attach to the already running, already logged-in terminal. No credentials, ever."""
        kwargs: dict[str, Any] = {"timeout": self.config.connect_timeout_ms}
        if self.config.terminal_path is not None:
            kwargs["path"] = self.config.terminal_path

        def initialize() -> tuple[bool, tuple[int, str] | None]:
            ok = bool(self._raw.initialize(**kwargs))
            return ok, (None if ok else self._raw.last_error())

        budget = self.config.connect_timeout_ms / 1000 + self.config.ipc_call_timeout_s
        (ok, error), _ = await self._ipc.call("initialize", initialize, timeout_s=budget)
        if not ok:
            raise Mt5ReadError("initialize", reason="initialize_failed", last_error=error)

    async def shutdown(self) -> None:
        if not self._ipc.hung:
            await self._ipc.call("shutdown", self._raw.shutdown)
        self._ipc.close()

    # ------------------------------------------------------------------ account / terminal

    async def terminal_info(self) -> Mt5TerminalInfo:
        raw = await self._read("terminal_info", self._raw.terminal_info)
        return parse_terminal(raw, self._clock())

    async def account_info(self) -> Mt5Account:
        raw = await self._read("account_info", self._raw.account_info)
        return parse_account(raw, self._clock())

    # ------------------------------------------------------------------ symbols

    async def symbol_spec(self, symbol: str) -> Mt5SymbolSpec:
        raw = await self._read(f"symbol_info({symbol})", partial(self._raw.symbol_info, symbol))
        return parse_symbol(raw, symbol)

    async def _grid(self, symbol: str) -> Grid:
        spec = await self.symbol_spec(symbol)
        return Grid(tick=spec.trade_tick_size, volume_step=spec.volume_step)

    async def tick(self, symbol: str) -> Mt5Tick:
        what = f"symbol_info_tick({symbol})"
        grid = await self._grid(symbol)
        result, error = await self._ipc.call(what, partial(self._raw.symbol_info_tick, symbol))
        if result is None:  # a symbol outside Market Watch has no tick: select it once and retry
            await self._ipc.call("symbol_select", partial(self._raw.symbol_select, symbol, True))
            result, error = await self._ipc.call(what, partial(self._raw.symbol_info_tick, symbol))
        if result is None:
            raise Mt5ReadError(what, reason="none_result", last_error=error)
        return parse_tick(result, symbol, grid, self._clock())

    async def read_spec_bundle(self, symbol: str) -> tuple[Mt5SymbolSpec, SpecSnapshot]:
        """One fresh read of the spec and of everything the spec pin covers."""
        spec = await self.symbol_spec(symbol)
        account = await self.account_info()
        version = await self._read("version", self._raw.version)
        try:
            terminal_version = f"{version[0]}.{version[1]}"
        except (TypeError, IndexError):
            raise Mt5ReadError("version", reason="malformed:version") from None
        snapshot = SpecSnapshot.from_reads(
            spec,
            account,
            terminal_version=terminal_version,
            package_version=package_version(self._raw),
        )
        return spec, snapshot

    async def read_spec_snapshot(self, symbol: str) -> SpecSnapshot:
        return (await self.read_spec_bundle(symbol))[1]

    # ------------------------------------------------------------------ positions / orders

    async def _grids_for(self, symbols: set[str]) -> dict[str, Grid]:
        if "" in symbols:
            raise Mt5ReadError("rows", reason="malformed:symbol")
        return {symbol: await self._grid(symbol) for symbol in sorted(symbols)}

    async def positions(self, symbol: str | None = None) -> list[Mt5Position]:
        kwargs = {"symbol": symbol} if symbol else {}
        rows = await self._read("positions_get", partial(self._raw.positions_get, **kwargs))
        grids = await self._grids_for({str(getattr(r, "symbol", "")) for r in rows})
        return [parse_position(r, grids[str(r.symbol)]) for r in rows]

    async def orders(self, symbol: str | None = None) -> list[Mt5Order]:
        kwargs = {"symbol": symbol} if symbol else {}
        rows = await self._read("orders_get", partial(self._raw.orders_get, **kwargs))
        grids = await self._grids_for({str(getattr(r, "symbol", "")) for r in rows})
        return [parse_order(r, grids[str(r.symbol)]) for r in rows]

    async def history_orders(self, since: datetime, until: datetime) -> list[Mt5Order]:
        what = "history_orders_get"
        args = (epoch_from_utc(since), epoch_from_utc(until))
        rows = await self._read(what, partial(self._raw.history_orders_get, *args))
        grids = await self._grids_for({str(getattr(r, "symbol", "")) for r in rows})
        return [parse_order(r, grids[str(r.symbol)], what) for r in rows]

    async def history_order(self, ticket: int) -> Mt5Order | None:
        what = "history_orders_get(ticket)"
        rows = await self._read(what, partial(self._raw.history_orders_get, ticket=ticket))
        if len(rows) == 0:
            return None
        grid = await self._grid(str(rows[0].symbol))
        return parse_order(rows[0], grid, what)

    async def _parse_deals(self, rows: Any) -> list[Mt5Deal]:
        # Balance operations (deposits...) have no symbol and no grid: they carry no price.
        grids = await self._grids_for({str(getattr(r, "symbol", "")) for r in rows} - {""})
        no_grid = Grid(tick=Decimal("0.0000001"), volume_step=Decimal("0.0000001"))
        deals = [parse_deal(r, grids.get(str(r.symbol), no_grid)) for r in rows]
        unique: dict[int, Mt5Deal] = {}
        for deal in (
            deals
        ):  # the terminal may repeat a deal; two *different* ones with one ticket are corrupt
            seen = unique.setdefault(deal.ticket, deal)
            if seen != deal:
                raise Mt5ReadError(
                    "history_deals_get", reason=f"malformed:duplicate_ticket:{deal.ticket}"
                )
        return sorted(unique.values(), key=lambda d: (d.time, d.ticket))

    async def history_deals(self, since: datetime, until: datetime) -> list[Mt5Deal]:
        args = (epoch_from_utc(since), epoch_from_utc(until))
        rows = await self._read("history_deals_get", partial(self._raw.history_deals_get, *args))
        return await self._parse_deals(rows)

    async def deals_of_position(self, position_id: int) -> list[Mt5Deal]:
        rows = await self._read(
            "history_deals_get(position)",
            partial(self._raw.history_deals_get, position=position_id),
        )
        return await self._parse_deals(rows)

    # ------------------------------------------------------------------ margin

    async def calc_margin(
        self, side: Side, symbol: str, volume: Decimal, price: Decimal
    ) -> Decimal:
        what = f"order_calc_margin({symbol})"
        spec = await self.symbol_spec(symbol)
        try:
            vol_f = to_float_on_grid(volume, spec.volume_step)
            price_f = to_float_on_grid(price, spec.trade_tick_size)
        except OffGridError:
            raise Mt5ReadError(what, reason="off_grid") from None
        action = int(OrderType.BUY if side is Side.BUY else OrderType.SELL)
        raw = await self._read(
            what, partial(self._raw.order_calc_margin, action, symbol, vol_f, price_f)
        )
        return parse_margin(raw, what)
