"""`Mt5Port`: everything the B3 robot needs from MetaTrader 5, as one Protocol.

Two implementations satisfy it: :class:`~hunter_exchanges.mt5.adapter.Mt5Adapter` over the real
vendor module (Windows only, ``live`` tests only) and the same adapter over the offline fake in
``services/b3-robot/tests/fakes/mt5_fake.py``. The contract suite in ``tests/mt5/`` is written
against this Protocol so it can run unchanged against a demo terminal.

Reading and refusing:

* every read returns ``Decimal``/UTC models or raises :class:`~.errors.Mt5ReadError` — an
  unavailable value is never a zero;
* every mutation either raises :class:`~.errors.Mt5NotSent` (nothing was sent) or returns a
  :class:`~.models.SendOutcome`; after the request may have left, there is no exception, only an
  outcome whose verdict may be ``UNCERTAIN`` (never resend);
* there is no method to log in, and none that closes a position by an opposite order beyond
  what ``send_entry`` is: the exit by bracket is ``send_sltp`` (contract §5.5 is R5's policy).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from .ipc import LateResult
from .models import (
    EntryRequest,
    Mt5Account,
    Mt5CheckResult,
    Mt5Deal,
    Mt5Order,
    Mt5Position,
    Mt5SymbolSpec,
    Mt5TerminalInfo,
    Mt5Tick,
    SendOutcome,
    Side,
    SltpRequest,
)
from .spec import SpecSnapshot, SpecStatus


class Mt5Port(Protocol):
    @property
    def ipc_hung(self) -> bool: ...
    def drain_late_results(self) -> list[LateResult]: ...

    # ---- session (never with credentials: the terminal is already logged in by the Everton)
    async def attach(self) -> None: ...
    async def shutdown(self) -> None: ...

    # ---- reads
    async def terminal_info(self) -> Mt5TerminalInfo: ...
    async def account_info(self) -> Mt5Account: ...
    async def symbol_spec(self, symbol: str) -> Mt5SymbolSpec: ...
    async def tick(self, symbol: str) -> Mt5Tick: ...
    async def positions(self, symbol: str | None = None) -> list[Mt5Position]: ...
    async def orders(self, symbol: str | None = None) -> list[Mt5Order]: ...
    async def history_orders(self, since: datetime, until: datetime) -> list[Mt5Order]: ...
    async def history_order(self, ticket: int) -> Mt5Order | None: ...
    async def history_deals(self, since: datetime, until: datetime) -> list[Mt5Deal]: ...
    async def deals_of_position(self, position_id: int) -> list[Mt5Deal]: ...
    async def calc_margin(
        self, side: Side, symbol: str, volume: Decimal, price: Decimal
    ) -> Decimal: ...
    async def check_entry(self, request: EntryRequest) -> Mt5CheckResult: ...

    # ---- specification watcher (contract §3.9)
    async def read_spec_snapshot(self, symbol: str) -> SpecSnapshot: ...
    def pin_spec(self, pin: SpecSnapshot) -> None: ...
    async def refresh_spec(self, symbol: str) -> SpecStatus: ...
    @property
    def spec_status(self) -> SpecStatus | None: ...

    # ---- mutations
    async def send_entry(self, request: EntryRequest) -> SendOutcome: ...
    async def send_sltp(self, request: SltpRequest) -> SendOutcome: ...
    async def cancel_order(self, ticket: int, *, magic: int) -> SendOutcome: ...
