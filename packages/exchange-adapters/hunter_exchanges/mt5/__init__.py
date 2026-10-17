"""MetaTrader 5 adapter for the B3 robot (``docs/RISK_ENGINE_B3.md``, task R2).

Everything MT5-specific stays in this package: callers see the ``Decimal``/UTC models in
:mod:`hunter_exchanges.mt5.models` and the :class:`~hunter_exchanges.mt5.port.Mt5Port` protocol.
Importing it never imports the vendor ``MetaTrader5`` wheel (Windows-only) — see
:mod:`hunter_exchanges.mt5.raw`.
"""

from __future__ import annotations
