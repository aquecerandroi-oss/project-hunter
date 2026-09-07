"""T2.5g — the collector's own count of events it lost.

The bug this pins: ``streaming.py`` asked the *adapter* for a
``dropped_events`` attribute it never had (``connection_field(adapter, ...)``
is a plain ``getattr``), so ``CoverageTracker.stamp`` was told ``0`` on every
stamp and the "a drop breaks the interval" rule was dead code in production —
measured on the VPS and on the local stack with 1.2M and 8.3M dropped events
next to a coverage hash that never once broke for that reason.
"""

from __future__ import annotations

from typing import Any

from hunter_exchanges.base import ConnectionState
from hunter_market_worker.supervision import DroppedEventsLedger


class _Adapter:
    def __init__(self, states: dict[str, ConnectionState]) -> None:
        self._states = states

    def connection_states(self) -> dict[str, ConnectionState]:
        return self._states


class _OldAdapter:
    """An adapter from before ``connection_states`` existed."""


def _state(dropped: int) -> ConnectionState:
    return ConnectionState(route="stream", ws_state="connected", dropped_events=dropped)


def test_the_total_is_the_sum_over_every_connection() -> None:
    adapter: Any = _Adapter({"a": _state(3), "b": _state(4)})
    ledger = DroppedEventsLedger()

    assert ledger.observe(adapter) == 7


def test_it_only_ever_grows_when_a_connection_is_recreated_from_zero() -> None:
    """``ws.py`` replaces ``ConnectionState`` on reconnect, so a per-connection
    counter can go 100 -> 0. A plain sum would fall (and a ``max(0, delta)``
    would silently swallow every drop after the reset)."""
    states = {"a": _state(100)}
    adapter: Any = _Adapter(states)
    ledger = DroppedEventsLedger()
    assert ledger.observe(adapter) == 100

    states["a"] = _state(5)  # the connection was recreated and dropped 5 more
    assert ledger.observe(adapter) == 105

    states["a"] = _state(6)
    assert ledger.observe(adapter) == 106


def test_an_adapter_without_connection_states_reports_nothing_lost() -> None:
    ledger = DroppedEventsLedger()

    assert ledger.observe(_OldAdapter()) == 0
