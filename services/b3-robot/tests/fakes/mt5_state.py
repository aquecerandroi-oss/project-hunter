"""FAKE MetaTrader 5: shared state and the float/malformed emission helpers. TEST CODE ONLY."""

from __future__ import annotations

import math
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from hunter_exchanges.mt5.constants import AccountMarginMode, AccountTradeMode, SymbolTradeMode

from .mt5_engine import FakeBroker
from .mt5_types import Hooks

T0_MS = int(datetime(2026, 11, 4, 13, 0, 0, tzinfo=UTC).timestamp() * 1000)
NOT_FOUND = (-4, "Terminal: Not found")
NO_IPC = (-10004, "No IPC connection")
SEND_FAILED = (-10001, "Send failed")


class FakeState:
    def __init__(
        self,
        symbol: str = "WINZ26",
        *,
        trade_mode: AccountTradeMode = AccountTradeMode.DEMO,
        margin_mode: AccountMarginMode = AccountMarginMode.EXCHANGE,
    ) -> None:
        self.hooks = Hooks()
        self.broker = FakeBroker(symbol, T0_MS, self.hooks)
        self.trade_mode, self.margin_mode = int(trade_mode), int(margin_mode)
        self.connected, self.algo_trading, self.tradeapi_disabled = True, True, False
        self.build, self.version_str = 4755, "17 Jul 2025"
        self.symbol_trade_mode = int(SymbolTradeMode.FULL)
        self.filling_mask, self.expiration_mask = 3, 15
        self._err: tuple[int, str] = (1, "Success")
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sent_requests: list[dict[str, Any]] = []
        self.initialize_kwargs: list[dict[str, Any]] = []
        self.login_calls = 0
        self._malform: dict[str, tuple[str, str]] = {}
        self.hang_entered, self.hang_release = threading.Event(), threading.Event()

    # ------------------------------------------------------------------ emission (floats, noise, malformed)
    def _n(self, x: float) -> float:
        return math.nextafter(x, math.inf) if self.hooks.float_noise and x != 0 else x

    def _emit(self, function: str, row: Any) -> Any:
        if function not in self._malform:
            return row
        mode, field = self._malform[function]
        data = row._asdict()
        if mode == "missing":
            del data[field]
        elif mode == "nan":
            data[field] = float("nan")
        elif mode == "wrong_type":
            data[field] = "garbage"
        return SimpleNamespace(**data)

    def _gate(self, name: str, **kw: Any) -> bool:
        self.calls.append((name, kw))
        if not self.connected:
            self._err = NO_IPC
            return False
        return True
