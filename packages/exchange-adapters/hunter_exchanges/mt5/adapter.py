"""`Mt5Adapter`: the :class:`~hunter_exchanges.mt5.port.Mt5Port` over a vendor-shaped module.

``Mt5Adapter(raw)`` accepts anything with the vendor module's functions (:class:`~.raw.Mt5Raw`):
the real ``MetaTrader5`` on a Windows box next to a logged-in terminal
(:meth:`Mt5Adapter.for_real_terminal`), or the offline fake in tests. The vendor package is
imported lazily and only by :func:`~.raw.load_metatrader5`.
"""

from __future__ import annotations

from .adapter_base import Mt5Config
from .adapter_writes import WritesMixin
from .raw import load_metatrader5

__all__ = ["Mt5Adapter", "Mt5Config"]


class Mt5Adapter(WritesMixin):
    @classmethod
    def for_real_terminal(cls, config: Mt5Config | None = None) -> Mt5Adapter:
        """Windows only; raises :class:`~.errors.Mt5NotAvailable` anywhere else."""
        return cls(load_metatrader5(), config=config)
