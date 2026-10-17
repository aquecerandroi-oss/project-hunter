"""The shape of the vendor ``MetaTrader5`` module, and the lazy, Windows-only loader.

``MetaTrader5`` ships ``win_amd64`` wheels only and talks to a *local, already logged-in*
terminal through IPC. Therefore:

* nothing in this package imports it at module level (``tests/mt5/test_lazy_import.py`` fails
  if one does) — Linux CI never installs it;
* :func:`load_metatrader5` imports it on demand and only on Windows;
* the protocol below has **no ``login``** and ``initialize`` is only ever called with the
  terminal ``path``/``timeout``/``portable`` keywords by the adapter: credentials are typed into
  the terminal by the Everton, never passed by us (design §1.3, contract I-S-1).

Return types are ``Any`` on purpose: the vendor returns named tuples of floats (or ``None``).
:mod:`hunter_exchanges.mt5.parse` is the one place that turns them into ``Decimal`` models.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any, Protocol

from .errors import Mt5NotAvailable


class Mt5Raw(Protocol):
    """The subset of the ``MetaTrader5`` module this adapter may call."""

    def initialize(self, *args: Any, **kwargs: Any) -> bool: ...
    def shutdown(self) -> None: ...
    def last_error(self) -> tuple[int, str]: ...
    def version(self) -> Any: ...
    def terminal_info(self) -> Any: ...
    def account_info(self) -> Any: ...
    def symbol_info(self, symbol: str) -> Any: ...
    def symbol_info_tick(self, symbol: str) -> Any: ...
    def symbol_select(self, symbol: str, enable: bool = True) -> bool: ...
    def positions_get(self, **kwargs: Any) -> Any: ...
    def orders_get(self, **kwargs: Any) -> Any: ...
    def history_orders_get(self, *args: Any, **kwargs: Any) -> Any: ...
    def history_deals_get(self, *args: Any, **kwargs: Any) -> Any: ...
    def order_check(self, request: dict[str, Any]) -> Any: ...
    def order_calc_margin(self, action: int, symbol: str, volume: float, price: float) -> Any: ...
    def order_send(self, request: dict[str, Any]) -> Any: ...


def load_metatrader5(*, platform: str | None = None) -> Mt5Raw:
    """Import the vendor module now. ``platform`` is injectable for tests (default ``sys.platform``)."""
    current = platform if platform is not None else sys.platform
    if current != "win32":
        raise Mt5NotAvailable(
            "the MetaTrader5 package only runs on Windows next to a terminal "
            f"(platform={current!r}); use the fake in tests"
        )
    try:
        module = importlib.import_module("MetaTrader5")
    except ImportError as exc:
        raise Mt5NotAvailable(f"MetaTrader5 is not installed: {exc}") from exc
    return module  # type: ignore[return-value]  # a module satisfies the Protocol structurally


def package_version(raw: object) -> str:
    """Version string of the vendor package (``__version__``), or ``unknown``."""
    return str(getattr(raw, "__version__", "unknown"))
