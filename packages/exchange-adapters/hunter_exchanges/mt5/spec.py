"""The specification watcher (``docs/RISK_ENGINE_B3.md`` §3.9, check 23; design §3.9).

At arming the robot pins the contract specification, the account margin mode and the versions
of the terminal and of the ``MetaTrader5`` package. Every 60 s and on start it re-reads; any
divergence refuses **entries** (``spec_changed``) until the Everton re-arms having looked at the
new values; three failed reads in a row refuse as well (``spec_unreadable``). Exits continue.

Two latches, deliberately different:

* ``CHANGED`` is latched: a later good read that matches the pin again **never** clears it —
  a tick size that flickered is a tick size that can flicker. Only :meth:`SpecWatcher.rearm`.
* ``UNREADABLE`` is a function of the *consecutive* failure count and clears with a good read
  that matches the pin; it never downgrades ``CHANGED``.

This module is pure (no IO): :class:`~hunter_exchanges.mt5.adapter.Mt5Adapter` does the reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .models import Mt5Account, Mt5Model, Mt5SymbolSpec

_COMPARED = (
    "symbol", "trade_tick_size", "trade_tick_value", "point", "digits", "volume_min",
    "volume_step", "volume_max", "trade_mode", "filling_mode", "expiration_mode",
    "account_margin_mode", "terminal_version", "package_version",
)  # fmt: skip


class SpecSnapshot(Mt5Model):
    """The pinned fields of contract §8.1 ``SpecPin``/``SpecNow`` that the terminal can answer.

    It is **not** the whole ``SpecPin``: ``order_lifecycle_proven`` (T14), ``comment_preserved``
    (T8) and ``stale_ticket_rejection_proven`` (T13) are evidence the demo session produces, and
    R5/R1 compose them with this snapshot at arming. The watcher compares only what it can read."""

    symbol: str
    trade_tick_size: Decimal
    trade_tick_value: Decimal
    point: Decimal
    digits: int
    volume_min: Decimal
    volume_step: Decimal
    volume_max: Decimal
    trade_mode: int
    filling_mode: int
    expiration_mode: int
    account_margin_mode: str
    terminal_version: str
    package_version: str

    @classmethod
    def from_reads(
        cls,
        spec: Mt5SymbolSpec,
        account: Mt5Account,
        *,
        terminal_version: str,
        package_version: str,
    ) -> SpecSnapshot:
        return cls(
            symbol=spec.symbol,
            trade_tick_size=spec.trade_tick_size,
            trade_tick_value=spec.trade_tick_value,
            point=spec.point,
            digits=spec.digits,
            volume_min=spec.volume_min,
            volume_step=spec.volume_step,
            volume_max=spec.volume_max,
            trade_mode=spec.trade_mode,
            filling_mode=spec.filling_mode,
            expiration_mode=spec.expiration_mode,
            account_margin_mode=account.margin_mode.value,
            terminal_version=terminal_version,
            package_version=package_version,
        )


class SpecStatus(StrEnum):
    OK = "ok"
    CHANGED = "changed"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class SpecDiff:
    field: str
    pinned: object
    now: object


class SpecWatcher:
    """State machine over a pin; see the module docstring for the two latches."""

    def __init__(self, pin: SpecSnapshot, *, unreadable_after: int = 3) -> None:
        self._pin = pin
        self._unreadable_after = unreadable_after
        self._diffs: dict[str, SpecDiff] = {}
        self._failures = 0

    @property
    def pin(self) -> SpecSnapshot:
        return self._pin

    @property
    def diffs(self) -> tuple[SpecDiff, ...]:
        return tuple(self._diffs.values())

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    @property
    def status(self) -> SpecStatus:
        if self._diffs:
            return SpecStatus.CHANGED
        if self._failures >= self._unreadable_after:
            return SpecStatus.UNREADABLE
        return SpecStatus.OK

    @property
    def refuses_entries(self) -> bool:
        return self.status is not SpecStatus.OK

    def observe(self, now: SpecSnapshot) -> SpecStatus:
        """Record a successful read."""
        self._failures = 0
        for name in _COMPARED:
            pinned, current = getattr(self._pin, name), getattr(now, name)
            if pinned != current and name not in self._diffs:
                self._diffs[name] = SpecDiff(name, pinned, current)
        return self.status

    def observe_failure(self) -> SpecStatus:
        """Record a failed read."""
        self._failures += 1
        return self.status

    def rearm(self, new_pin: SpecSnapshot) -> None:
        """The Everton looked at the new values and re-armed: the only way back from CHANGED."""
        self._pin = new_pin
        self._diffs = {}
        self._failures = 0
